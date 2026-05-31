import os
import sys

import pandas as pd
import pytest
from pytest import approx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.indicators import (
    BollingerBandsIndicator,
    BollingerResult,
    MACDIndicator,
    MACDResult,
    RSIIndicator,
    StochasticIndicator,
    StochasticResult,
)


def _make_closes(n=60, seed=100.0):
    prices = [seed + (i % 5) * 2 - (i % 3) for i in range(n)]
    return pd.Series(prices, dtype=float)


def _make_ohlcv(n=60):
    closes = _make_closes(n)
    df = pd.DataFrame({
        "close": closes,
        "open": closes * 0.999,
        "high": closes * 1.005,
        "low": closes * 0.995,
    })
    return df


# ── RSI ──────────────────────────────────────────────────────────────────────

def test_rsi_indicator_name():
    assert RSIIndicator().name == "rsi"


def test_rsi_compute_returns_float_in_valid_range():
    value = RSIIndicator(period=14).compute(_make_closes(50))
    assert isinstance(value, float)
    assert 0.0 <= value <= 100.0


def test_rsi_compute_with_next_higher_price_raises_rsi():
    closes = _make_closes(30)
    ind = RSIIndicator(period=14)
    base_rsi = ind.compute(closes)
    assert ind.compute_with_next(closes, closes.iloc[-1] * 1.05) >= base_rsi


def test_rsi_compute_with_next_lower_price_lowers_rsi():
    closes = _make_closes(30)
    ind = RSIIndicator(period=14)
    base_rsi = ind.compute(closes)
    assert ind.compute_with_next(closes, closes.iloc[-1] * 0.90) <= base_rsi


def test_rsi_period_affects_sensitivity():
    closes = _make_closes(60)
    assert RSIIndicator(period=7).compute(closes) != approx(RSIIndicator(period=28).compute(closes), abs=0.01)


# ── MACD ─────────────────────────────────────────────────────────────────────

def test_macd_indicator_name():
    assert MACDIndicator().name == "macd"


def test_macd_compute_returns_named_tuple():
    result = MACDIndicator().compute(_make_closes(60))
    assert isinstance(result, MACDResult)


def test_macd_histogram_equals_macd_minus_signal():
    r = MACDIndicator().compute(_make_closes(60))
    assert r.histogram == approx(r.macd - r.signal, abs=1e-6)


def test_macd_compute_ohlcv_matches_compute():
    """OHLCV DataFrame의 기본 compute_ohlcv는 종가만으로 계산한 결과와 동일해야 함."""
    df = _make_ohlcv(60)
    r_close = MACDIndicator().compute(df["close"])
    r_ohlcv = MACDIndicator().compute_ohlcv(df)
    assert r_close.macd == approx(r_ohlcv.macd, abs=1e-6)


def test_macd_fast_slow_param_affects_result():
    closes = _make_closes(60)
    r1 = MACDIndicator(fast=12, slow=26).compute(closes)
    r2 = MACDIndicator(fast=5, slow=13).compute(closes)
    assert r1.macd != approx(r2.macd, abs=1e-6)


# ── Bollinger Bands ──────────────────────────────────────────────────────────

def test_bbands_indicator_name():
    assert BollingerBandsIndicator().name == "bbands"


def test_bbands_compute_returns_named_tuple():
    result = BollingerBandsIndicator().compute(_make_closes(60))
    assert isinstance(result, BollingerResult)


def test_bbands_upper_greater_than_lower():
    r = BollingerBandsIndicator().compute(_make_closes(60))
    assert r.upper > r.lower


def test_bbands_middle_between_upper_and_lower():
    r = BollingerBandsIndicator().compute(_make_closes(60))
    assert r.lower <= r.middle <= r.upper


def test_bbands_width_pct_positive():
    r = BollingerBandsIndicator().compute(_make_closes(60))
    assert r.width_pct > 0


def test_bbands_wider_std_gives_wider_band():
    closes = _make_closes(60)
    r1 = BollingerBandsIndicator(std=1.0).compute(closes)
    r2 = BollingerBandsIndicator(std=2.0).compute(closes)
    assert r2.upper - r2.lower > r1.upper - r1.lower


# ── Stochastic ───────────────────────────────────────────────────────────────

def test_stochastic_indicator_name():
    assert StochasticIndicator().name == "stochastic"


def test_stochastic_compute_returns_named_tuple():
    result = StochasticIndicator().compute(_make_closes(60))
    assert isinstance(result, StochasticResult)


def test_stochastic_k_in_valid_range():
    result = StochasticIndicator().compute(_make_closes(60))
    assert 0.0 <= result.k <= 100.0


def test_stochastic_d_in_valid_range():
    result = StochasticIndicator().compute(_make_closes(60))
    assert 0.0 <= result.d <= 100.0


def test_stochastic_compute_ohlcv_returns_named_tuple():
    result = StochasticIndicator().compute_ohlcv(_make_ohlcv(60))
    assert isinstance(result, StochasticResult)


def test_stochastic_ohlcv_k_in_valid_range():
    result = StochasticIndicator().compute_ohlcv(_make_ohlcv(60))
    assert 0.0 <= result.k <= 100.0


# ── BaseIndicator interface ───────────────────────────────────────────────────

def test_base_indicator_compute_ohlcv_default_delegates_to_compute():
    """RSIIndicator는 compute_ohlcv 오버라이드가 없으므로 기본 위임이 동작해야 함."""
    df = _make_ohlcv(50)
    r_direct = RSIIndicator(period=14).compute(df["close"])
    r_ohlcv = RSIIndicator(period=14).compute_ohlcv(df)
    assert r_direct == approx(r_ohlcv, abs=1e-6)
