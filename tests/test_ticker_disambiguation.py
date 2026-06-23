import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from telegram import Chat, User
from telegram.ext import ApplicationBuilder, CommandHandler

import main
from core.ticker_disambiguation import (
    create_disambiguation_token,
    pop_valid_disambiguation,
    _pending_disambiguations,
)


def _build_app_with_dummy_price_handler():
    """get_me() 네트워크 호출 없이 bot.username을 채워 CommandHandler 매칭이 동작하게 한다."""
    app = ApplicationBuilder().token("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11").build()
    app.bot._bot_user = User(id=999, first_name="TestBot", is_bot=True, username="testbot")
    app.bot._bot_initialized = True
    app._initialized = True

    captured = {}

    async def dummy_price(update, context):
        captured["text"] = update.message.text
        captured["args"] = context.args

    app.add_handler(CommandHandler("price", dummy_price))
    return app, captured


def _make_callback_update(token: str, idx: int, user_id: int = 111):
    chat = Chat(id=user_id, type="private")
    user = User(id=user_id, first_name="tester", is_bot=False)

    query_message = MagicMock()
    query_message.message_id = 5
    query_message.date = datetime.now()
    query_message.chat = chat

    query = MagicMock()
    query.data = f"tickerpick|{token}|{idx}"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = query_message
    query.from_user = user

    update = MagicMock()
    update.callback_query = query
    update.effective_chat.id = user_id
    return update, query


# 합성 Update/Message + process_update() 재실행 경로가 실제 PTB(22.8)에서
# CommandHandler까지 도달해 정상적으로 명령을 재실행하는지 검증한다.
async def test_ticker_disambiguation_callback_replays_patched_command():
    app, captured = _build_app_with_dummy_price_handler()

    token = create_disambiguation_token(
        "111", "/price 토스 삼천당제약", "삼천당제약", [("삼천당제약", "000250")]
    )
    update, query = _make_callback_update(token, idx=0)

    context = MagicMock()
    context.bot = app.bot
    context.application = app

    await main.ticker_disambiguation_callback(update, context)

    query.answer.assert_awaited_once()
    query.edit_message_text.assert_awaited_once()
    assert captured["text"] == "/price 토스 000250"
    assert captured["args"] == ["토스", "000250"]


async def test_ticker_disambiguation_callback_rejects_wrong_user():
    app, captured = _build_app_with_dummy_price_handler()

    token = create_disambiguation_token(
        "111", "/price 토스 삼천당제약", "삼천당제약", [("삼천당제약", "000250")]
    )
    update, query = _make_callback_update(token, idx=0, user_id=222)

    context = MagicMock()
    context.bot = app.bot
    context.application = app

    await main.ticker_disambiguation_callback(update, context)

    assert "text" not in captured
    query.edit_message_text.assert_awaited_once()
    assert "다른 사용자" in query.edit_message_text.call_args[0][0]


async def test_ticker_disambiguation_callback_rejects_invalid_index():
    app, captured = _build_app_with_dummy_price_handler()

    token = create_disambiguation_token(
        "111", "/price 토스 삼천당제약", "삼천당제약", [("삼천당제약", "000250")]
    )
    update, query = _make_callback_update(token, idx=5)

    context = MagicMock()
    context.bot = app.bot
    context.application = app

    await main.ticker_disambiguation_callback(update, context)

    assert "text" not in captured
    query.edit_message_text.assert_awaited_once()


async def test_resolve_ticker_for_command_sends_disambiguation_buttons(monkeypatch):
    # 정확매칭 실패(한글 이름이 그대로 남음) 시 find_kr_stock_candidates 결과로 버튼을 보내야 한다.
    async def fake_resolve_ticker(user_id, exchange, raw):
        return raw  # 정확 매칭 실패 시 resolve_ticker는 원본 이름을 그대로 반환

    async def fake_find_candidates(name, adapter, user_id, exchange, limit=5):
        return [("삼천당제약", "000250"), ("삼천리", "004690")]

    monkeypatch.setattr(main.exchange_adapter, "resolve_ticker", fake_resolve_ticker)
    monkeypatch.setattr(main, "find_kr_stock_candidates", fake_find_candidates)

    update = MagicMock()
    update.message.text = "/price 토스 삼천당제"
    update.message.reply_text = AsyncMock()

    exchange, ticker = await main.resolve_ticker_for_command(
        update, "111", ["토스", "삼천당제"], "upbit"
    )

    assert ticker is None
    update.message.reply_text.assert_awaited_once()
    _, kwargs = update.message.reply_text.call_args
    markup = kwargs["reply_markup"]
    callback_datas = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert len(callback_datas) == 2
    assert all(cd.startswith("tickerpick|") for cd in callback_datas)


async def test_resolve_ticker_for_command_falls_back_to_generic_error_when_no_candidates(monkeypatch):
    async def fake_resolve_ticker(user_id, exchange, raw):
        return raw

    async def fake_find_candidates(name, adapter, user_id, exchange, limit=5):
        return []

    monkeypatch.setattr(main.exchange_adapter, "resolve_ticker", fake_resolve_ticker)
    monkeypatch.setattr(main, "find_kr_stock_candidates", fake_find_candidates)

    update = MagicMock()
    update.message.text = "/price 토스 존재하지않는종목"
    update.message.reply_text = AsyncMock()

    exchange, ticker = await main.resolve_ticker_for_command(
        update, "111", ["토스", "존재하지않는종목"], "upbit"
    )

    assert ticker is None
    update.message.reply_text.assert_awaited_once()
    args, _ = update.message.reply_text.call_args
    assert "종목코드로 입력하세요" in args[0]


def test_pop_valid_disambiguation_is_single_use():
    token = create_disambiguation_token("111", "/price 토스 삼천당제약", "삼천당제약", [("삼천당제약", "000250")])

    code, original_text, raw_name = pop_valid_disambiguation(token, "111", 0)
    assert code == "000250"
    assert original_text == "/price 토스 삼천당제약"
    assert raw_name == "삼천당제약"
    assert token not in _pending_disambiguations

    code2, err, _ = pop_valid_disambiguation(token, "111", 0)
    assert code2 is None
    assert "만료" in err or "찾을 수 없는" in err
