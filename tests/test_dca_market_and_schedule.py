import os
from datetime import datetime
from unittest.mock import MagicMock
import pytest

from core.parsers import KST
from core.dca_manager import (
    DcaManager,
    parse_dca_schedule,
    compute_next_run_at,
    _compute_dca_limit_price,
    _DCA_SIDECAR_RETRY_SECONDS,
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
