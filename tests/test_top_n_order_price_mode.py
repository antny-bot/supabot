"""TOP N 예약주문 제출 시점 호가 방식(order_price_mode) 적용 테스트. 거래소 API는 전부 mock."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from core import order_sync
from core.order_sync import compute_top_n_order_plan, _shift_krx_ticks


def test_shift_krx_ticks_basic():
    assert _shift_krx_ticks(100000, 2) == 100200   # 100원 단위 구간
    assert _shift_krx_ticks(100000, -2) == 99800
    assert _shift_krx_ticks(1000, 2) == 1002        # 1원 단위 구간


def test_shift_krx_ticks_boundary_down():
    # 50000원 경계: 아래 구간은 50원 단위
    assert _shift_krx_ticks(50000, -2) == 49900


def test_plan_limit_current_uses_current_not_stored():
    t, p = compute_top_n_order_plan("limit_current", "bid", 100150, 90000)
    assert (t, p) == ("limit", 100100.0)


def test_plan_aggressive_bid_and_ask():
    assert compute_top_n_order_plan("limit_aggressive", "bid", 100000, 90000) == ("limit", 100200.0)
    assert compute_top_n_order_plan("limit_aggressive", "ask", 100000, 90000) == ("limit", 99800.0)


def test_plan_aggressive_clamped_to_limits():
    t, p = compute_top_n_order_plan("limit_aggressive", "bid", 100000, 0, upper_limit=100100)
    assert p == 100100.0
    t, p = compute_top_n_order_plan("limit_aggressive", "ask", 100000, 0, lower_limit=99900)
    assert p == 99900.0


def test_plan_market():
    assert compute_top_n_order_plan("market", "bid", 100000, 90000) == ("market", 100000.0)


def test_plan_no_current_price_falls_back_to_stored_limit():
    assert compute_top_n_order_plan("market", "bid", 0, 90000) == ("limit", 90000.0)


def _run_submit(monkeypatch, mode, ticker_price):
    om = MagicMock()
    ex_adapter = MagicMock()
    ex_adapter.get_open_orders = AsyncMock(return_value=[])
    ex_adapter.create_order = AsyncMock(return_value={"uuid": "new-1"})
    monkeypatch.setattr(order_sync, "_get_app_context", lambda: (om, MagicMock(), ex_adapter, MagicMock()))
    monkeypatch.setattr(order_sync.trading_gate, "is_trading_halted", lambda: False)
    monkeypatch.setattr(order_sync, "_get_template_order_price_mode", AsyncMock(return_value=mode))
    monkeypatch.setattr(order_sync, "_get_limit_warned_orders", lambda: {})
    monkeypatch.setattr(order_sync, "_get_reorder_failures", lambda: {})
    try:
        from core import db
        monkeypatch.setattr(db, "is_db_available", lambda: False)
    except Exception:
        pass

    ex_obj = MagicMock()
    ex_obj.supports_reserved_orders = True
    ex_obj.is_order_placement_allowed = lambda t: True
    ex_obj.requires_integer_volume = lambda: True
    ex_obj.is_us_stock = lambda t: False
    ex_obj.get_ticker = AsyncMock(return_value={"trade_price": ticker_price})

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    ord_ = {
        "uuid": "reserved:abc", "user_id": "u1", "exchange": "toss", "ticker": "005930",
        "side": "bid", "price": 90000.0, "volume": 1.0, "filled_volume": 0.0,
        "status": "reserved", "strategy": "kospi_top_dca", "template_id": 8,
    }
    ok = asyncio.run(order_sync._submit_reserved_or_reorder(app, ord_, ex_obj, ticker_cache={}))
    return ok, ex_adapter, om, ord_


def test_submit_reserved_market_mode_sends_market_order(monkeypatch):
    ok, ex, om, ord_ = _run_submit(monkeypatch, "market", 100000)
    assert ok
    args, kwargs = ex.create_order.call_args
    assert kwargs.get("ord_type") == "market"
    om.replace_order_uuid.assert_called_once_with("reserved:abc", "new-1")
    assert ord_["order_type"] == "market"


def test_submit_reserved_aggressive_uses_live_price(monkeypatch):
    ok, ex, om, ord_ = _run_submit(monkeypatch, "limit_aggressive", 100000)
    assert ok
    args, kwargs = ex.create_order.call_args
    assert args[4] == 100200.0           # price (낡은 90000이 아님)
    assert "ord_type" not in kwargs
    assert ord_["price"] == 100200.0
