from abc import ABC, abstractmethod

import pandas as pd
import ta


class BaseIndicator(ABC):
    """캔들 종가 시리즈를 입력받아 신호 값을 반환하는 지표 플러그인 인터페이스."""

    @property
    @abstractmethod
    def name(self) -> str:
        """지표 식별자."""

    @abstractmethod
    def compute(self, closes: pd.Series) -> float:
        """현재 지표 값 계산. closes: 종가 시리즈(float) → 신호 값."""


class RSIIndicator(BaseIndicator):
    """RSI(Relative Strength Index) 지표."""

    def __init__(self, period: int = 14):
        self._period = period

    @property
    def name(self) -> str:
        return "rsi"

    def compute(self, closes: pd.Series) -> float:
        return float(
            ta.momentum.RSIIndicator(close=closes, window=self._period).rsi().iloc[-1]
        )

    def compute_with_next(self, closes: pd.Series, next_close: float) -> float:
        """가상의 다음 종가를 포함해 RSI 계산 (이분 탐색 역산 전용)."""
        extended = pd.concat(
            [closes, pd.Series([float(next_close)])], ignore_index=True
        )
        return self.compute(extended)
