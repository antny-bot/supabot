import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.order_manager import OrderManager
from core.user_manager import UserManager
from core.order_execution import (
    execute_grid_orders,
    execute_rsitrade_orders,
    execute_sgridrsi_orders,
)


def _order_manager(tmp_path):
    return OrderManager(str(tmp_path / "orders.json"))


def _bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _user(preferences=None):
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    if preferences:
        prefs.update(preferences)
    return {"is_active": True, "preferences": prefs, "exchanges": {}, "llm": {"gemini_api_key": ""}}


# ---- execute_grid_orders ----

async def test_execute_grid_orders_buy_path_uses_buy_limit_order(tmp_path):
    om = _order_manager(tmp_path)
    adapter = MagicMock()
    adapter.buy_limit_order = AsyncMock(side_effect=[{"uuid": f"u{i}"} for i in range(3)])
    adapter.create_order = AsyncMock()
    bot = _bot()
    sync_fn = AsyncMock()

    result = await execute_grid_orders(
        exchange_adapter=adapter, order_manager=om,
        user_id="111", exchange="upbit", ticker="KRW-BTC",
        start_price=100.0, end_price=200.0, count=3, budget_or_volume=300000,
        is_sell=False, group_no=7, bot=bot, notify_chat_id="111",
        trigger_sync_fn=sync_fn,
    )

    assert adapter.buy_limit_order.await_count == 3
    assert adapter.create_order.await_count == 0
    assert result["success_count"] == 3
    assert result["group_no"] == 7
    orders = om.get_user_orders("111")
    assert len(orders) == 3
    assert all(o["side"] == "bid" and o["strategy"] == "grid" and o["group_no"] == 7 for o in orders)
    bot.send_message.assert_awaited_once()
    msg = bot.send_message.call_args.kwargs["text"]
    assert "배치 #7" in msg
    sync_fn.assert_called_once()


async def test_execute_grid_orders_sell_path_uses_create_order(tmp_path):
    om = _order_manager(tmp_path)
    adapter = MagicMock()
    adapter.create_order = AsyncMock(return_value={"uuid": "sell-1"})
    adapter.buy_limit_order = AsyncMock()
    bot = _bot()

    result = await execute_grid_orders(
        exchange_adapter=adapter, order_manager=om,
        user_id="111", exchange="upbit", ticker="KRW-BTC",
        start_price=100.0, end_price=100.0, count=1, budget_or_volume=1.0,
        is_sell=True, group_no=9, bot=bot, notify_chat_id="111",
    )

    adapter.create_order.assert_awaited_once()
    assert adapter.create_order.call_args.args[3] == "ask"
    assert adapter.buy_limit_order.await_count == 0
    orders = om.get_user_orders("111")
    assert orders[0]["side"] == "ask" and orders[0]["strategy"] == "sgrid"
    assert result["success_count"] == 1


async def test_execute_grid_orders_kis_zero_volume_is_skipped_without_placing_order(tmp_path):
    om = _order_manager(tmp_path)
    adapter = MagicMock()
    adapter.buy_limit_order = AsyncMock(return_value={"uuid": "should-not-be-called"})
    bot = _bot()

    result = await execute_grid_orders(
        exchange_adapter=adapter, order_manager=om,
        user_id="111", exchange="kis", ticker="005930",
        start_price=1_000_000.0, end_price=1_000_000.0, count=1, budget_or_volume=10.0,
        is_sell=False, group_no=1, bot=bot, notify_chat_id="111",
    )

    # volume rounds down to 0 for KIS -> must be skipped WITHOUT calling the exchange
    adapter.buy_limit_order.assert_not_awaited()
    assert result["skipped_count"] == 1
    assert result["success_count"] == 0
    assert om.get_user_orders("111") == []
    msg = bot.send_message.call_args.kwargs["text"]
    assert "건너뜀" in msg


async def test_execute_grid_orders_continues_after_exchange_exception(tmp_path):
    om = _order_manager(tmp_path)
    adapter = MagicMock()
    adapter.buy_limit_order = AsyncMock(side_effect=[Exception("boom"), {"uuid": "u2"}])
    bot = _bot()

    result = await execute_grid_orders(
        exchange_adapter=adapter, order_manager=om,
        user_id="111", exchange="upbit", ticker="KRW-BTC",
        start_price=100.0, end_price=200.0, count=2, budget_or_volume=200000,
        is_sell=False, group_no=2, bot=bot, notify_chat_id="111",
    )

    assert adapter.buy_limit_order.await_count == 2
    assert result["success_count"] == 1
    assert len(om.get_user_orders("111")) == 1


# ---- execute_rsitrade_orders ----

async def test_execute_rsitrade_orders_places_linked_buy_orders(tmp_path):
    om = _order_manager(tmp_path)
    adapter = MagicMock()
    adapter.create_order = AsyncMock(side_effect=[{"uuid": "b1"}, {"uuid": "b2"}])
    engine = MagicMock()
    engine.get_price_by_rsi = AsyncMock(side_effect=[1000.0, 2000.0])
    bot = _bot()
    sync_fn = AsyncMock()

    result = await execute_rsitrade_orders(
        exchange_adapter=adapter, order_manager=om, signal_engine=engine,
        user_id="111", exchange="upbit", ticker="KRW-BTC",
        buy_rsi_range="25-30", sell_rsi_range="65-75",
        count=2, per_order_budgets=[100000.0, 100000.0],
        user=_user(), group_no=3, bot=bot, notify_chat_id="111",
        trigger_sync_fn=sync_fn,
    )

    assert adapter.create_order.await_count == 2
    assert adapter.create_order.call_args_list[0].args[3] == "bid"
    orders = om.get_user_orders("111")
    assert len(orders) == 2
    assert all(o["strategy"] == "rsitrade" and o["group_no"] == 3 for o in orders)
    assert all(o["linked_to"] is not None for o in orders)  # sell_rsi_range present -> linked
    assert result["success"] == 2
    sync_fn.assert_called_once()


async def test_execute_rsitrade_orders_buy_only_has_no_linked_to(tmp_path):
    om = _order_manager(tmp_path)
    adapter = MagicMock()
    adapter.create_order = AsyncMock(return_value={"uuid": "b1"})
    engine = MagicMock()
    engine.get_price_by_rsi = AsyncMock(return_value=1000.0)
    bot = _bot()

    await execute_rsitrade_orders(
        exchange_adapter=adapter, order_manager=om, signal_engine=engine,
        user_id="111", exchange="upbit", ticker="KRW-BTC",
        buy_rsi_range="25-30", sell_rsi_range="-",
        count=1, per_order_budgets=[100000.0],
        user=_user(), group_no=4, bot=bot, notify_chat_id="111",
    )

    orders = om.get_user_orders("111")
    assert orders[0]["linked_to"] is None


async def test_execute_rsitrade_orders_kis_rounds_to_int_and_skips_zero(tmp_path):
    om = _order_manager(tmp_path)
    adapter = MagicMock()
    adapter.create_order = AsyncMock(return_value={"uuid": "b1"})
    engine = MagicMock()
    # price too high -> rounded volume becomes 0 for KIS and must be skipped
    engine.get_price_by_rsi = AsyncMock(return_value=10_000_000.0)
    bot = _bot()

    result = await execute_rsitrade_orders(
        exchange_adapter=adapter, order_manager=om, signal_engine=engine,
        user_id="111", exchange="kis", ticker="005930",
        buy_rsi_range="25-30", sell_rsi_range="-",
        count=1, per_order_budgets=[100000.0],
        user=_user(), group_no=5, bot=bot, notify_chat_id="111",
    )

    adapter.create_order.assert_not_awaited()
    assert result["success"] == 0
    assert om.get_user_orders("111") == []


async def test_execute_rsitrade_orders_skips_when_no_price_available(tmp_path):
    om = _order_manager(tmp_path)
    adapter = MagicMock()
    adapter.create_order = AsyncMock()
    engine = MagicMock()
    engine.get_price_by_rsi = AsyncMock(return_value=None)
    bot = _bot()

    result = await execute_rsitrade_orders(
        exchange_adapter=adapter, order_manager=om, signal_engine=engine,
        user_id="111", exchange="upbit", ticker="KRW-BTC",
        buy_rsi_range="25-30", sell_rsi_range="-",
        count=1, per_order_budgets=[100000.0],
        user=_user(), group_no=6, bot=bot, notify_chat_id="111",
    )

    adapter.create_order.assert_not_awaited()
    assert result["success"] == 0


# ---- execute_sgridrsi_orders ----

async def test_execute_sgridrsi_orders_places_sell_orders_without_linked_to(tmp_path):
    om = _order_manager(tmp_path)
    adapter = MagicMock()
    adapter.create_order = AsyncMock(return_value={"uuid": "s1"})
    engine = MagicMock()
    engine.get_price_by_rsi = AsyncMock(return_value=1000.0)
    bot = _bot()
    sync_fn = AsyncMock()

    result = await execute_sgridrsi_orders(
        exchange_adapter=adapter, order_manager=om, signal_engine=engine,
        user_id="111", exchange="upbit", ticker="KRW-BTC",
        sell_rsi_range="65-75", count=1, budget=100000.0,
        user=_user(), group_no=8, bot=bot, notify_chat_id="111",
        trigger_sync_fn=sync_fn,
    )

    assert adapter.create_order.call_args.args[3] == "ask"
    orders = om.get_user_orders("111")
    assert orders[0]["strategy"] == "sgridrsi"
    assert orders[0]["linked_to"] is None
    assert orders[0]["side"] == "ask"
    assert result["success"] == 1
    msg = bot.send_message.call_args.kwargs["text"]
    assert "배치 #8" in msg
    sync_fn.assert_called_once()
