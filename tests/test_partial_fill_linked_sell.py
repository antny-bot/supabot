import inspect
from unittest.mock import AsyncMock, MagicMock
import pytest

from core.order_manager import OrderManager
from core.user_manager import UserManager
from core.order_execution import _execute_order_batch


def _sync_run(coro):
    """Windows 샌드박스 Proactor loopback 소켓 블로킹 방지용 경량 동기 코루틴 러너."""
    stack = [coro]
    val = None
    while stack:
        top = stack[-1]
        try:
            nxt = top.send(val)
            val = None
            if inspect.iscoroutine(nxt) or hasattr(nxt, "__await__"):
                if hasattr(nxt, "__await__"):
                    nxt = nxt.__await__()
                stack.append(nxt)
            else:
                val = nxt
        except StopIteration as e:
            stack.pop()
            val = e.value
    return val


@pytest.fixture
def clean_om(tmp_path):
    return OrderManager(str(tmp_path / "orders.json"))


def test_order_manager_crud_and_indexing(clean_om):
    om = clean_om
    # 1. Add order
    om.add_order("u1", "upbit", "KRW-BTC", "ord-1", 50000, 1.5, side="bid", strategy="rsitrade")
    assert om.has_order("ord-1")
    assert om.get_order("ord-1")["price"] == 50000
    assert om.get_order("ord-1")["volume"] == 1.5

    # 2. Update order using generic helper
    ok = om.update_order("ord-1", filled_volume=0.5, status="partial")
    assert ok
    assert om.get_order("ord-1")["filled_volume"] == 0.5
    assert om.get_order("ord-1")["status"] == "partial"

    # 3. Replace UUID
    ok = om.replace_order_uuid("ord-1", "ord-2")
    assert ok
    assert not om.has_order("ord-1")
    assert om.has_order("ord-2")
    assert om.get_order("ord-2")["reorder_of"] == "ord-1"

    # 4. Remove order
    removed = om.remove_order("ord-2")
    assert removed
    assert not om.has_order("ord-2")
    assert om.get_order("ord-2") is None


def test_linked_sell_multiple_partial_fills(tmp_path, monkeypatch):
    import main as main_mod

    om = OrderManager(str(tmp_path / "orders.json"))
    monkeypatch.setattr(main_mod, "order_manager", om)

    # Setup mocks
    bot = MagicMock()
    bot.send_message = AsyncMock()
    app = MagicMock()
    app.bot = bot

    adapter = MagicMock()
    adapter.create_order = AsyncMock(side_effect=[{"uuid": "sell-1"}, {"uuid": "sell-2"}])
    ex_mock = MagicMock()
    ex_mock.round_volume = lambda v: float(v)
    ex_mock.requires_integer_volume = lambda: False
    ex_mock.adjust_price_to_tick = lambda p, t=None: float(p)
    adapter.get_exchange = lambda e: ex_mock
    monkeypatch.setattr(main_mod, "exchange_adapter", adapter)

    sig_engine = MagicMock()
    sig_engine.get_price_by_rsi = AsyncMock(return_value=60000.0)
    monkeypatch.setattr(main_mod, "signal_engine", sig_engine)

    # Mock user_manager
    monkeypatch.setattr(main_mod.user_manager, "get_user", lambda uid: {"preferences": UserManager.DEFAULT_PREFERENCES})

    # Initial Buy Order: 10 units total
    buy_uuid = "buy-order-100"
    om.add_order("u1", "upbit", "KRW-BTC", buy_uuid, 50000.0, 10.0, side="bid", strategy="rsitrade", linked_to="70")

    buy_ord = om.get_order(buy_uuid)

    # Step 1: First partial fill of 3 units
    res1 = _sync_run(main_mod._create_linked_sell_order(app, buy_ord, exec_vol=3.0, state="wait"))
    assert res1 == "created"
    assert adapter.create_order.call_count == 1
    # Check sell order 1 created with volume 3.0
    sells = main_mod._find_linked_sell_orders(buy_uuid)
    assert len(sells) == 1
    assert sells[0]["uuid"] == "sell-1"
    assert sells[0]["volume"] == 3.0
    assert om.get_order(buy_uuid)["filled_volume"] == 3.0

    # Step 2: Second partial fill of additional 7 units (total 10 units)
    res2 = _sync_run(main_mod._create_linked_sell_order(app, buy_ord, exec_vol=10.0, state="done"))
    assert res2 == "created"
    assert adapter.create_order.call_count == 2
    # Check sell order 2 created with volume 7.0 (needed_sell_vol = 10.0 - 3.0)
    sells = main_mod._find_linked_sell_orders(buy_uuid)
    assert len(sells) == 2
    assert sells[1]["uuid"] == "sell-2"
    assert sells[1]["volume"] == 7.0
    assert om.get_order(buy_uuid)["filled_volume"] == 10.0

    # Step 3: Crash recovery / duplicate call (exec_vol=10.0 again)
    res3 = _sync_run(main_mod._create_linked_sell_order(app, buy_ord, exec_vol=10.0, state="done"))
    assert res3 == "exists"
    assert adapter.create_order.call_count == 2  # No extra order placed! Idempotent!


def test_orphan_order_rollback_failure_alert(clean_om, monkeypatch):
    import core.order_execution as oe
    monkeypatch.setattr(oe, "ORDER_PLACEMENT_SLEEP_SECONDS", 0)
    om = clean_om
    bot = MagicMock()
    bot.send_message = AsyncMock()

    adapter = MagicMock()
    adapter.create_order = AsyncMock(return_value={"uuid": "exchange-order-999"})
    adapter.cancel_order = AsyncMock(return_value=False)  # Rollback fails!

    # Simulate add_order throwing exception
    om.add_order = MagicMock(side_effect=RuntimeError("DB disk full"))

    leg_fn = AsyncMock(return_value={"price": 100, "volume": 1, "side": "bid", "strategy": "grid"})
    log = MagicMock()

    success, skipped = _sync_run(_execute_order_batch(
        exchange_adapter=adapter,
        order_manager=om,
        user_id="user-1",
        exchange="upbit",
        ticker="KRW-BTC",
        group_no=1,
        count=1,
        leg_fn=leg_fn,
        is_reserved=False,
        log=log,
        bot=bot,
        notify_chat_id="user-1",
    ))

    assert success == 0
    # Telegram alert must be sent on orphan order rollback failure
    bot.send_message.assert_awaited_once()
    msg_text = bot.send_message.call_args.kwargs["text"]
    assert "고아 주문 발생" in msg_text
    assert "exchange-order-999" in msg_text
