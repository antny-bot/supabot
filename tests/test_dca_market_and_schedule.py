import os
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
import pytest

from core.parsers import KST
from core.dca_manager import (
    DcaManager,
    parse_dca_schedule,
    compute_next_run_at,
    _compute_dca_limit_price,
    _DCA_SIDECAR_RETRY_SECONDS,
    _DCA_MAX_SIDECAR_RETRIES,
    _DCA_RETRY_DELAY_SECONDS,
    execute_due_dca_schedules,
    _dca_fail_counts,
)
from core.order_manager import OrderManager


def test_parse_dca_schedule_weekdays_and_ranges():
    # 1. 매일 / 월~일
    res_daily = parse_dca_schedule("매일")
    assert res_daily["frequency"] == "daily"
    assert res_daily["days_of_week"] is None

    res_all_days = parse_dca_schedule("월~일")
    assert res_all_days["frequency"] == "daily"
    assert res_all_days["days_of_week"] is None

    # 2. 평일 / 월~금
    res_weekdays = parse_dca_schedule("월~금")
    assert res_weekdays["frequency"] == "days"
    assert res_weekdays["days_of_week"] == [0, 1, 2, 3, 4]

    res_weekdays_txt = parse_dca_schedule("평일")
    assert res_weekdays_txt["frequency"] == "days"
    assert res_weekdays_txt["days_of_week"] == [0, 1, 2, 3, 4]

    # 3. 특정 요일 조합 (월/수/금, 월,수,금, 월 수 금)
    res_mwf1 = parse_dca_schedule("월,수,금")
    assert res_mwf1["frequency"] == "days"
    assert res_mwf1["days_of_week"] == [0, 2, 4]

    res_mwf2 = parse_dca_schedule("월/수/금")
    assert res_mwf2["days_of_week"] == [0, 2, 4]

    res_mwf3 = parse_dca_schedule("월 수 금")
    assert res_mwf3["days_of_week"] == [0, 2, 4]

    # 4. 단일 요일 (금, 금요일)
    res_fri = parse_dca_schedule("금")
    assert res_fri["frequency"] == "weekly"
    assert res_fri["days_of_week"] == [4]

    res_fri_yoil = parse_dca_schedule("금요일")
    assert res_fri_yoil["frequency"] == "weekly"
    assert res_fri_yoil["days_of_week"] == [4]

    # 5. 주말
    res_weekend = parse_dca_schedule("토,일")
    assert res_weekend["days_of_week"] == [5, 6]

    # 6. 부분 범위 (월~목)
    res_mon_thu = parse_dca_schedule("월~목")
    assert res_mon_thu["frequency"] == "days"
    assert res_mon_thu["days_of_week"] == [0, 1, 2, 3]


def test_parse_dca_schedule_sunday_and_invalid_tokens():
    # 1. 일, 일요일
    res_sun1 = parse_dca_schedule("일")
    assert res_sun1["frequency"] == "weekly"
    assert res_sun1["days_of_week"] == [6]

    res_sun2 = parse_dca_schedule("일요일")
    assert res_sun2["frequency"] == "weekly"
    assert res_sun2["days_of_week"] == [6]

    # 2. 화~일, 수-일, 월~일
    res_tue_sun = parse_dca_schedule("화~일")
    assert res_tue_sun["frequency"] == "days"
    assert res_tue_sun["days_of_week"] == [1, 2, 3, 4, 5, 6]

    res_wed_sun = parse_dca_schedule("수-일")
    assert res_wed_sun["frequency"] == "days"
    assert res_wed_sun["days_of_week"] == [2, 3, 4, 5, 6]

    res_mon_sun = parse_dca_schedule("월~일")
    assert res_mon_sun["frequency"] == "daily"
    assert res_mon_sun["days_of_week"] is None

    # 3. 토,일요일
    res_sat_sun = parse_dca_schedule("토,일요일")
    assert res_sat_sun["frequency"] == "days"
    assert res_sat_sun["days_of_week"] == [5, 6]

    # 4. 월수금
    res_mwf = parse_dca_schedule("월수금")
    assert res_mwf["frequency"] == "days"
    assert res_mwf["days_of_week"] == [0, 2, 4]

    # 5. 잘못된 토큰 (KeyError가 아닌 ValueError 발생 확인)
    with pytest.raises(ValueError, match="알 수 없는 요일"):
        parse_dca_schedule("화~똠")

    with pytest.raises(ValueError, match="알 수 없는 요일"):
        parse_dca_schedule("월,똠,금")

    with pytest.raises(ValueError):
        parse_dca_schedule("invalid_token_123")


def test_compute_next_run_at_specific_days():
    # 2026-11-09는 월요일
    base_dt = datetime(2026, 11, 9, 8, 0, tzinfo=KST)
    base_ts = base_dt.timestamp()

    # 월/수/금 09:05 -> 오늘이 월요일 08:00이므로 오늘 09:05가 다음 실행
    next_ts = compute_next_run_at("days", "09:05", days_of_week=[0, 2, 4], now=base_ts)
    next_dt = datetime.fromtimestamp(next_ts, tz=KST)
    assert next_dt.weekday() == 0
    assert next_dt.hour == 9
    assert next_dt.minute == 5

    # 월요일 10:00(이미 지남) -> 다음은 수요일(2) 09:05
    past_mon = datetime(2026, 11, 9, 10, 0, tzinfo=KST).timestamp()
    next_ts_wed = compute_next_run_at("days", "09:05", days_of_week=[0, 2, 4], now=past_mon)
    next_dt_wed = datetime.fromtimestamp(next_ts_wed, tz=KST)
    assert next_dt_wed.weekday() == 2
    assert next_dt_wed.hour == 9
    assert next_dt_wed.minute == 5

    # 금요일 10:00(이미 지남) -> 다음은 다음 주 월요일(0) 09:05
    past_fri = datetime(2026, 11, 13, 10, 0, tzinfo=KST).timestamp()
    next_ts_mon = compute_next_run_at("days", "09:05", days_of_week=[0, 2, 4], now=past_fri)
    next_dt_mon = datetime.fromtimestamp(next_ts_mon, tz=KST)
    assert next_dt_mon.weekday() == 0
    assert next_dt_mon.hour == 9
    assert next_dt_mon.minute == 5


def test_dca_manager_add_schedule_with_order_type_and_carryover(tmp_path, monkeypatch):
    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: False)
    dca_file = tmp_path / "dca_test.json"
    mgr = DcaManager(file_path=str(dca_file))

    sched = mgr.add_schedule(
        user_id="test_user",
        exchange="upbit",
        ticker="BTC",
        side="bid",
        frequency="days",
        days_of_week=[0, 2, 4],
        amount_type="budget",
        amount=50000,
        exec_time="09:05",
        order_type="market",
        carryover_mode="delay_20m",
    )

    assert sched["order_type"] == "market"
    assert sched["carryover_mode"] == "delay_20m"
    assert sched["days_of_week"] == [0, 2, 4]

    # JSON 저장 확인
    loaded_mgr = DcaManager(file_path=str(dca_file))
    assert len(loaded_mgr.schedules) == 1
    assert loaded_mgr.schedules[0]["order_type"] == "market"
    assert loaded_mgr.schedules[0]["carryover_mode"] == "delay_20m"


def test_dca_manager_defer_and_advance_carryover(tmp_path, monkeypatch):
    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: False)
    dca_file = tmp_path / "dca_defer_test.json"
    mgr = DcaManager(file_path=str(dca_file))

    now_ts = datetime(2026, 11, 9, 9, 5, 0, tzinfo=KST).timestamp()
    sched = mgr.add_schedule(
        user_id="u1",
        exchange="kis",
        ticker="005930",
        side="bid",
        frequency="days",
        days_of_week=[0, 2, 4],
        amount_type="volume",
        amount=1,
        order_type="market",
        carryover_mode="delay_20m",
        now=now_ts,
    )

    sched_id = sched["id"]

    # 사이드카 또는 휴장 시 20분 연기 테스트
    retry_ts = now_ts + _DCA_SIDECAR_RETRY_SECONDS
    ok = mgr.defer_schedule(sched_id, retry_ts)
    assert ok is True
    updated = mgr.get_schedule(sched_id)
    assert updated["next_run_at"] == retry_ts

    # 이월 후 실행 완료 시 다음 정규 주기(수요일)로 advance 테스트
    advanced = mgr.advance_schedule(sched_id, now_ts=retry_ts, increment_run=True)
    assert advanced["run_count"] == 1
    next_dt = datetime.fromtimestamp(advanced["next_run_at"], tz=KST)
    # 다음 회차는 수요일(2) 09:05
    assert next_dt.weekday() == 2
    assert next_dt.hour == 9
    assert next_dt.minute == 5


def test_compute_dca_limit_price_behavior():
    ex_obj = MagicMock()
    ex_obj.adjust_price_to_tick.side_effect = lambda p, t=None: round(p, -2)

    # 매수 시 현재가보다 0.1% 높여 호가 버퍼 적용
    bid_price = _compute_dca_limit_price(ex_obj, "upbit", "BTC", "bid", 50000000, None)
    assert bid_price >= 50000000

    # 매도 시 현재가보다 0.1% 낮춰 안전 호가 적용
    ask_price = _compute_dca_limit_price(ex_obj, "upbit", "BTC", "ask", 50000000, None)
    assert ask_price <= 50000000


def test_dca_execute_upbit_volume_market_buy_no_name_error(tmp_path, monkeypatch):
    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.order_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.trading_gate.is_trading_halted", lambda: False)
    monkeypatch.setattr("core.trading_gate.check_can_place_order", lambda *a, **kw: (True, ""))

    dca_file = tmp_path / "dca_vol_market.json"
    order_file = tmp_path / "orders.json"
    dm = DcaManager(file_path=str(dca_file))
    om = OrderManager(file_path=str(order_file))

    now_ts = datetime(2026, 11, 9, 9, 5, 0, tzinfo=KST).timestamp()
    sched = dm.add_schedule(
        user_id="user1",
        exchange="upbit",
        ticker="KRW-BTC",
        side="bid",
        frequency="daily",
        amount_type="volume",
        amount=0.001,
        order_type="market",
        now=now_ts,
    )
    dm.defer_schedule(sched["id"], now_ts)

    ex_obj = MagicMock()
    ex_obj.is_market_open.return_value = True
    ex_obj.is_order_placement_allowed.return_value = True
    ex_obj.adjust_price_to_tick.side_effect = lambda p, t=None: round(p, -3)
    ex_obj.round_volume.side_effect = lambda v: round(v, 8)
    ex_obj.requires_integer_volume.return_value = False

    adapter = MagicMock()
    adapter.get_exchange.return_value = ex_obj
    current_price = 100_000_000
    adapter.get_ticker = AsyncMock(return_value={"trade_price": current_price})
    adapter.get_min_order_amount.return_value = 5000
    adapter.create_order = AsyncMock(return_value={"uuid": "upbit-mkt-order-1"})

    um = MagicMock()
    um.get_user.return_value = {"is_active": True, "preferences": {}}

    app = MagicMock()
    app.bot.send_message = AsyncMock()

    async def _run():
        return await execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=now_ts)

    executed = asyncio.run(_run())
    assert executed == 1
    # upbit 시장가 매수는 ord_price = effective_budget (0.001 * 100,000,000 = 100,000원), volume = 0, ord_type = 'market'
    adapter.create_order.assert_called_once_with(
        "user1", "upbit", "KRW-BTC", "bid", 100_000.0, 0, ord_type="market"
    )
    assert len(om.orders) == 1
    assert om.orders[0]["uuid"] == "upbit-mkt-order-1"


def test_dca_sidecar_and_regular_error_handling(tmp_path, monkeypatch):
    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.order_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.trading_gate.is_trading_halted", lambda: False)
    monkeypatch.setattr("core.trading_gate.check_can_place_order", lambda *a, **kw: (True, ""))

    dca_file = tmp_path / "dca_err_test.json"
    order_file = tmp_path / "orders.json"
    dm = DcaManager(file_path=str(dca_file))
    om = OrderManager(file_path=str(order_file))

    now_ts = datetime(2026, 11, 9, 9, 5, 0, tzinfo=KST).timestamp()
    sched = dm.add_schedule(
        user_id="user1",
        exchange="upbit",
        ticker="KRW-BTC",
        side="bid",
        frequency="daily",
        amount_type="budget",
        amount=50000,
        now=now_ts,
    )
    sched_id = sched["id"]

    ex_obj = MagicMock()
    ex_obj.is_market_open.return_value = True
    ex_obj.is_order_placement_allowed.return_value = True
    ex_obj.adjust_price_to_tick.side_effect = lambda p, t=None: round(p, -3)
    ex_obj.round_volume.side_effect = lambda v: round(v, 8)
    ex_obj.requires_integer_volume.return_value = False

    adapter = MagicMock()
    adapter.get_exchange.return_value = ex_obj
    adapter.get_ticker = AsyncMock(return_value={"trade_price": 50000000})
    adapter.get_min_order_amount.return_value = 5000

    um = MagicMock()
    um.get_user.return_value = {"is_active": True, "preferences": {}}

    app = MagicMock()
    app.bot.send_message = AsyncMock()

    # 1. 일반 거부 에러 ("호가 단위 오류"): 사이드카로 오탐되지 않고 일반 실패 카운트 증가
    _dca_fail_counts.clear()
    adapter.create_order = AsyncMock(return_value={"error": "호가 단위 오류: 주문 가격을 확인하세요"})
    dm.defer_schedule(sched_id, now_ts)

    executed = asyncio.run(execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=now_ts))
    assert executed == 0
    assert _dca_fail_counts.get(sched_id) == 1
    sched_cur = dm.get_schedule(sched_id)
    assert not sched_cur.get("is_carryover")
    assert sched_cur["next_run_at"] == now_ts + _DCA_RETRY_DELAY_SECONDS

    # 2. 사이드카/서킷브레이커 에러: 이월 처리(20분 지연)되고 carryover_count 1 증가, 일반 실패 카운트는 증가하지 않음
    _dca_fail_counts.clear()
    adapter.create_order = AsyncMock(return_value={"error": "시장 사이드카 발동으로 인한 매매정지"})
    dm.defer_schedule(sched_id, now_ts)

    executed = asyncio.run(execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=now_ts))
    assert executed == 0
    sched_cur = dm.get_schedule(sched_id)
    assert sched_cur.get("is_carryover") is True
    assert sched_cur.get("carryover_reason") == "sidecar_halt"
    assert sched_cur.get("carryover_count") == 1
    assert _dca_fail_counts.get(sched_id, 0) == 0

    # 3. 사이드카 상한 초과: 12회 연속 거래정지 후 일반 실패 처리로 전환되는지 확인
    sched_cur["carryover_count"] = _DCA_MAX_SIDECAR_RETRIES
    dm.defer_schedule(sched_id, now_ts)

    executed = asyncio.run(execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=now_ts))
    assert executed == 0
    # 일반 실패 카운트가 1 증가해야 함
    assert _dca_fail_counts.get(sched_id) == 1
    sched_cur = dm.get_schedule(sched_id)
    # is_carryover 플래그 정리됨
    assert not sched_cur.get("is_carryover")
