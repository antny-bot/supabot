import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.user_manager import UserManager
import core.exchanges.kis as kis_module
import main
from handlers import strategy_handlers


def _make_update(user_id=111, text="/grid"):
    update = MagicMock()
    update.effective_chat.id = user_id
    update.message.text = text
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    update.message.reply_text = AsyncMock(return_value=status_msg)
    return update


def _make_context(args):
    ctx = MagicMock()
    ctx.args = args
    return ctx


def _active_user(preferences=None):
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    if preferences:
        prefs.update(preferences)
    return {
        "is_active": True,
        "preferences": prefs,
        "exchanges": {},
        "llm": {"gemini_api_key": ""},
    }


def _patch_auth(monkeypatch, user):
    """check_auth 데코레이터가 통과하도록 user_manager.get_user 목킹."""
    mock_um = MagicMock()
    mock_um.get_user = MagicMock(return_value=user)
    monkeypatch.setattr(main, "user_manager", mock_um)


# T4: grid_command — KIS 거래소 + 정규장 외 → 정규장 안내
async def test_grid_command_kis_outside_market_hours(monkeypatch):
    user = _active_user()
    _patch_auth(monkeypatch, user)
    monkeypatch.setattr(kis_module, "is_kis_regular_session", lambda: False)

    update = _make_update(text="/grid 한투 005930 70000 80000 3 1000000")
    ctx = _make_context(["한투", "005930", "70000", "80000", "3", "1000000"])

    await strategy_handlers.grid_command(update, ctx)

    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args.args[0]
    assert "정규장" in reply_text


# T5: grid_command — 유효 인자 → 확인 미리보기 + 인라인 버튼
async def test_grid_command_valid_args_sends_preview(monkeypatch):
    user = _active_user({"default_exchange": "upbit", "max_order_krw": None})
    _patch_auth(monkeypatch, user)

    update = _make_update(text="/grid KRW-BTC 90000000 95000000 3 600000")
    ctx = _make_context(["KRW-BTC", "90000000", "95000000", "3", "600000"])

    await strategy_handlers.grid_command(update, ctx)

    update.message.reply_text.assert_called_once()
    call_kwargs = update.message.reply_text.call_args
    # reply_markup 포함 여부 확인
    reply_markup = call_kwargs.kwargs.get("reply_markup") or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
    assert reply_markup is not None

    message_text = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("text", "")
    assert "거미줄 매수 주문 확인" in message_text

    # callback_data에 거래소·종목 포함 확인
    buttons = reply_markup.inline_keyboard
    confirm_button = buttons[0][0]
    assert confirm_button.callback_data.startswith("gridrun|upbit|KRW-BTC")


# T6: rsitrade_command — 예산 미설정 → 오류 안내
async def test_rsitrade_command_no_budget_shows_error(monkeypatch):
    user = _active_user({"default_exchange": "upbit", "rsi_budget_krw": None})
    _patch_auth(monkeypatch, user)

    # RSI 지원 여부 확인용 (KIS 아니므로 통과)
    mock_adapter = MagicMock()
    mock_adapter.resolve_ticker = AsyncMock(side_effect=lambda user_id, exchange, ticker: ticker)
    monkeypatch.setattr(main, "exchange_adapter", mock_adapter)

    update = _make_update(text="/rsitrade KRW-BTC")
    ctx = _make_context(["KRW-BTC"])

    await strategy_handlers.rsitrade_command(update, ctx)

    update.message.reply_text.assert_called()
    all_texts = " ".join(
        call.args[0] if call.args else call.kwargs.get("text", "")
        for call in update.message.reply_text.call_args_list
    )
    assert "예산" in all_texts
    assert "rsi_budget_krw" in all_texts
