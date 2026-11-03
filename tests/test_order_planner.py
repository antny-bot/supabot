"""order_planner.py 단위 테스트 (test_order_planner.py)."""
import pytest
from manager.backend.services.order_planner import (
    get_tick_size,
    adjust_price_to_tick,
    round_volume,
    plan_grid_orders,
    plan_rsitrade_orders,
)


def test_tick_size_and_volume_rounding():
    # 주식 호가 단위
    assert get_tick_size(70000, "kis") == 100
    assert get_tick_size(15000, "toss") == 10
    assert adjust_price_to_tick(70088, "kis") == 70000.0

    # 코인 호가 단위
    assert get_tick_size(50000000, "upbit") == 1000
    assert adjust_price_to_tick(50000550, "upbit") == 50000000.0

    # 주식은 정수 수량, 코인은 소수 4자리
    assert round_volume(10.789, "kis") == 10.0
    assert round_volume(0.123456, "upbit") == 0.1235


def test_plan_grid_orders_kr_stock():
    orders = plan_grid_orders(
        user_id="123",
        exchange="toss",
        ticker="005930",
        start_price=60000.0,
        end_price=70000.0,
        count=3,
        budget_or_volume=300000.0,
        is_sell=False,
        group_no=10,
        template_id=99,
    )
    assert len(orders) == 3
    # 가격: 60000, 65000, 70000
    assert orders[0]["price"] == 60000.0
    assert orders[1]["price"] == 65000.0
    assert orders[2]["price"] == 70000.0
    # 모든 주문 status='reserved'
    for o in orders:
        assert o["status"] == "reserved"
        assert o["side"] == "bid"
        assert o["strategy"] == "grid"
        assert o["group_no"] == 10
        assert o["template_id"] == 99
        assert o["uuid"].startswith("reserved:")
        assert isinstance(o["volume"], float)
        assert o["volume"] > 0


def test_plan_grid_orders_crypto_sell():
    orders = plan_grid_orders(
        user_id="456",
        exchange="upbit",
        ticker="KRW-BTC",
        start_price=90000000.0,
        end_price=100000000.0,
        count=2,
        budget_or_volume=1.0,
        is_sell=True,
        group_no=11,
    )
    assert len(orders) == 2
    assert orders[0]["side"] == "ask"
    assert orders[0]["strategy"] == "sgrid"
    assert orders[0]["volume"] == 0.5
    assert orders[1]["volume"] == 0.5


def test_plan_rsitrade_orders():
    orders = plan_rsitrade_orders(
        user_id="789",
        exchange="kis",
        ticker="005930",
        start_rsi=25.0,
        end_rsi=35.0,
        count=3,
        total_budget=300000.0,
        current_price=70000.0,
        current_rsi=35.0,
        group_no=12,
    )
    assert len(orders) == 3
    for o in orders:
        assert o["status"] == "reserved"
        assert o["side"] == "bid"
        assert o["strategy"] == "rsitrade"
        assert "target_rsi" in o
        assert o["group_no"] == 12


def test_plan_orders_zero_budget():
    assert plan_grid_orders("u", "kis", "005930", 50000, 60000, 3, 0.0, False, 1) == []
    assert plan_rsitrade_orders("u", "kis", "005930", 25, 35, 3, 0.0, 70000, 30, 1) == []
