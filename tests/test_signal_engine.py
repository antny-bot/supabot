import asyncio
import os
import sys

import pandas as pd
import ta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.signal_engine import SignalEngine


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
