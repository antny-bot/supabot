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


def test_dca_kill_switch_silent_defer_and_inactive_user(tmp_path, monkeypatch):
    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.order_manager.is_db_available", lambda: False)

    dca_file = tmp_path / "dca_ks_test.json"
    order_file = tmp_path / "orders_ks.json"
    dm = DcaManager(file_path=str(dca_file))
    om = OrderManager(file_path=str(order_file))

    now_ts = datetime(2026, 11, 9, 9, 5, 0, tzinfo=KST).timestamp()

    # 1. 비활성 유저 스케줄: 킬스위치 여부와 무관하게 즉시 스케줄 제거 및 무음 처리
    sched_inact = dm.add_schedule(
        user_id="inactive_user",
        exchange="upbit",
        ticker="KRW-BTC",
        side="bid",
        frequency="daily",
        amount_type="budget",
        amount=50000,
        now=now_ts,
    )
    dm.defer_schedule(sched_inact["id"], now_ts)

    um = MagicMock()
    um.get_user.side_effect = lambda uid: {"is_active": False} if uid == "inactive_user" else {"is_active": True}

    adapter = MagicMock()
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    executed = asyncio.run(execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=now_ts))
    assert executed == 0
    assert dm.get_schedule(sched_inact["id"]) is None
    assert app.bot.send_message.call_count == 0

    # 2. 활성 유저 + 킬스위치 ON: 알림 발송 없이 5분 무음 지연
    monkeypatch.setattr("core.trading_gate.is_trading_halted", lambda: True)
    sched_act = dm.add_schedule(
        user_id="active_user",
        exchange="upbit",
        ticker="KRW-BTC",
        side="bid",
        frequency="daily",
        amount_type="budget",
        amount=50000,
        now=now_ts,
    )
    dm.defer_schedule(sched_act["id"], now_ts)

    executed = asyncio.run(execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=now_ts))
    assert executed == 0
    assert app.bot.send_message.call_count == 0  # 무음 지연(알림 미발송)
    cur_sched = dm.get_schedule(sched_act["id"])
    assert cur_sched["next_run_at"] == now_ts + _DCA_RETRY_DELAY_SECONDS
    assert not cur_sched.get("is_carryover")


def test_dca_sidecar_notification_only_once(tmp_path, monkeypatch):
    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.order_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.trading_gate.is_trading_halted", lambda: False)
    monkeypatch.setattr("core.trading_gate.check_can_place_order", lambda *a, **kw: (True, ""))

    dca_file = tmp_path / "dca_sidecar_once.json"
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
    adapter.create_order = AsyncMock(return_value={"error": "시장 사이드카 발동으로 인한 거래정지"})

    um = MagicMock()
    um.get_user.return_value = {"is_active": True}
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    _dca_fail_counts.clear()

    # 1회차: 첫 이월 시작 시 알림 1회 발송
    dm.defer_schedule(sched_id, now_ts)
    asyncio.run(execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=now_ts))
    assert app.bot.send_message.call_count == 1
    assert dm.get_schedule(sched_id)["carryover_count"] == 1

    # 2회차 (20분 뒤 다시 사이드카 감지): 알림이 중복 발송되지 않고 call_count 여전히 1 유지
    dm.defer_schedule(sched_id, now_ts + 1200)
    asyncio.run(execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=now_ts + 1200))
    assert app.bot.send_message.call_count == 1
    assert dm.get_schedule(sched_id)["carryover_count"] == 2


def test_dca_template_budget_error_defers_schedule(tmp_path, monkeypatch):
    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.order_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.trading_gate.is_trading_halted", lambda: False)
    monkeypatch.setattr("core.trading_gate.check_can_place_order", lambda *a, **kw: (True, ""))

    dca_file = tmp_path / "dca_tpl_err.json"
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
        template_id=999,
        now=now_ts,
    )
    sched_id = sched["id"]
    dm.defer_schedule(sched_id, now_ts)

    # get_db().table("strategy_templates").select().eq().execute_async() 에서 예외 유발
    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_eq.execute_async = AsyncMock(side_effect=Exception("DB query timeout"))
    mock_select.eq.return_value = mock_eq
    mock_table.select.return_value = mock_select
    mock_table.upsert.return_value.execute_async = AsyncMock()
    mock_db.table.return_value = mock_table

    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: True)
    monkeypatch.setattr("core.dca_manager.get_db", lambda: mock_db)

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
    adapter.create_order = AsyncMock()

    um = MagicMock()
    um.get_user.return_value = {"is_active": True}
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    executed = asyncio.run(execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=now_ts))
    # 예산 조회 실패 시 전액 주문되지 않고 안전하게 보류되어야 함
    assert executed == 0
    assert adapter.create_order.call_count == 0
    cur_sched = dm.get_schedule(sched_id)
    assert cur_sched["next_run_at"] == now_ts + _DCA_RETRY_DELAY_SECONDS


def test_order_sync_volume_adjustment_for_dca_market(tmp_path, monkeypatch):
    monkeypatch.setattr("core.order_manager.is_db_available", lambda: False)

    order_file = tmp_path / "orders.json"
    om = OrderManager(file_path=str(order_file))
    om.add_order(
        user_id="u1",
        exchange="upbit",
        ticker="KRW-BTC",
        uuid="dca-mkt-uuid-1",
        price=100000000,
        volume=0.001,  # 발주 시점의 추정 수량
        side="bid",
        strategy="dca",
    )

    from core import order_sync
    monkeypatch.setattr(order_sync, "_get_app_context", lambda: (om, MagicMock(), MagicMock(), MagicMock()))
    monkeypatch.setattr(order_sync, "_call_append_trade", MagicMock())

    calls = []
    orig_update = om.update_order
    def spy_update(uuid, **fields):
        calls.append((uuid, fields))
        return orig_update(uuid, **fields)
    monkeypatch.setattr(om, "update_order", spy_update)

    ord_data = om.get_order("dca-mkt-uuid-1")
    # 실제 거래소 체결 수량: 0.00098765
    res = {
        "state": "done",
        "executed_volume": 0.00098765,
    }

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    ex_obj = MagicMock()

    asyncio.run(order_sync._process_order_fill(app, ord_data, res, ex_obj))

    # update_order가 실제 체결 수량으로 보정하여 호출되었는지 확인
    assert len(calls) == 1
    assert calls[0][0] == "dca-mkt-uuid-1"
    assert calls[0][1]["volume"] == 0.00098765
    assert calls[0][1]["filled_volume"] == 0.00098765
    assert calls[0][1]["status"] == "done"


def test_dca_manager_fallback_and_reload_preserves_order_type(tmp_path, monkeypatch):
    dca_file = tmp_path / "dca_save_test.json"
    dm = DcaManager(file_path=str(dca_file))

    sched = dm.add_schedule(
        user_id="u1",
        exchange="upbit",
        ticker="KRW-BTC",
        side="bid",
        frequency="daily",
        amount_type="budget",
        amount=50000,
        order_type="market",
        carryover_mode="delay_20m",
        template_id=123,
    )

    # 1. 파일에 order_type, carryover_mode, template_id가 저장되어 있는지 확인
    import json
    with open(str(dca_file), "r", encoding="utf-8") as f:
        saved_file = json.load(f)
    assert saved_file[0]["order_type"] == "market"
    assert saved_file[0]["carryover_mode"] == "delay_20m"
    assert saved_file[0]["template_id"] == 123

    # 2. DB에 해당 컬럼이 없는 구버전 스키마라 order_type 등의 키가 없이 반환되는 상황 모킹
    db_row_no_columns = {
        "id": sched["id"],
        "user_id": "u1",
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "side": "bid",
        "frequency": "daily",
        "amount_type": "budget",
        "amount": 50000,
        # order_type, carryover_mode, template_id 누락
    }

    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_select.execute.return_value = MagicMock(data=[db_row_no_columns])
    mock_table.select.return_value = mock_select
    mock_db.table.return_value = mock_table

    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: True)
    monkeypatch.setattr("core.dca_manager.get_db", lambda: mock_db)

    # _load_schedules 호출 시 로컬 파일의 원래 값이 복원/병합되는지 검증
    new_dm = DcaManager(file_path=str(dca_file))
    loaded_sched = new_dm.get_schedule(sched["id"])
    assert loaded_sched["order_type"] == "market"
    assert loaded_sched["carryover_mode"] == "delay_20m"
    assert loaded_sched["template_id"] == 123


def test_parse_dca_schedule_daily_single_branch():
    daily_tokens = ["매일", "매일마다", "daily", "every", "everyday", "1d", "월~일", "월-일", "월/일", "월~일요일"]
    for tok in daily_tokens:
        res = parse_dca_schedule(tok)
        assert res["frequency"] == "daily"
        assert res["days_of_week"] is None


def test_dca_delay_20m_mode_carryover_and_next_check_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr("core.dca_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.order_manager.is_db_available", lambda: False)
    monkeypatch.setattr("core.trading_gate.is_trading_halted", lambda: False)

    dca_file = tmp_path / "dca_delay20_test.json"
    order_file = tmp_path / "orders.json"
    dm = DcaManager(file_path=str(dca_file))
    om = OrderManager(file_path=str(order_file))

    now_ts = datetime(2026, 11, 9, 9, 5, 0, tzinfo=KST).timestamp()
    sched = dm.add_schedule(
        user_id="user1",
        exchange="kis",
        ticker="005930",
        side="bid",
        frequency="daily",
        amount_type="budget",
        amount=50000,
        carryover_mode="delay_20m",
        now=now_ts,
    )
    sched_id = sched["id"]
    dm.defer_schedule(sched_id, now_ts)

    ex_obj = MagicMock()
    # 거래소 휴장/장외 시간 상태
    ex_obj.is_market_open.return_value = False
    ex_obj.is_order_placement_allowed.return_value = False
    # 다음 개장 시각이 2시간 뒤 (now_ts + 7200초)
    next_open_ts = now_ts + 7200
    ex_obj.next_check_timestamp.return_value = next_open_ts

    adapter = MagicMock()
    adapter.get_exchange.return_value = ex_obj
    um = MagicMock()
    um.get_user.return_value = {"is_active": True}
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    # 1회차 실행: 20분(1200초) 대신 더 늦은 다음 개장 시각(7200초)으로 지연되어야 함
    executed = asyncio.run(execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=now_ts))
    assert executed == 0
    cur_sched = dm.get_schedule(sched_id)
    assert cur_sched["next_run_at"] == next_open_ts
    assert cur_sched["is_carryover"] is True
    assert cur_sched["carryover_reason"] == "delay_20m"
    assert app.bot.send_message.call_count == 1  # 첫 1회 안내 알림 확인

    # 2회차 실행: 이미 is_carryover인 경우 추가 알림 없이 지연만 갱신
    dm.defer_schedule(sched_id, next_open_ts)
    executed2 = asyncio.run(execute_due_dca_schedules(app, dm, adapter, om, um, now_ts=next_open_ts))
    assert executed2 == 0
    assert app.bot.send_message.call_count == 1  # 중복 알림 미발송 확인


@pytest.mark.asyncio
async def test_internal_api_dca_validation(monkeypatch):
    from unittest.mock import MagicMock
    import internal_api
    from internal_api import _internal_execute_dca_handler

    monkeypatch.setattr(internal_api, "_verify_webhook_request", AsyncMock(return_value=True))

    # 1. order_type 유효하지 않은 값 -> 400
    req_bad_order_type = MagicMock()
    req_bad_order_type.json = AsyncMock(return_value={
        "user_id": "u1",
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "side": "bid",
        "amount": 50000,
        "order_type": "invalid_mode_xyz",
    })
    res = await _internal_execute_dca_handler(req_bad_order_type)
    assert res.status == 400
    assert "유효하지 않은 주문 방식" in res.text

    # 2. carryover_mode 유효하지 않은 값 -> 400
    req_bad_carry = MagicMock()
    req_bad_carry.json = AsyncMock(return_value={
        "user_id": "u1",
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "side": "bid",
        "amount": 50000,
        "order_type": "market",
        "carryover_mode": "invalid_carry_mode",
    })
    res2 = await _internal_execute_dca_handler(req_bad_carry)
    assert res2.status == 400
    assert "유효하지 않은 이월 옵션" in res2.text
