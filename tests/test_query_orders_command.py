import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import main
from handlers import query_handlers
from core.user_manager import UserManager


def _user(default_exchange="bithumb"):
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    prefs["default_exchange"] = default_exchange
    return {
        "is_active": True,
        "is_admin": False,
        "preferences": prefs,
        "exchanges": {},
        "llm": {"gemini_api_key": ""},
    }


def _patch_auth(monkeypatch, user):
    mock_um = MagicMock()
    mock_um.get_user = MagicMock(return_value=user)
    monkeypatch.setattr(main, "user_manager", mock_um)
    return mock_um


def _make_update(user_id=111):
    update = MagicMock()
    update.effective_chat.id = user_id
    update.message.reply_text = AsyncMock()
    return update


def _make_context(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


async def test_orders_command_without_args_shows_all_user_orders_across_exchanges(monkeypatch):
    _patch_auth(monkeypatch, _user(default_exchange="bithumb"))

    mock_om = MagicMock()
    mock_om.get_user_orders = MagicMock(return_value=[
        {"user_id": "111", "exchange": "bithumb", "ticker": "KRW-BTC", "price": 100.0, "volume": 1.0, "side": "bid", "status": "wait", "group_no": 1},
        {"user_id": "111", "exchange": "toss", "ticker": "403850", "price": 30000.0, "volume": 1.0, "side": "bid", "status": "reserved", "group_no": 3},
    ])
    monkeypatch.setattr(main, "order_manager", mock_om)

    update = _make_update()
    context = _make_context([])

    await query_handlers.orders_command(update, context)

    mock_om.get_user_orders.assert_called_once_with("111")
    text = update.message.reply_text.call_args.args[0]
    assert "BITHUMB" in text
    assert "토스증권" in text
    assert "403850" in text


async def test_orders_command_with_exchange_arg_filters_to_that_exchange(monkeypatch):
    _patch_auth(monkeypatch, _user(default_exchange="bithumb"))

    mock_om = MagicMock()
    mock_om.get_user_orders = MagicMock(return_value=[
        {"user_id": "111", "exchange": "toss", "ticker": "403850", "price": 30000.0, "volume": 1.0, "side": "bid", "status": "reserved", "group_no": 3},
    ])
    monkeypatch.setattr(main, "order_manager", mock_om)

    update = _make_update()
    context = _make_context(["toss"])

    await query_handlers.orders_command(update, context)

    mock_om.get_user_orders.assert_called_once_with("111", "toss")
    text = update.message.reply_text.call_args.args[0]
    assert "토스증권" in text
    assert "403850" in text
