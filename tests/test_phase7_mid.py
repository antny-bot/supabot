"""Phase 7 중기: 멀티지표 + 워치리스트 BB 알림 테스트"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.indicators import BollingerResult, MACDResult, StochasticResult
from core.exchanges.upbit import UpbitExchange
from core.signal_engine import SignalEngine


def _long_candles(n=100, price=50_000_000):
    candles = []
    for i in range(n):
        p = float(price + (i % 7) * 100_000 - (i % 4) * 50_000)
        candles.append({
            "candle_date_time_kst": f"20260101{i:04d}",
            "trade_price": p,
            "opening_price": p * 0.999,
            "high_price": p * 1.005,
            "low_price": p * 0.995,
        })
    return candles


# ── 워치리스트 BB 알림 ────────────────────────────────────────────────────────

class _FakeAdapter:
    def __init__(self, candles, current_price=None):
        self._candles = candles
        self._override_price = current_price

    async def get_candles(self, exchange, ticker, interval="day", count=200, user_id=None):
        candles = list(self._candles[-count:])
        if self._override_price is not None:
            candles[-1] = {**candles[-1], "trade_price": float(self._override_price)}
        return candles

    @staticmethod
    def adjust_price_to_tick(p):
        return int(p)

    def get_exchange(self, exchange):
        return UpbitExchange(self)


def _make_user_manager(prefs_override=None):
    prefs = {
        "rsi_interval": "day",
        "signal_alerts": True,
        "signal_rsi_threshold": 80,   # 높게 → RSI 알림 항상 발생
        "signal_bb_alert": False,
        **(prefs_override or {}),
    }
    um = MagicMock()
    um.users = {
        "111": {
            "is_active": True,
            "preferences": prefs,
            "exchanges": {"upbit": {"watchlist": ["KRW-BTC"]}},
        }
    }
    return um


def test_watchlist_rsi_alert_fires_when_rsi_below_threshold():
    """RSI가 threshold 이하일 때 send_message 호출."""
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    engine = SignalEngine(_make_user_manager({"signal_rsi_threshold": 80}), _FakeAdapter(_long_candles()))
    asyncio.run(engine.analyze_watchlist(app))

    app.bot.send_message.assert_called_once()
    call_kwargs = app.bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == "111"
    assert "RSI" in call_kwargs["text"]


def test_watchlist_no_alert_when_rsi_above_threshold():
    """RSI가 threshold 초과면 send_message 미호출."""
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    engine = SignalEngine(_make_user_manager({"signal_rsi_threshold": 5}), _FakeAdapter(_long_candles()))
    asyncio.run(engine.analyze_watchlist(app))

    app.bot.send_message.assert_not_called()


def test_watchlist_bb_alert_fires_when_price_below_lower_band():
    """signal_bb_alert=True 이고 종가가 BB 하단 아래일 때 send_message 호출."""
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    candles = _long_candles(100, price=50_000_000)
    # RSI threshold를 극도로 낮게 → RSI 조건은 False. BB만 트리거.
    # 종가를 BB 하단보다 훨씬 낮은 값으로 강제
    engine = SignalEngine(
        _make_user_manager({
            "signal_rsi_threshold": 1,  # RSI 거의 항상 위 → RSI 알림 꺼짐
            "signal_bb_alert": True,
        }),
        _FakeAdapter(candles, current_price=1),  # 아주 낮은 종가 → 반드시 BB 하단 미만
    )
    asyncio.run(engine.analyze_watchlist(app))

    app.bot.send_message.assert_called_once()
    text = app.bot.send_message.call_args.kwargs["text"]
    assert "BB하단" in text


def test_watchlist_bb_alert_off_does_not_fire_for_bb_condition():
    """signal_bb_alert=False(기본)이면 BB 조건 검사 안 함."""
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    candles = _long_candles(100, price=50_000_000)
    engine = SignalEngine(
        _make_user_manager({
            "signal_rsi_threshold": 1,
            "signal_bb_alert": False,  # BB 알림 꺼짐
        }),
        _FakeAdapter(candles, current_price=1),
    )
    asyncio.run(engine.analyze_watchlist(app))

    app.bot.send_message.assert_not_called()


def test_watchlist_alert_message_includes_both_reasons_when_both_triggered():
    """RSI + BB 모두 충족 시 메시지에 두 조건 모두 표시."""
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    candles = _long_candles(100, price=50_000_000)
    engine = SignalEngine(
        _make_user_manager({
            "signal_rsi_threshold": 80,  # RSI 높게 → RSI 조건 충족
            "signal_bb_alert": True,
        }),
        _FakeAdapter(candles, current_price=1),  # 종가 극저 → BB 조건 충족
    )
    asyncio.run(engine.analyze_watchlist(app))

    text = app.bot.send_message.call_args.kwargs["text"]
    assert "RSI" in text
    assert "BB하단" in text


def test_watchlist_inactive_user_skipped():
    """is_active=False 유저는 알림 없음."""
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    um = MagicMock()
    um.users = {"222": {
        "is_active": False,
        "preferences": {"signal_alerts": True, "signal_rsi_threshold": 80, "signal_bb_alert": False, "rsi_interval": "day"},
        "exchanges": {"upbit": {"watchlist": ["KRW-BTC"]}},
    }}
    engine = SignalEngine(um, _FakeAdapter(_long_candles()))
    asyncio.run(engine.analyze_watchlist(app))
    app.bot.send_message.assert_not_called()


# ── signal_bb_alert config 파싱 ───────────────────────────────────────────────

def test_signal_bb_alert_config_parse_on():
    from core.parsers import parse_config_value
    assert parse_config_value("signal_bb_alert", "on") is True


def test_signal_bb_alert_config_parse_off():
    from core.parsers import parse_config_value
    assert parse_config_value("signal_bb_alert", "off") is False


def test_signal_bb_alert_config_parse_invalid_raises():
    from core.parsers import parse_config_value
    import pytest
    with pytest.raises(ValueError):
        parse_config_value("signal_bb_alert", "maybe")


def test_signal_bb_alert_in_default_preferences():
    from core.user_manager import UserManager
    assert "signal_bb_alert" in UserManager.DEFAULT_PREFERENCES
    assert UserManager.DEFAULT_PREFERENCES["signal_bb_alert"] is False
