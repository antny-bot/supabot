import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import ta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.indicators import BollingerResult, MACDResult, StochasticResult
from core.signal_engine import SignalEngine
from core.exchanges.upbit import UpbitExchange
from core.exchanges.bithumb import BithumbExchange
from core.exchanges.kis import KisExchange
from core.exchanges.toss import TossExchange

_EXCHANGE_CLASSES = {
    "upbit": UpbitExchange,
    "bithumb": BithumbExchange,
    "kis": KisExchange,
    "toss": TossExchange,
}


class DummyUsers:
    users = {}


class DummyAdapter:
    def __init__(self, candles):
        self._candles = candles

    async def get_candles(self, exchange, ticker, interval="day", count=200, user_id=None):
        return self._candles[-count:]

    @staticmethod
    def adjust_price_to_tick(price):
        return float(price)

    def get_exchange(self, exchange):
        return _EXCHANGE_CLASSES[exchange](self)


def _build_candles(close_prices):
    candles = []
    for idx, close in enumerate(close_prices, start=1):
        candles.append(
            {
                "candle_date_time_kst": f"202605{idx:02d}",
                "trade_price": float(close),
                "opening_price": float(close),
                "high_price": float(close),
                "low_price": float(close),
            }
        )
    return candles


def _sample_close_prices():
    prices = [1000]
    for _ in range(25):
        prices.append(prices[-1] + 20)
    for _ in range(10):
        prices.append(prices[-1] - 10)
    for _ in range(4):
        prices.append(prices[-1] + 10)
    return prices


def test_bid_target_price_does_not_rise_above_last_close_when_target_rsi_is_lower():
    closes = _sample_close_prices()
    engine = SignalEngine(DummyUsers(), DummyAdapter(_build_candles(closes)))

    current_rsi, _ = asyncio.run(engine.get_rsi("bithumb", "KRW-BTC"))
    target_price = asyncio.run(engine.get_price_by_rsi("bithumb", "KRW-BTC", 30, side="bid"))

    assert current_rsi > 30
    assert target_price <= closes[-1]


def test_bid_target_price_recreates_target_rsi_with_same_indicator_model():
    closes = _sample_close_prices()
    engine = SignalEngine(DummyUsers(), DummyAdapter(_build_candles(closes)))

    target_price = asyncio.run(engine.get_price_by_rsi("bithumb", "KRW-BTC", 30, side="bid"))
    next_series = pd.Series(closes + [target_price])
    next_rsi = ta.momentum.RSIIndicator(close=next_series, window=14).rsi().iloc[-1]

    assert next_rsi <= 30.2
    assert next_rsi >= 28.0


class _TickTrackingAdapter(DummyAdapter):
    """KIS/Toss는 KRX 호가단위(adjust_krx_price_to_tick)를 써야 하는지 추적."""
    def __init__(self, candles):
        super().__init__(candles)
        self.krx_calls = 0
        self.crypto_calls = 0

    def get_exchange(self, exchange):
        real = _EXCHANGE_CLASSES[exchange](self)
        tracker = self

        class _Wrapped:
            def supports_minute_candles(self):
                return real.supports_minute_candles()

            def adjust_price_to_tick(self, price, ticker=None):
                if exchange in ("kis", "toss"):
                    tracker.krx_calls += 1
                else:
                    tracker.crypto_calls += 1
                return real.adjust_price_to_tick(price, ticker)

        return _Wrapped()


def test_get_price_by_rsi_uses_krx_tick_for_toss_and_kis():
    closes = _sample_close_prices()

    for exchange in ("toss", "kis"):
        adapter = _TickTrackingAdapter(_build_candles(closes))
        engine = SignalEngine(DummyUsers(), adapter)
        asyncio.run(engine.get_price_by_rsi(exchange, "005930", 30, side="bid"))
        assert adapter.krx_calls == 1
        assert adapter.crypto_calls == 0


def test_get_price_by_rsi_uses_crypto_tick_for_upbit_bithumb():
    closes = _sample_close_prices()
    adapter = _TickTrackingAdapter(_build_candles(closes))
    engine = SignalEngine(DummyUsers(), adapter)
    asyncio.run(engine.get_price_by_rsi("bithumb", "KRW-BTC", 30, side="bid"))
    assert adapter.crypto_calls == 1
    assert adapter.krx_calls == 0


# ── get_indicators ────────────────────────────────────────────────────────────

def _long_candles(n=100):
    """OHLCV 충분한 캔들 데이터 (지표 계산 기간 충족)."""
    prices = [100 + (i % 7) * 3 - (i % 4) for i in range(n)]
    candles = []
    for idx, p in enumerate(prices, start=1):
        candles.append({
            "candle_date_time_kst": f"20260101{idx:04d}",
            "trade_price": float(p),
            "opening_price": float(p) * 0.999,
            "high_price": float(p) * 1.005,
            "low_price": float(p) * 0.995,
        })
    return candles


def test_get_indicators_returns_all_keys():
    engine = SignalEngine(DummyUsers(), DummyAdapter(_long_candles()))
    result = asyncio.run(engine.get_indicators("upbit", "KRW-BTC"))
    assert result is not None
    for key in ("rsi", "macd", "bbands", "stoch", "current_price", "interval"):
        assert key in result


def test_get_indicators_rsi_in_valid_range():
    engine = SignalEngine(DummyUsers(), DummyAdapter(_long_candles()))
    result = asyncio.run(engine.get_indicators("upbit", "KRW-BTC"))
    assert 0.0 <= result["rsi"] <= 100.0


def test_get_indicators_returns_correct_types():
    engine = SignalEngine(DummyUsers(), DummyAdapter(_long_candles()))
    result = asyncio.run(engine.get_indicators("upbit", "KRW-BTC"))
    assert isinstance(result["macd"], MACDResult)
    assert isinstance(result["bbands"], BollingerResult)
    assert isinstance(result["stoch"], StochasticResult)


def test_get_indicators_returns_none_when_no_candles():
    class EmptyAdapter:
        async def get_candles(self, *a, **kw):
            return None
        @staticmethod
        def adjust_price_to_tick(p): return float(p)
        def get_exchange(self, exchange):
            return _EXCHANGE_CLASSES[exchange](self)

    engine = SignalEngine(DummyUsers(), EmptyAdapter())
    result = asyncio.run(engine.get_indicators("upbit", "KRW-BTC"))
    assert result is None


def test_get_indicators_kis_minute_falls_back_to_day():
    """KIS + 분봉 요청 시 interval이 day로 폴백되어야 함."""
    calls = []

    class TrackingAdapter:
        async def get_candles(self, exchange, ticker, interval, count, user_id=None):
            calls.append(interval)
            return _long_candles()
        @staticmethod
        def adjust_price_to_tick(p): return float(p)
        def get_exchange(self, exchange):
            return _EXCHANGE_CLASSES[exchange](self)

    engine = SignalEngine(DummyUsers(), TrackingAdapter())
    asyncio.run(engine.get_indicators("kis", "005930", interval="60"))
    assert calls[0] == "day"


# ── snooze ────────────────────────────────────────────────────────────────────

def test_set_snooze_1h():
    engine = SignalEngine(DummyUsers(), DummyAdapter([]))
    before = time.time()
    expires = engine.set_snooze("123", "upbit", "KRW-BTC", "1h")
    assert abs(expires - (before + 3600)) < 2


def test_set_snooze_2h():
    engine = SignalEngine(DummyUsers(), DummyAdapter([]))
    before = time.time()
    expires = engine.set_snooze("123", "upbit", "KRW-BTC", "2h")
    assert abs(expires - (before + 7200)) < 2


def test_set_snooze_day_returns_next_midnight():
    engine = SignalEngine(DummyUsers(), DummyAdapter([]))
    expires = engine.set_snooze("123", "upbit", "KRW-BTC", "day")
    kst = timezone(timedelta(hours=9))
    exp_dt = datetime.fromtimestamp(expires, tz=kst)
    assert exp_dt.hour == 0 and exp_dt.minute == 0 and exp_dt.second == 0
    assert exp_dt > datetime.now(kst)


def test_analyze_watchlist_sends_alert_once_then_snoozes():
    """조건 충족 시 첫 폴링에만 알람 발송, 이후 스누즈 중엔 발송 안 함."""
    sent = []

    class FakeBot:
        async def send_message(self, **kw):
            sent.append(kw)

    class FakeApp:
        bot = FakeBot()

    user_data = {
        "is_active": True,
        "preferences": {
            "signal_alerts": True,
            "signal_rsi_threshold": 80,  # 높게 설정해 항상 RSI 트리거
            "signal_bb_alert": False,
            "rsi_interval": "day",
        },
        "exchanges": {"upbit": {"watchlist": ["KRW-BTC"]}},
    }

    class FakeUsers:
        users = {"999": user_data}

    engine = SignalEngine(FakeUsers(), DummyAdapter(_long_candles()))
    app = FakeApp()

    asyncio.run(engine.analyze_watchlist(app))
    assert len(sent) == 1

    # 두 번째 실행 — 스누즈 중이므로 발송 없음
    asyncio.run(engine.analyze_watchlist(app))
    assert len(sent) == 1


def test_analyze_watchlist_sends_again_after_snooze_expires():
    """스누즈 만료 후엔 알람 재발송."""
    sent = []

    class FakeBot:
        async def send_message(self, **kw):
            sent.append(kw)

    class FakeApp:
        bot = FakeBot()

    user_data = {
        "is_active": True,
        "preferences": {
            "signal_alerts": True,
            "signal_rsi_threshold": 80,
            "signal_bb_alert": False,
            "rsi_interval": "day",
        },
        "exchanges": {"upbit": {"watchlist": ["KRW-BTC"]}},
    }

    class FakeUsers:
        users = {"999": user_data}

    engine = SignalEngine(FakeUsers(), DummyAdapter(_long_candles()))
    app = FakeApp()

    asyncio.run(engine.analyze_watchlist(app))
    assert len(sent) == 1

    # 스누즈를 과거로 강제 만료
    engine._alert_snooze[("999", "upbit", "KRW-BTC")] = time.time() - 1

    asyncio.run(engine.analyze_watchlist(app))
    assert len(sent) == 2
