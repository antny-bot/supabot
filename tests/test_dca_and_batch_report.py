import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.parsers import KST
from core.dca_manager import (
    DcaManager,
    parse_dca_schedule,
    format_dca_schedule,
    parse_dca_amount,
    parse_dca_time,
    parse_dca_max_runs,
    compute_next_run_at,
    execute_due_dca_schedules,
    extract_available_cash,
    analyze_user_cash_sufficiency,
    format_cash_health_section,
    check_daily_cash_alerts,
    _daily_cash_alert_sent,
    _cash_last_checked_ts,
)
from core.order_manager import OrderManager
from core.trade_log import append_trade, read_trades
from core.formatters import (
    build_report_view_page,
    build_timeseries_report_view_page,
)
from handlers.query_handlers import parse_report_args
from handlers import list_view_handlers


def test_parse_dca_schedule_variants():
    assert parse_dca_schedule("매일") == {
        "frequency": "daily",
        "days_of_week": None,
        "day_of_month": None,
    }
    assert parse_dca_schedule("매주수") == {
        "frequency": "weekly",
        "days_of_week": [2],
        "day_of_month": None,
    }
    assert parse_dca_schedule("월수금") == {
        "frequency": "days",
        "days_of_week": [0, 2, 4],
        "day_of_month": None,
    }
    assert parse_dca_schedule("평일") == {
        "frequency": "days",
        "days_of_week": [0, 1, 2, 3, 4],
        "day_of_month": None,
    }
    assert parse_dca_schedule("매월15일") == {
        "frequency": "monthly",
        "days_of_week": None,
        "day_of_month": 15,
    }


def test_parse_dca_amount_and_options():
    assert parse_dca_amount("5만") == ("budget", 50000.0)
    assert parse_dca_amount("10만원") == ("budget", 100000.0)
    assert parse_dca_amount("$150") == ("budget", 150.0)
    assert parse_dca_amount("2주") == ("volume", 2.0)
    assert parse_dca_amount("0.05개") == ("volume", 0.05)
    assert parse_dca_time("9:05") == "09:05"
    assert parse_dca_time("9시5분") == "09:05"
    assert parse_dca_max_runs("12회") == 12


def test_compute_next_run_at():
    # 2026-10-26 08:00 KST (Monday)
    base_dt = datetime(2026, 10, 26, 8, 0, 0, tzinfo=KST)
    now_ts = base_dt.timestamp()

    # 오늘 09:05가 아직 안 지났으므로 당일 09:05
    next_daily = compute_next_run_at("daily", "09:05", now=now_ts)
    assert datetime.fromtimestamp(next_daily, tz=KST) == datetime(2026, 10, 26, 9, 5, 0, tzinfo=KST)

    # after_current=True 이면 내일 09:05
    next_daily_after = compute_next_run_at("daily", "09:05", now=now_ts, after_current=True)
    assert datetime.fromtimestamp(next_daily_after, tz=KST) == datetime(2026, 10, 27, 9, 5, 0, tzinfo=KST)

    # 매주 수요일(2) 10:00 -> 2026-10-28 10:00
    next_wed = compute_next_run_at("weekly", "10:00", days_of_week=[2], now=now_ts)
    assert datetime.fromtimestamp(next_wed, tz=KST) == datetime(2026, 10, 28, 10, 0, 0, tzinfo=KST)

    # 매월 15일 09:05 -> 이미 10월 26일이므로 11월 15일 09:05
    next_monthly = compute_next_run_at("monthly", "09:05", day_of_month=15, now=now_ts)
    assert datetime.fromtimestamp(next_monthly, tz=KST) == datetime(2026, 11, 15, 9, 5, 0, tzinfo=KST)


def test_dca_execution_assigns_batch_group_no(tmp_path, monkeypatch):
    dca_file = tmp_path / "dca_schedules.json"
    orders_file = tmp_path / "orders.json"
    trades_file = tmp_path / "trades.jsonl"

    monkeypatch.setattr("core.order_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.trade_log.is_db_available", lambda: False)
    monkeypatch.setattr("core.trade_log.TRADE_LOG_PATH", str(trades_file))

    om = OrderManager(file_path=str(orders_file))
    dm = DcaManager(file_path=str(dca_file))

    # 기존 체결 로그에 #2 배치가 있으면 다음 배치 번호는 #3이어야 함
    append_trade("u1", "upbit", "KRW-BTC", "bid", 90000000, 0.001, "grid", "uuid-0", path=str(trades_file), group_no=2)

    gno = dm.get_next_group_no("u1", order_manager=om)
    assert gno == 3

    now_ts = datetime(2026, 10, 26, 9, 5, 0, tzinfo=KST).timestamp()
    sched = dm.add_schedule(
        user_id="u1",
        exchange="upbit",
        ticker="KRW-BTC",
        side="bid",
        frequency="daily",
        exec_time="09:05",
        amount_type="budget",
        amount=50000,
        max_runs=2,
        group_no=gno,
        now=now_ts - 60,  # due now
    )
    assert sched["group_no"] == 3
    assert sched["next_run_at"] <= now_ts

    # Mock exchange_adapter & user_manager
    ex_obj = MagicMock()
    ex_obj.is_market_open.return_value = True
    ex_obj.is_order_placement_allowed.return_value = True
    ex_obj.adjust_price_to_tick.side_effect = lambda p, t=None: round(p, -3)
    ex_obj.round_volume.side_effect = lambda v: round(v, 8)
    ex_obj.requires_integer_volume.return_value = False

    adapter = MagicMock()
    adapter.get_exchange.return_value = ex_obj
    adapter.get_ticker = AsyncMock(return_value={"trade_price": 100000000})
    adapter.get_min_order_amount.return_value = 5000
    adapter.create_order = AsyncMock(return_value={"uuid": "dca-order-1"})

    um = MagicMock()
    um.get_user.return_value = {"is_active": True, "preferences": {}}

    app = MagicMock()
    app.bot.send_message = AsyncMock()

    executed = asyncio.run(
        execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=now_ts)
    )
    assert executed == 1
    assert len(om.orders) == 1
    placed = om.orders[0]
    assert placed["uuid"] == "dca-order-1"
    assert placed["strategy"] == "dca"
    assert placed["group_no"] == 3

    updated_sched = dm.get_schedule(sched["id"])
    assert updated_sched["run_count"] == 1
    assert updated_sched["next_run_at"] > now_ts


def test_trade_log_filtering_and_timeseries_report(tmp_path, monkeypatch):
    trades_file = tmp_path / "trades.jsonl"
    monkeypatch.setattr("core.trade_log.is_db_available", lambda: False)

    append_trade("u1", "upbit", "KRW-BTC", "bid", 90000000, 0.001, "dca", "u-1", path=str(trades_file), group_no=5)
    append_trade("u1", "upbit", "KRW-BTC", "bid", 92000000, 0.001, "dca", "u-2", path=str(trades_file), group_no=5)
    append_trade("u1", "upbit", "KRW-BTC", "ask", 96000000, 0.001, "dca", "u-3", path=str(trades_file), group_no=5)
    append_trade("u1", "upbit", "KRW-ETH", "bid", 4000000, 0.1, "grid", "u-4", path=str(trades_file), group_no=6)

    batch5 = read_trades("u1", "all", path=str(trades_file), group_no=5)
    assert len(batch5) == 3

    eth_only = read_trades("u1", "all", path=str(trades_file), ticker="ETH")
    assert len(eth_only) == 1
    assert eth_only[0]["group_no"] == 6

    # parse_report_args 검증
    assert parse_report_args(["#5", "week"]) == ("week", 5, None)
    assert parse_report_args(["BTC", "month"]) == ("month", None, "BTC")
    assert parse_report_args(["005930"]) == ("all", None, "005930")
    assert parse_report_args(["#5", "BTC"]) == ("all", 5, "BTC")

    # 시계열 리포트 렌더링 검증 (평단 91,000,000원에 0.001개 매도 -> 실현손익 +5,000원)
    text, page, total_pages = build_timeseries_report_view_page(
        batch5, period="all", group_no=5, page=0
    )
    assert "시계열 매매 리포트 (배치 #5 | 전체)" in text
    assert "시간순 체결 타임라인" in text
    assert "+5,000원" in text
    assert page == 0
    assert total_pages == 1

    # 일반 리포트에서도 배치 요약 섹션이 포함되는지 검증
    all_trades = read_trades("u1", "all", path=str(trades_file))
    full_text, _, _ = build_report_view_page(all_trades, "all", 0)
    assert "배치(#N)별 전략 체결 요약" in full_text
    assert "#5" in full_text
    assert "#6" in full_text


def test_cash_sufficiency_and_daily_alerts(tmp_path, monkeypatch):
    dca_file = tmp_path / "dca_schedules.json"
    orders_file = tmp_path / "orders.json"
    trades_file = tmp_path / "trades.jsonl"
    monkeypatch.setattr("core.order_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.trade_log.is_db_available", lambda: False)
    monkeypatch.setattr("core.trade_log.TRADE_LOG_PATH", str(trades_file))
    monkeypatch.setattr("core.dca_manager.append_operational_event", lambda *a, **kw: None)

    om = OrderManager(file_path=str(orders_file))
    dm = DcaManager(file_path=str(dca_file))

    now_ts = datetime(2026, 10, 26, 9, 0, 0, tzinfo=KST).timestamp()
    # 업비트 매일 10만원 정기 매수 (다음 1회 10만원, 7일 70만원 필요)
    dm.add_schedule(
        user_id="u1",
        exchange="upbit",
        ticker="KRW-BTC",
        side="bid",
        frequency="daily",
        exec_time="09:05",
        amount_type="budget",
        amount=100000,
        group_no=1,
        now=now_ts,
    )
    # 한투 매주월 1주 정기 매수 (현재가 70,000원 가정 -> 1회 70,000원)
    dm.add_schedule(
        user_id="u1",
        exchange="kis",
        ticker="005930",
        side="bid",
        frequency="weekly",
        days_of_week=[0],
        exec_time="09:05",
        amount_type="volume",
        amount=1,
        group_no=2,
        now=now_ts,
    )

    # 업비트 가용 KRW = 30,000원 (1회 100,000원 대비 70,000원 즉시 부족 -> short_next)
    # 한투 가용 예수금 = 200,000원 (충분 -> ok)
    async def fake_get_balances(uid, ex):
        if ex == "upbit":
            return [{"currency": "KRW", "balance": "30000", "locked": "50000"}]
        if ex == "kis":
            return {"cash": 200000, "total_eval": 500000, "stocks": []}
        return None

    adapter = MagicMock()
    adapter.get_balances = AsyncMock(side_effect=fake_get_balances)
    adapter.get_ticker = AsyncMock(return_value={"trade_price": 70000})

    assert extract_available_cash("upbit", [{"currency": "KRW", "balance": "30000", "locked": "0"}]) == 30000.0
    assert extract_available_cash("kis", {"cash": 200000}) == 200000.0

    reports = asyncio.run(analyze_user_cash_sufficiency("u1", dm, om, adapter, now_ts=now_ts))
    by_ex = {r["exchange"]: r for r in reports}

    assert by_ex["upbit"]["status"] == "short_next"
    assert by_ex["upbit"]["shortfall_next_krw"] == 70000
    assert by_ex["upbit"]["shortfall_weekly_krw"] == 670000
    assert "70,000원" in by_ex["upbit"]["guide_message"]

    assert by_ex["kis"]["status"] == "ok"
    assert by_ex["kis"]["shortfall_next_krw"] == 0

    section_html = format_cash_health_section(reports, html=True)
    assert "계좌 예수금" in section_html
    assert "채워주세요" in section_html

    # /status 대시보드에도 예수금 가이드와 DCA 스케줄이 표시되는지 검증
    status_msg, _ = list_view_handlers.build_status_message(
        [], False, dca_schedules=dm.get_user_schedules("u1"), cash_reports=reports
    )
    assert "KRW-BTC" in status_msg
    assert "#1" in status_msg
    assert "채워주세요" in status_msg

    # 일일 알림 발송 및 당일 중복 방지 검증
    _daily_cash_alert_sent.clear()
    _cash_last_checked_ts.clear()
    um = MagicMock()
    um.get_user.return_value = {"is_active": True}
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    sent1 = asyncio.run(check_daily_cash_alerts(app, dm, om, adapter, um, now_ts=now_ts))
    assert sent1 == 1
    assert app.bot.send_message.await_count == 1

    # 같은 날 다시 호출하면 중복 발송되지 않아야 함
    sent2 = asyncio.run(check_daily_cash_alerts(app, dm, om, adapter, um, now_ts=now_ts + 600))
    assert sent2 == 0
    assert app.bot.send_message.await_count == 1
