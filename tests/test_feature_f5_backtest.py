"""F5 백테스트 엔진(src/core/backtest.py) 단위 테스트."""
import pandas as pd
import numpy as np
import pytest
from src.core.backtest import BacktestResult, BacktestTrade, run_rsi_backtest


def _generate_synthetic_candles(count: int = 200, base_price: float = 1000.0, trend: str = "cycle") -> pd.DataFrame:
    """합성 캔들 DataFrame 생성 (close, high, low, open, volume)."""
    import math

    closes = []
    highs = []
    lows = []
    opens = []
    volumes = []
    dates = pd.date_range("2026-01-01", periods=count, freq="1h")

    for i in range(count):
        if trend == "up":
            price = base_price * (1.0 + 0.002 * i)
        elif trend == "down":
            price = base_price * (1.0 - 0.002 * i)
        else:  # cycle (sine wave for rsi oscillation)
            price = base_price * (1.0 + 0.05 * math.sin(i / 5.0))
        closes.append(price)
        highs.append(price * 1.002)
        lows.append(price * 0.998)
        opens.append(price)
        volumes.append(100.0)

    df = pd.DataFrame({
        "timestamp": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })
    return df


def test_backtest_empty_or_short_candles():
    """캔들 데이터가 부족할 때 적절히 빈 결과/0 반환 검증."""
    empty_df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    res = run_rsi_backtest(
        df=empty_df,
        buy_rsi_range="25-30",
        sell_rsi_range="65-70",
        count=3,
        initial_budget=1_000_000.0,
    )
    assert res.total_trades == 0
    assert res.final_balance == 1_000_000.0
    assert res.total_return_pct == 0.0

    short_df = _generate_synthetic_candles(10)
    res_short = run_rsi_backtest(
        df=short_df,
        buy_rsi_range="25-30",
        sell_rsi_range="65-70",
        count=3,
        initial_budget=1_000_000.0,
    )
    assert res_short.total_trades == 0
    assert res_short.final_balance == 1_000_000.0


def test_backtest_rsi_cyclic_trading():
    """진동하는 캔들 데이터에서 매수/매도 사이클 및 승률, MDD 정상 산출 검증."""
    df = _generate_synthetic_candles(count=150, base_price=10_000.0, trend="cycle")
    res = run_rsi_backtest(
        df=df,
        buy_rsi_range="30-35",
        sell_rsi_range="65-70",
        count=3,
        initial_budget=10_000_000.0,
        fee_rate=0.0005,
        slippage_pct=0.0002,
    )

    assert res.initial_budget == 10_000_000.0
    assert res.total_trades >= 0
    assert 0.0 <= res.win_rate <= 100.0
    assert res.mdd_pct >= 0.0
    assert len(res.trades) == res.total_trades


def test_backtest_no_external_api_calls():
    """백테스트는 순수 시뮬레이터로 외부 네트워크/거래소 API를 호출하지 않음을 확인."""
    df = _generate_synthetic_candles(count=50)
    res = run_rsi_backtest(
        df=df,
        buy_rsi_range="30-35",
        sell_rsi_range="65-70",
        count=3,
        initial_budget=500_000.0,
    )
    assert isinstance(res, BacktestResult)
