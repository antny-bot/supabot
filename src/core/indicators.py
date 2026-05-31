from abc import ABC, abstractmethod
from typing import Any, NamedTuple

import pandas as pd
import ta


class BaseIndicator(ABC):
    """캔들 데이터를 입력받아 신호 값을 반환하는 지표 플러그인 인터페이스."""

    @property
    @abstractmethod
    def name(self) -> str:
        """지표 식별자."""

    @abstractmethod
    def compute(self, closes: pd.Series) -> Any:
        """종가 시리즈만으로 지표 계산."""

    def compute_ohlcv(self, df: pd.DataFrame) -> Any:
        """OHLCV DataFrame으로 지표 계산. 기본 구현은 compute(df['close'])로 위임."""
        return self.compute(df["close"].astype(float))


# ── RSI ──────────────────────────────────────────────────────────────────────

class RSIIndicator(BaseIndicator):
    """RSI(Relative Strength Index) 지표."""

    def __init__(self, period: int = 14):
        self._period = period

    @property
    def name(self) -> str:
        return "rsi"

    def compute(self, closes: pd.Series) -> float:
        return float(
            ta.momentum.RSIIndicator(close=closes.astype(float), window=self._period).rsi().iloc[-1]
        )

    def compute_with_next(self, closes: pd.Series, next_close: float) -> float:
        """가상의 다음 종가를 포함해 RSI 계산 (이분 탐색 역산 전용)."""
        extended = pd.concat(
            [closes, pd.Series([float(next_close)])], ignore_index=True
        )
        return self.compute(extended)


# ── MACD ─────────────────────────────────────────────────────────────────────

class MACDResult(NamedTuple):
    macd: float
    signal: float
    histogram: float


class MACDIndicator(BaseIndicator):
    """MACD(Moving Average Convergence Divergence) 지표."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self._fast = fast
        self._slow = slow
        self._signal = signal

    @property
    def name(self) -> str:
        return "macd"

    def compute(self, closes: pd.Series) -> MACDResult:
        ind = ta.trend.MACD(
            close=closes.astype(float),
            window_fast=self._fast,
            window_slow=self._slow,
            window_sign=self._signal,
        )
        return MACDResult(
            macd=float(ind.macd().iloc[-1]),
            signal=float(ind.macd_signal().iloc[-1]),
            histogram=float(ind.macd_diff().iloc[-1]),
        )


# ── Bollinger Bands ──────────────────────────────────────────────────────────

class BollingerResult(NamedTuple):
    upper: float
    middle: float
    lower: float
    width_pct: float  # (upper - lower) / middle * 100


class BollingerBandsIndicator(BaseIndicator):
    """볼린저 밴드(Bollinger Bands) 지표."""

    def __init__(self, period: int = 20, std: float = 2.0):
        self._period = period
        self._std = std

    @property
    def name(self) -> str:
        return "bbands"

    def compute(self, closes: pd.Series) -> BollingerResult:
        ind = ta.volatility.BollingerBands(
            close=closes.astype(float), window=self._period, window_dev=self._std
        )
        upper = float(ind.bollinger_hband().iloc[-1])
        middle = float(ind.bollinger_mavg().iloc[-1])
        lower = float(ind.bollinger_lband().iloc[-1])
        width_pct = (upper - lower) / middle * 100 if middle else 0.0
        return BollingerResult(upper=upper, middle=middle, lower=lower, width_pct=width_pct)


# ── Stochastic ───────────────────────────────────────────────────────────────

class StochasticResult(NamedTuple):
    k: float   # %K
    d: float   # %D (signal)


class StochasticIndicator(BaseIndicator):
    """스토캐스틱(Stochastic Oscillator) 지표."""

    def __init__(self, k_period: int = 14, d_period: int = 3, smooth_k: int = 3):
        self._k = k_period
        self._d = d_period
        self._smooth_k = smooth_k

    @property
    def name(self) -> str:
        return "stochastic"

    def compute(self, closes: pd.Series) -> StochasticResult:
        """종가만 사용하는 근사 계산 (high=close, low=close 처리)."""
        c = closes.astype(float)
        return self._stoch(high=c, low=c, close=c)

    def compute_ohlcv(self, df: pd.DataFrame) -> StochasticResult:
        """OHLCV DataFrame으로 정확한 Stochastic 계산."""
        close = df["close"].astype(float)
        high = df["high"].astype(float) if "high" in df.columns else close
        low = df["low"].astype(float) if "low" in df.columns else close
        return self._stoch(high=high, low=low, close=close)

    def _stoch(self, high: pd.Series, low: pd.Series, close: pd.Series) -> StochasticResult:
        ind = ta.momentum.StochasticOscillator(
            high=high, low=low, close=close,
            window=self._k, smooth_window=self._smooth_k,
        )
        return StochasticResult(
            k=float(ind.stoch().iloc[-1]),
            d=float(ind.stoch_signal().iloc[-1]),
        )
