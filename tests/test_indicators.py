import os
import sys

import pandas as pd
import pytest
from pytest import approx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.indicators import RSIIndicator


def _make_closes(n=50, seed_price=100.0):
    """단조 증가 가격으로 간단한 종가 시리즈 생성."""
    prices = [seed_price + i * 0.5 for i in range(n)]
    return pd.Series(prices, dtype=float)


def test_rsi_indicator_name():
    assert RSIIndicator().name == "rsi"


def test_rsi_compute_returns_float_in_valid_range():
    closes = _make_closes(50)
    value = RSIIndicator(period=14).compute(closes)
    assert isinstance(value, float)
    assert 0.0 <= value <= 100.0


def test_rsi_compute_with_next_higher_price_raises_rsi():
    closes = _make_closes(30)
    ind = RSIIndicator(period=14)
    base_rsi = ind.compute(closes)
    # 강한 상승 → RSI 증가
    higher_rsi = ind.compute_with_next(closes, closes.iloc[-1] * 1.05)
    assert higher_rsi >= base_rsi


def test_rsi_compute_with_next_lower_price_lowers_rsi():
    closes = _make_closes(30)
    ind = RSIIndicator(period=14)
    base_rsi = ind.compute(closes)
    # 급락 → RSI 감소
    lower_rsi = ind.compute_with_next(closes, closes.iloc[-1] * 0.90)
    assert lower_rsi <= base_rsi


def test_rsi_period_affects_sensitivity():
    # 상승-하락 반복 시리즈: 주기에 따라 민감도가 달라야 함
    prices = [100 + (i % 5) * 2 - (i % 3) for i in range(60)]
    closes = pd.Series(prices, dtype=float)
    rsi_short = RSIIndicator(period=7).compute(closes)
    rsi_long = RSIIndicator(period=28).compute(closes)
    # 두 지표가 다른 값을 반환해야 함
    assert rsi_short != pytest.approx(rsi_long, abs=0.01)
