"""Phase 10 중기: /report 수익률 리포트 + 조용한 시간(Quiet Hours) 테스트"""
import json
import os
import sys
import time
import tempfile
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


# ── trade_log: append + read ─────────────────────────────────────────────────

def test_append_trade_creates_file_and_record():
    """append_trade가 trade log 파일에 레코드를 추가해야 함."""
    from core.trade_log import append_trade, read_trades
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        append_trade("u1", "upbit", "KRW-BTC", "bid", 50_000_000, 0.001, "manual", "uuid-1", path=path)
        trades = read_trades("u1", path=path)
        assert len(trades) == 1
        assert trades[0]["ticker"] == "KRW-BTC"
        assert trades[0]["side"] == "bid"
    finally:
        os.unlink(path)


def test_read_trades_filters_by_user_id():
    """read_trades는 해당 user_id의 기록만 반환해야 함."""
    from core.trade_log import append_trade, read_trades
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = f.name
    try:
        append_trade("u1", "upbit", "KRW-BTC", "bid", 50_000_000, 0.001, "manual", "uuid-1", path=path)
        append_trade("u2", "upbit", "KRW-ETH", "bid", 3_000_000, 0.01, "manual", "uuid-2", path=path)
        trades = read_trades("u1", path=path)
        assert len(trades) == 1
        assert trades[0]["user_id"] == "u1"
    finally:
        os.unlink(path)


def test_read_trades_period_today_filters_old():
    """period='today' 이전 기록은 반환되지 않아야 함."""
    from core.trade_log import read_trades
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        old_ts = time.time() - 86400 * 2  # 2일 전
        f.write(json.dumps({"ts": old_ts, "user_id": "u1", "ticker": "KRW-BTC",
                             "exchange": "upbit", "side": "bid",
                             "price": 1.0, "volume": 1.0, "strategy": "manual", "uuid": "old"}) + "\n")
        path = f.name
    try:
        trades = read_trades("u1", period="today", path=path)
        assert len(trades) == 0
    finally:
        os.unlink(path)


def test_read_trades_returns_empty_when_no_file():
    """파일이 없으면 빈 리스트를 반환해야 함."""
    from core.trade_log import read_trades
    trades = read_trades("u1", period="all", path="/nonexistent/path/trades.jsonl")
    assert trades == []


# ── build_report_view ─────────────────────────────────────────────────────────

def test_build_report_view_shows_ticker_and_pnl():
    """build_report_view에 종목별 매수/매도와 손익이 표시되어야 함."""
    from core.formatters import build_report_view
    trades = [
        {"exchange": "upbit", "ticker": "KRW-BTC", "side": "bid", "price": 50_000_000.0, "volume": 0.001,
         "strategy": "manual", "uuid": "a"},
        {"exchange": "upbit", "ticker": "KRW-BTC", "side": "ask", "price": 55_000_000.0, "volume": 0.001,
         "strategy": "manual", "uuid": "b"},
    ]
    view = build_report_view(trades, "today")
    assert "KRW-BTC" in view
    assert "매수" in view
    assert "매도" in view
    assert "손익" in view


def test_build_report_view_net_positive():
    """매도 > 매수인 경우 총 손익이 양수여야 함."""
    from core.formatters import build_report_view
    trades = [
        {"exchange": "upbit", "ticker": "KRW-BTC", "side": "bid", "price": 50_000_000.0, "volume": 0.001, "strategy": "manual", "uuid": "a"},
        {"exchange": "upbit", "ticker": "KRW-BTC", "side": "ask", "price": 60_000_000.0, "volume": 0.001, "strategy": "manual", "uuid": "b"},
    ]
    view = build_report_view(trades, "all")
    # net = 60000 - 50000 = +10000원 → "+" 기호 포함
    assert "+10,000" in view


# ── /report command ───────────────────────────────────────────────────────────

async def test_report_command_no_trades_shows_empty_message(monkeypatch, tmp_path):
    """체결 기록이 없으면 '기록이 없습니다' 메시지를 반환해야 함."""
    import main
    from handlers import query_handlers
    import core.trade_log as tl
    from core.user_manager import UserManager

    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    user = {"is_active": True, "is_admin": False, "preferences": prefs,
            "exchanges": {}, "llm": {"gemini_api_key": ""}}
    mock_um = MagicMock()
    mock_um.get_user.return_value = user
    monkeypatch.setattr(main, "user_manager", mock_um)

    empty_log = str(tmp_path / "trades.jsonl")
    monkeypatch.setattr(tl, "TRADE_LOG_PATH", empty_log)

    update = MagicMock()
    update.effective_chat.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []

    await query_handlers.report_command(update, context)

    call_text = update.message.reply_text.call_args[0][0]
    assert "기록" in call_text


async def test_report_command_invalid_period_shows_usage(monkeypatch):
    """잘못된 period 인자 시 사용법을 안내해야 함."""
    import main
    from handlers import query_handlers
    from core.user_manager import UserManager

    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    user = {"is_active": True, "is_admin": False, "preferences": prefs,
            "exchanges": {}, "llm": {"gemini_api_key": ""}}
    mock_um = MagicMock()
    mock_um.get_user.return_value = user
    monkeypatch.setattr(main, "user_manager", mock_um)

    update = MagicMock()
    update.effective_chat.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["badperiod"]

    await query_handlers.report_command(update, context)

    call_text = update.message.reply_text.call_args[0][0]
    assert "사용법" in call_text


# ── is_quiet_hours ────────────────────────────────────────────────────────────

def test_is_quiet_hours_false_when_not_configured():
    """quiet_hours 미설정 시 항상 False를 반환해야 함."""
    from core.user_manager import is_quiet_hours
    from core.user_manager import UserManager
    user = {"preferences": dict(UserManager.DEFAULT_PREFERENCES)}
    assert is_quiet_hours(user) is False


def test_is_quiet_hours_true_within_range():
    """현재 시각이 quiet_hours 범위 내이면 True를 반환해야 함."""
    from core.user_manager import is_quiet_hours
    from datetime import datetime, timezone, timedelta

    class _FakeDateTime:
        @staticmethod
        def now(tz=None):
            return datetime(2024, 1, 1, 23, 30, tzinfo=tz)  # 23:30

    import core.user_manager as um_module
    orig = um_module.datetime
    try:
        um_module.datetime = _FakeDateTime
        user = {"preferences": {"quiet_hours_start": "22:00", "quiet_hours_end": "08:00"}}
        assert is_quiet_hours(user) is True
    finally:
        um_module.datetime = orig


def test_is_quiet_hours_false_outside_range():
    """현재 시각이 quiet_hours 범위 밖이면 False를 반환해야 함."""
    from core.user_manager import is_quiet_hours
    from datetime import datetime, timezone, timedelta

    class _FakeDateTime:
        @staticmethod
        def now(tz=None):
            return datetime(2024, 1, 1, 12, 0, tzinfo=tz)  # 12:00

    import core.user_manager as um_module
    orig = um_module.datetime
    try:
        um_module.datetime = _FakeDateTime
        user = {"preferences": {"quiet_hours_start": "22:00", "quiet_hours_end": "08:00"}}
        assert is_quiet_hours(user) is False
    finally:
        um_module.datetime = orig


# ── build_config_view: quiet hours ──────────────────────────────────────────

def test_config_view_shows_quiet_hours_when_set():
    """quiet_hours 설정 시 설정 뷰에 시간대가 표시되어야 함."""
    from core.formatters import build_config_view
    from core.user_manager import UserManager
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    prefs["quiet_hours_start"] = "22:00"
    prefs["quiet_hours_end"] = "08:00"
    user = {"is_active": True, "is_admin": False, "preferences": prefs,
            "exchanges": {}, "llm": {}}
    view = build_config_view(user)
    assert "22:00" in view
    assert "08:00" in view


def test_config_view_shows_quiet_hours_disabled_when_none():
    """quiet_hours 미설정 시 '비활성'으로 표시되어야 함."""
    from core.formatters import build_config_view
    from core.user_manager import UserManager
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    user = {"is_active": True, "is_admin": False, "preferences": prefs,
            "exchanges": {}, "llm": {}}
    view = build_config_view(user)
    assert "비활성" in view


# ── parsers: quiet_hours ──────────────────────────────────────────────────────

def test_parse_config_quiet_hours_valid_time():
    """HH:MM 형식의 조용한 시간대를 정상 파싱해야 함."""
    from core.parsers import parse_config_value
    result = parse_config_value("quiet_hours_start", "22:00")
    assert result == "22:00"


def test_parse_config_quiet_hours_off_returns_none():
    """'off' 입력 시 None을 반환해야 함."""
    from core.parsers import parse_config_value
    result = parse_config_value("quiet_hours_end", "off")
    assert result is None


def test_parse_config_quiet_hours_invalid_format_raises():
    """잘못된 형식은 ValueError를 발생시켜야 함."""
    from core.parsers import parse_config_value
    try:
        parse_config_value("quiet_hours_start", "2200")
        assert False, "ValueError 미발생"
    except ValueError:
        pass
