import asyncio
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.bot_logger import get_logger
from core.user_manager import is_quiet_hours
from core.indicators import (
    BollingerBandsIndicator,
    MACDIndicator,
    RSIIndicator,
    StochasticIndicator,
)

_log = get_logger("signal_engine")

_KST = timezone(timedelta(hours=9))


def _next_midnight_kst() -> float:
    now = datetime.now(_KST)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


def _rename_candle_df(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={
        "trade_price": "close",
        "opening_price": "open",
        "high_price": "high",
        "low_price": "low",
    })


class SignalEngine:
    def __init__(self, user_manager, exchange_adapter):
        self.user_manager = user_manager
        self.exchange_adapter = exchange_adapter
        self._alert_snooze: dict[tuple[str, str, str], float] = {}

    def set_snooze(self, user_id: str, exchange: str, ticker: str, mode: str) -> float:
        """mode: '1h' | '2h' | 'day' — 스누즈 만료 unix timestamp 반환"""
        if mode == "1h":
            expires = time.time() + 3600
        elif mode == "2h":
            expires = time.time() + 7200
        else:
            expires = _next_midnight_kst()
        self._alert_snooze[(user_id, exchange, ticker)] = expires
        return expires

    async def get_rsi(self, exchange, ticker, interval="day", period=14, user_id=None):
        """Return the latest RSI and candle dataframe for a market."""
        # KIS는 분봉 미지원 — 사용자 설정이 분봉이더라도 일봉으로 자동 폴백
        if exchange == "kis" and interval != "day":
            interval = "day"
        try:
            candles = await self.exchange_adapter.get_candles(
                exchange,
                ticker,
                interval=interval,
                count=period + 50,
                user_id=user_id,
            )
            if not candles:
                return None, None
            df = _rename_candle_df(pd.DataFrame(candles))
            if "candle_date_time_kst" in df.columns:
                df = df.sort_values("candle_date_time_kst")

            closes = df["close"].astype(float).reset_index(drop=True)
            rsi_value = RSIIndicator(period=period).compute(closes)
            return rsi_value, df
        except Exception as e:
            _log.error("RSI calculation error", exc_info=e, extra={"event": "rsi_error", "exchange": exchange, "ticker": ticker})
            return None, None

    async def get_indicators(self, exchange, ticker, interval="day", user_id=None):
        """Return RSI, MACD, Bollinger Bands, Stochastic for a market.

        Returns a dict with keys: rsi, macd, bbands, stoch, current_price, interval.
        Returns None if candle data is unavailable.
        """
        if exchange == "kis" and interval != "day":
            interval = "day"
        try:
            candles = await self.exchange_adapter.get_candles(
                exchange, ticker, interval=interval, count=100, user_id=user_id
            )
            if not candles:
                return None
            df = _rename_candle_df(pd.DataFrame(candles))
            if "candle_date_time_kst" in df.columns:
                df = df.sort_values("candle_date_time_kst")
            df = df.reset_index(drop=True)

            return {
                "rsi": RSIIndicator(period=14).compute(df["close"]),
                "macd": MACDIndicator().compute(df["close"]),
                "bbands": BollingerBandsIndicator().compute(df["close"]),
                "stoch": StochasticIndicator().compute_ohlcv(df),
                "current_price": float(df["close"].astype(float).iloc[-1]),
                "interval": interval,
            }
        except Exception as e:
            _log.error("Indicator calculation error", exc_info=e, extra={"event": "indicator_error", "exchange": exchange, "ticker": ticker})
            return None

    @staticmethod
    def _calculate_rsi_for_next_close(close_series, next_close, period):
        return RSIIndicator(period=period).compute_with_next(close_series, next_close)

    def _search_price_for_target_rsi(self, close_series, current_price, current_rsi, target_rsi, side, period):
        if side == "bid":
            if target_rsi >= current_rsi:
                return current_price
            high = current_price
            low = current_price * 0.98
            low_rsi = self._calculate_rsi_for_next_close(close_series, low, period)
            while low > 1 and low_rsi > target_rsi:
                low *= 0.98
                low_rsi = self._calculate_rsi_for_next_close(close_series, low, period)
            for _ in range(32):
                mid = (low + high) / 2
                mid_rsi = self._calculate_rsi_for_next_close(close_series, mid, period)
                if mid_rsi <= target_rsi:
                    low = mid
                else:
                    high = mid
            return low

        if target_rsi <= current_rsi:
            return current_price
        low = current_price
        high = current_price * 1.02
        high_rsi = self._calculate_rsi_for_next_close(close_series, high, period)
        while high_rsi < target_rsi:
            high *= 1.02
            high_rsi = self._calculate_rsi_for_next_close(close_series, high, period)
        for _ in range(32):
            mid = (low + high) / 2
            mid_rsi = self._calculate_rsi_for_next_close(close_series, mid, period)
            if mid_rsi >= target_rsi:
                high = mid
            else:
                low = mid
        return high

    async def get_price_by_rsi(self, exchange, ticker, target_rsi, side="bid", interval="day", period=14, user_id=None):
        """Estimate the next-close price that would place RSI near the target."""
        current_rsi, df = await self.get_rsi(
            exchange,
            ticker,
            interval=interval,
            period=period,
            user_id=user_id,
        )
        if current_rsi is None or df is None or len(df) < period:
            return None

        close_series = df["close"].astype(float).reset_index(drop=True)
        current_price = float(close_series.iloc[-1])
        target_price = self._search_price_for_target_rsi(
            close_series,
            current_price,
            float(current_rsi),
            float(target_rsi),
            side,
            period,
        )

        buffer = 0.001
        if side == "bid":
            target_price *= 1 - buffer
        else:
            target_price *= 1 + buffer

        return self.exchange_adapter.adjust_price_to_tick(target_price)

    async def analyze_watchlist(self, application):
        """Scan watchlists and send alerts based on RSI and (optionally) Bollinger Bands."""
        users = self.user_manager.users
        for user_id, user_data in users.items():
            if not user_data.get("is_active") or not user_data["preferences"].get("signal_alerts"):
                continue

            for exchange, ex_data in user_data.get("exchanges", {}).items():
                watchlist = ex_data.get("watchlist", [])
                for ticker in watchlist:
                    interval = user_data["preferences"].get("rsi_interval", "day")
                    threshold = float(user_data["preferences"].get("signal_rsi_threshold", 30))
                    use_bb = user_data["preferences"].get("signal_bb_alert", False)

                    indicators = await self.get_indicators(exchange, ticker, interval=interval, user_id=user_id)
                    if indicators is None:
                        await asyncio.sleep(0.5)
                        continue

                    rsi = indicators["rsi"]
                    bb = indicators["bbands"]
                    current_price = indicators["current_price"]

                    rsi_triggered = rsi <= threshold
                    bb_triggered = use_bb and current_price < bb.lower

                    snooze_key = (user_id, exchange, ticker)
                    if self._alert_snooze.get(snooze_key, 0) > time.time():
                        await asyncio.sleep(0.5)
                        continue

                    if (rsi_triggered or bb_triggered) and not is_quiet_hours(user_data):
                        reasons = []
                        if rsi_triggered:
                            reasons.append(f"RSI {rsi:.2f} ≤ {threshold:g}")
                        if bb_triggered:
                            reasons.append(f"종가 {current_price:,.0f} < BB하단 {bb.lower:,.0f}")

                        msg = (
                            f"🔔 <b>[{exchange.upper()}] 매수 시그널</b>\n\n"
                            f"🔹 종목: {ticker}\n"
                            f"🔹 조건: {' / '.join(reasons)}\n\n"
                            "💡 현재 가격대에서 진입을 고려해 보세요!"
                        )
                        keyboard = [
                            [InlineKeyboardButton("🕸️ 거미줄 셋팅하기", callback_data=f"grid_quick_{exchange}_{ticker}")],
                            [
                                InlineKeyboardButton("⏰ 1시간 스누즈", callback_data=f"signal_snooze_1h_{exchange}_{ticker}"),
                                InlineKeyboardButton("⏰ 2시간 스누즈", callback_data=f"signal_snooze_2h_{exchange}_{ticker}"),
                                InlineKeyboardButton("🌙 오늘 하루", callback_data=f"signal_snooze_day_{exchange}_{ticker}"),
                            ],
                        ]
                        await application.bot.send_message(
                            chat_id=user_id,
                            text=msg,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                        )
                        self._alert_snooze[snooze_key] = _next_midnight_kst()

                    await asyncio.sleep(0.5)
