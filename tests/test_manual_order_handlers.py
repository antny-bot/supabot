import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.user_manager import UserManager
import main
from handlers import manual_order_handlers


def _active_user(preferences=None):
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    if preferences:
        prefs.update(preferences)
    return {
        "is_active": True,
        "preferences": prefs,
        "exchanges": {"upbit": {}},
        "llm": {"gemini_api_key": ""},
    }


def _make_query(user_id, token):
    query = MagicMock()
    query.from_user.id = user_id
    query.data = f"manualrun|{token}"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    return query


def _make_update(query):
    update = MagicMock()
    update.callback_query = query
    return update


def _make_context():
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def _patch_user_manager(monkeypatch, user):
    mock_um = MagicMock()
    mock_um.get_user = MagicMock(return_value=user)
    monkeypatch.setattr(main, "user_manager", mock_um)


def _patch_order_manager(monkeypatch, open_orders=None):
    mock_om = MagicMock()
    mock_om.get_user_orders = MagicMock(return_value=open_orders or [])
    mock_om.add_order = MagicMock()
    monkeypatch.setattr(main, "order_manager", mock_om)
    return mock_om


def _patch_exchange_adapter(monkeypatch, ticker_price=None, create_order_result=None):
    mock_ex = MagicMock()
    if ticker_price is None:
        mock_ex.get_ticker = AsyncMock(return_value=None)
    else:
        mock_ex.get_ticker = AsyncMock(return_value={"trade_price": ticker_price})
    mock_ex.create_order = AsyncMock(return_value=create_order_result or {"uuid": "order-uuid-1"})
    fake_exchange_obj = MagicMock()
    fake_exchange_obj.env_label = MagicMock(return_value=None)
    fake_exchange_obj.is_market_open = MagicMock(return_value=True)
    fake_exchange_obj.supports_reserved_orders = False
    mock_ex.get_exchange = MagicMock(return_value=fake_exchange_obj)
    monkeypatch.setattr(main, "exchange_adapter", mock_ex)
    return mock_ex


async def test_market_buy_blocked_when_estimated_exposure_exceeds_max_order(monkeypatch):
    """시장가 매수는 price=0이라 한도 검증이 우회되던 구멍(L1) — 현재가 추정으로 막혀야 한다."""
    user = _active_user({"max_order_krw": 1_000_000})
    _patch_user_manager(monkeypatch, user)
    _patch_order_manager(monkeypatch)
    mock_ex = _patch_exchange_adapter(monkeypatch, ticker_price=100_000_000)

    token = main.create_manual_order_token("1", "upbit", "bid", "KRW-BTC", 0.0, 0.1, ord_type="market")
    query = _make_query(1, token)
    update = _make_update(query)
    ctx = _make_context()

    await manual_order_handlers.manual_order_confirm_callback(update, ctx)

    query.edit_message_text.assert_called_once()
    msg = query.edit_message_text.call_args.args[0]
    assert "한도" in msg or "초과" in msg
    mock_ex.create_order.assert_not_called()


async def test_market_buy_proceeds_when_within_estimated_limit(monkeypatch):
    user = _active_user({"max_order_krw": 1_000_000_000})
    _patch_user_manager(monkeypatch, user)
    mock_om = _patch_order_manager(monkeypatch)
    mock_ex = _patch_exchange_adapter(monkeypatch, ticker_price=100_000_000)

    token = main.create_manual_order_token("1", "upbit", "bid", "KRW-BTC", 0.0, 0.1, ord_type="market")
    query = _make_query(1, token)
    update = _make_update(query)
    ctx = _make_context()

    await manual_order_handlers.manual_order_confirm_callback(update, ctx)

    mock_ex.create_order.assert_called_once()
    mock_om.add_order.assert_called_once()


async def test_market_buy_blocked_when_ticker_lookup_fails(monkeypatch):
    """현재가 조회 실패 시 한도 검증을 우회하지 않고 안전하게 차단한다."""
    user = _active_user({"max_order_krw": 1_000_000_000})
    _patch_user_manager(monkeypatch, user)
    _patch_order_manager(monkeypatch)
    mock_ex = _patch_exchange_adapter(monkeypatch, ticker_price=None)

    token = main.create_manual_order_token("1", "upbit", "bid", "KRW-BTC", 0.0, 0.1, ord_type="market")
    query = _make_query(1, token)
    update = _make_update(query)
    ctx = _make_context()

    await manual_order_handlers.manual_order_confirm_callback(update, ctx)

    query.edit_message_text.assert_called_once()
    msg = query.edit_message_text.call_args.args[0]
    assert "현재가 조회" in msg
    mock_ex.create_order.assert_not_called()


async def test_limit_buy_still_blocked_by_max_order_unchanged(monkeypatch):
    """기존 지정가 매수 한도 검증 동작은 회귀 없이 유지되어야 한다."""
    user = _active_user({"max_order_krw": 1_000_000})
    _patch_user_manager(monkeypatch, user)
    _patch_order_manager(monkeypatch)
    mock_ex = _patch_exchange_adapter(monkeypatch)

    token = main.create_manual_order_token("1", "upbit", "bid", "KRW-BTC", 100_000_000, 0.1, ord_type="limit")
    query = _make_query(1, token)
    update = _make_update(query)
    ctx = _make_context()

    await manual_order_handlers.manual_order_confirm_callback(update, ctx)

    query.edit_message_text.assert_called_once()
    mock_ex.create_order.assert_not_called()
    mock_ex.get_ticker.assert_not_called()
