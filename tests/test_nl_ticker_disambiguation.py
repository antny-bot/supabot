import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import main
from handlers import nl_intent_handlers
from core.ticker_disambiguation import create_nl_disambiguation_token


async def test_execute_confirmed_intent_sends_disambiguation_buttons(monkeypatch):
    # 한글 종목명이 정확히 매칭되지 않으면(resolve_ticker가 원본 그대로 반환) 후보 버튼을 보내야 한다.
    async def fake_resolve_ticker(user_id, exchange, ticker):
        return ticker

    async def fake_find_candidates(name, adapter, user_id, exchange, limit=5):
        return [("삼천당제약", "000250")]

    monkeypatch.setattr(main.exchange_adapter, "resolve_ticker", fake_resolve_ticker)
    monkeypatch.setattr(nl_intent_handlers, "find_kr_stock_candidates", fake_find_candidates)

    query = MagicMock()
    query.from_user.id = 111
    query.edit_message_text = AsyncMock()

    user = {"preferences": {"default_exchange": "upbit"}}
    intent = {"action": "cancel", "exchange": "kis", "ticker": "삼천당제"}

    await nl_intent_handlers.execute_confirmed_intent(query, MagicMock(), user, intent)

    query.edit_message_text.assert_awaited_once()
    args, kwargs = query.edit_message_text.call_args
    assert "후보" in args[0]
    markup = kwargs["reply_markup"]
    callback_datas = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert len(callback_datas) == 1
    assert callback_datas[0].startswith("nltickerpick|")


async def test_execute_confirmed_intent_falls_back_to_error_when_no_candidates(monkeypatch):
    async def fake_resolve_ticker(user_id, exchange, ticker):
        return ticker

    async def fake_find_candidates(name, adapter, user_id, exchange, limit=5):
        return []

    monkeypatch.setattr(main.exchange_adapter, "resolve_ticker", fake_resolve_ticker)
    monkeypatch.setattr(nl_intent_handlers, "find_kr_stock_candidates", fake_find_candidates)

    query = MagicMock()
    query.from_user.id = 111
    query.edit_message_text = AsyncMock()

    user = {"preferences": {"default_exchange": "upbit"}}
    intent = {"action": "cancel", "exchange": "kis", "ticker": "존재하지않는종목"}

    await nl_intent_handlers.execute_confirmed_intent(query, MagicMock(), user, intent)

    query.edit_message_text.assert_awaited_once()
    assert "찾을 수 없습니다" in query.edit_message_text.call_args[0][0]


async def test_nl_ticker_disambiguation_callback_resolves_and_reexecutes(monkeypatch):
    # 후보 선택 → intent['ticker']를 코드로 교체해 execute_confirmed_intent를 재호출하는지 검증.
    token = create_nl_disambiguation_token(
        "111", {"action": "cancel", "exchange": "kis", "ticker": "삼천당제"}, [("삼천당제약", "000250")]
    )

    async def fake_resolve_ticker(user_id, exchange, ticker):
        return ticker

    monkeypatch.setattr(main.exchange_adapter, "resolve_ticker", fake_resolve_ticker)
    monkeypatch.setattr(main.order_manager, "get_user_orders", lambda user_id, exchange: [])
    monkeypatch.setattr(main.user_manager, "get_user", lambda uid: {"is_active": True, "preferences": {}})

    query = MagicMock()
    query.data = f"nltickerpick|{token}|0"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user.id = 111

    update = MagicMock()
    update.callback_query = query
    update.effective_chat.id = 111

    await nl_intent_handlers.nl_ticker_disambiguation_callback(update, MagicMock())

    query.answer.assert_awaited_once()
    final_call = query.edit_message_text.call_args_list[-1]
    assert "취소 완료" in final_call[0][0]
    assert "000250" in final_call[0][0]


async def test_nl_ticker_disambiguation_callback_rejects_wrong_user(monkeypatch):
    token = create_nl_disambiguation_token(
        "111", {"action": "cancel", "exchange": "kis", "ticker": "삼천당제"}, [("삼천당제약", "000250")]
    )

    query = MagicMock()
    query.data = f"nltickerpick|{token}|0"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user.id = 222

    update = MagicMock()
    update.callback_query = query
    update.effective_chat.id = 222

    await nl_intent_handlers.nl_ticker_disambiguation_callback(update, MagicMock())

    query.edit_message_text.assert_awaited_once()
    assert "다른 사용자" in query.edit_message_text.call_args[0][0]
