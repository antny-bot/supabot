"""Phase 10 단기: /config UX 개선 + 자연어 커버리지 확대 테스트"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


# ── build_config_view: stop_loss_pct + signal_bb_alert ──────────────────────

def test_config_view_shows_stop_loss_pct():
    """stop_loss_pct가 설정된 경우 설정값%로 표시되어야 함."""
    from core.formatters import build_config_view
    from core.user_manager import UserManager
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    prefs["stop_loss_pct"] = 5.0
    user = {"is_active": True, "is_admin": False, "preferences": prefs,
            "exchanges": {}, "llm": {}}
    view = build_config_view(user)
    assert "stop_loss_pct" in view
    assert "5%" in view


def test_config_view_shows_stop_loss_disabled_when_none():
    """stop_loss_pct가 None이면 '없음 (손절 비활성)'으로 표시되어야 함."""
    from core.formatters import build_config_view
    from core.user_manager import UserManager
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    prefs["stop_loss_pct"] = None
    user = {"is_active": True, "is_admin": False, "preferences": prefs,
            "exchanges": {}, "llm": {}}
    view = build_config_view(user)
    assert "없음 (손절 비활성)" in view


def test_config_view_shows_signal_bb_alert():
    """signal_bb_alert 설정이 현재 설정 뷰에 표시되어야 함."""
    from core.formatters import build_config_view
    from core.user_manager import UserManager
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    prefs["signal_bb_alert"] = True
    user = {"is_active": True, "is_admin": False, "preferences": prefs,
            "exchanges": {}, "llm": {}}
    view = build_config_view(user)
    assert "signal_bb_alert" in view


# ── /config no-args: shows config view HTML ──────────────────────────────────

async def test_config_command_no_args_shows_html_view(monkeypatch):
    """/config 인자 없이 호출 시 HTML 설정 뷰를 전송해야 함."""
    import main
    from handlers import config_handlers
    from core.user_manager import UserManager

    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    user = {"is_active": True, "is_admin": False, "preferences": prefs,
            "exchanges": {}, "llm": {"gemini_api_key": ""}}
    mock_um = MagicMock()
    mock_um.get_user.return_value = user
    monkeypatch.setattr(main, "user_manager", mock_um)

    mock_om = MagicMock()
    mock_om.orders = {}
    monkeypatch.setattr(main, "order_manager", mock_om)

    update = MagicMock()
    update.effective_chat.id = 123
    update.message.text = "/config"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.args = []

    await config_handlers.config_command(update, context)

    update.message.reply_text.assert_called_once()
    call_kwargs = update.message.reply_text.call_args
    assert call_kwargs.kwargs.get("parse_mode") == "HTML"
    msg = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("text", "")
    assert "현재 사용자 설정" in msg


# ── /config shorthand: /config <key> <value> ─────────────────────────────────

async def test_config_command_shorthand_sets_value(monkeypatch):
    """/config rsi_budget_krw 1000000 형식이 설정을 저장해야 함."""
    import main
    from handlers import config_handlers
    from core.user_manager import UserManager

    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    user = {"is_active": True, "is_admin": False, "preferences": prefs,
            "exchanges": {}, "llm": {"gemini_api_key": ""}}
    mock_um = MagicMock()
    mock_um.get_user.return_value = user
    monkeypatch.setattr(main, "user_manager", mock_um)

    mock_om = MagicMock()
    mock_om.orders = {}
    monkeypatch.setattr(main, "order_manager", mock_om)

    update = MagicMock()
    update.effective_chat.id = 123
    update.message.text = "/config rsi_budget_krw 1000000"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.args = ["rsi_budget_krw", "1000000"]

    await config_handlers.config_command(update, context)

    mock_um.update_preference.assert_called_once()
    call_args = mock_um.update_preference.call_args
    assert call_args[0][1] == "rsi_budget_krw"
    assert call_args[0][2] == 1000000


# ── NL 패턴: budget change ───────────────────────────────────────────────────

def test_nl_budget_change_detected():
    """'예산 100만 바꿔줘'가 config_set rsi_budget_krw 인텐트를 반환해야 함."""
    from core.natural_language import preprocess_natural_language_intent
    user = {"preferences": {"default_exchange": "upbit"}}
    intent = preprocess_natural_language_intent("예산 100만 바꿔줘", user)
    assert intent is not None
    assert intent["action"] == "config_set"
    assert intent["config_key"] == "rsi_budget_krw"
    assert intent["config_value"] == "1000000"


def test_nl_budget_change_with_설정():
    """'예산 50만 설정'도 config_set rsi_budget_krw를 반환해야 함."""
    from core.natural_language import preprocess_natural_language_intent
    user = {"preferences": {"default_exchange": "upbit"}}
    intent = preprocess_natural_language_intent("RSI 예산 50만 설정해줘", user)
    assert intent is not None
    assert intent["action"] == "config_set"
    assert intent["config_key"] == "rsi_budget_krw"
    assert int(intent["config_value"]) == 500000


# ── NL 패턴: stop-loss ────────────────────────────────────────────────────────

def test_nl_stoploss_detected():
    """'손절 5% 설정'이 config_set stop_loss_pct 인텐트를 반환해야 함."""
    from core.natural_language import preprocess_natural_language_intent
    user = {"preferences": {"default_exchange": "upbit"}}
    intent = preprocess_natural_language_intent("손절 5% 설정해줘", user)
    assert intent is not None
    assert intent["action"] == "config_set"
    assert intent["config_key"] == "stop_loss_pct"
    assert intent["config_value"] == "5"


# ── NL 패턴: BB alert ─────────────────────────────────────────────────────────

def test_nl_bb_alert_on_detected():
    """'볼린저 알림 켜줘'가 config_set signal_bb_alert on을 반환해야 함."""
    from core.natural_language import preprocess_natural_language_intent
    user = {"preferences": {"default_exchange": "upbit"}}
    intent = preprocess_natural_language_intent("볼린저 알림 켜줘", user)
    assert intent is not None
    assert intent["action"] == "config_set"
    assert intent["config_key"] == "signal_bb_alert"
    assert intent["config_value"] == "on"


def test_nl_bb_alert_off_detected():
    """'볼린저 알림 꺼줘'가 config_set signal_bb_alert off를 반환해야 함."""
    from core.natural_language import preprocess_natural_language_intent
    user = {"preferences": {"default_exchange": "upbit"}}
    intent = preprocess_natural_language_intent("볼린저 알림 꺼줘", user)
    assert intent is not None
    assert intent["action"] == "config_set"
    assert intent["config_key"] == "signal_bb_alert"
    assert intent["config_value"] == "off"


# ── NL 패턴: RSI check ────────────────────────────────────────────────────────

def test_nl_rsi_check_detected():
    """'BTC RSI 알려줘'가 rsi 인텐트와 ticker를 반환해야 함."""
    from core.natural_language import preprocess_natural_language_intent
    user = {"preferences": {"default_exchange": "upbit"}}
    intent = preprocess_natural_language_intent("BTC RSI 알려줘", user)
    assert intent is not None
    assert intent["action"] == "rsi"
    assert intent.get("ticker") == "BTC"


def test_nl_rsi_check_with_korean_ticker():
    """'삼성전자 RSI 확인'이 rsi 인텐트를 반환해야 함."""
    from core.natural_language import preprocess_natural_language_intent
    user = {"preferences": {"default_exchange": "kis"}}
    intent = preprocess_natural_language_intent("삼성전자 RSI 확인해줘", user)
    assert intent is not None
    assert intent["action"] == "rsi"
    assert intent.get("ticker") == "005930"


# ── NL 패턴: indicators ───────────────────────────────────────────────────────

def test_nl_indicators_detected():
    """'지표 보여줘 ETH'가 indicators 인텐트와 ticker를 반환해야 함."""
    from core.natural_language import preprocess_natural_language_intent
    user = {"preferences": {"default_exchange": "upbit"}}
    intent = preprocess_natural_language_intent("ETH 지표 보여줘", user)
    assert intent is not None
    assert intent["action"] == "indicators"
    assert intent.get("ticker") == "ETH"


def test_nl_macd_triggers_indicators():
    """'비트 MACD 알려줘'가 indicators 인텐트를 반환해야 함."""
    from core.natural_language import preprocess_natural_language_intent
    user = {"preferences": {"default_exchange": "upbit"}}
    intent = preprocess_natural_language_intent("비트 MACD 알려줘", user)
    assert intent is not None
    assert intent["action"] == "indicators"
    assert intent.get("ticker") == "BTC"
