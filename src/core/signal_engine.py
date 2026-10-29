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

    def clean_expired_snoozes(self):
        """만료된 스누즈 항목을 정리하여 메모리 누수를 방지한다."""
        now = time.time()
        expired = [k for k, exp in self._alert_snooze.items() if exp <= now]
        for k in expired:
            self._alert_snooze.pop(k, None)

    def set_snooze(self, user_id: str, exchange: str, ticker: str, mode: str) -> float:
        """mode: '1h' | '2h' | 'day' — 스누즈 만료 unix timestamp 반환"""
        self.clean_expired_snoozes()
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
        # 분봉 미지원 거래소(KIS)는 사용자 설정이 분봉이더라도 일봉으로 자동 폴백
        if not self.exchange_adapter.get_exchange(exchange).supports_minute_candles() and interval != "day":
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
        if not self.exchange_adapter.get_exchange(exchange).supports_minute_candles() and interval != "day":
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

            closes = df["close"].astype(float)
            return {
                "rsi": RSIIndicator(period=14).compute(closes),
                "macd": MACDIndicator().compute(closes),
                "bbands": BollingerBandsIndicator().compute(closes),
                "stoch": StochasticIndicator().compute_ohlcv(df),
                "current_price": float(closes.iloc[-1]),
                "interval": interval,
                "ma7":  float(closes.iloc[-7:].mean())  if len(closes) >= 7  else None,
                "ma14": float(closes.iloc[-14:].mean()) if len(closes) >= 14 else None,
                "ma30": float(closes.iloc[-30:].mean()) if len(closes) >= 30 else None,
                "ma90": float(closes.iloc[-90:].mean()) if len(closes) >= 90 else None,
            }
        except Exception as e:
            _log.error("Indicator calculation error", exc_info=e, extra={"event": "indicator_error", "exchange": exchange, "ticker": ticker})
            return None

    @staticmethod
    def _calculate_rsi_for_next_close(close_series, next_close, period):
        return RSIIndicator(period=period).compute_with_next(close_series, next_close)

    def _search_price_for_target_rsi(self, close_series, current_price, current_rsi, target_rsi, side, period):
        # 1. 고속 대수적 역산 (Wilder's Smoothing Inverse) 시도
        try:
            if side == "bid" and target_rsi >= current_rsi:
                return current_price
            if side == "ask" and target_rsi <= current_rsi:
                return current_price

            diffs = close_series.diff().dropna()
            gains = diffs.clip(lower=0)
            losses = (-diffs.clip(upper=0))

            avg_gain = gains.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean().iloc[-1]
            avg_loss = losses.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean().iloc[-1]

            target_rs = float(target_rsi) / (100.0 - float(target_rsi)) if float(target_rsi) < 100 else 1e9

            if side == "bid":
                req_loss = ((period - 1) * avg_gain) / target_rs - (period - 1) * avg_loss
                if req_loss > 0:
                    est_price = current_price - req_loss
                    if 0 < est_price <= current_price:
                        check_rsi = self._calculate_rsi_for_next_close(close_series, est_price, period)
                        if abs(check_rsi - target_rsi) <= 1.0:
                            return est_price
            else:
                req_gain = target_rs * (period - 1) * avg_loss - (period - 1) * avg_gain
                if req_gain > 0:
                    est_price = current_price + req_gain
                    if est_price >= current_price:
                        check_rsi = self._calculate_rsi_for_next_close(close_series, est_price, period)
                        if abs(check_rsi - target_rsi) <= 1.0:
                            return est_price
        except Exception as e:
            _log.debug("RSI algebraic inverse failed: %s", e)

        # 2. 안전 폴백: 이분 탐색 (무한 루프 방지 및 경계 한도)
        if side == "bid":
            if target_rsi >= current_rsi:
                return current_price
            high = current_price
            low = current_price * 0.98
            low_limit = max(current_price * 1e-4, 1e-8)
            low_rsi = self._calculate_rsi_for_next_close(close_series, low, period)
            iterations = 0
            while low > low_limit and low_rsi > target_rsi and iterations < 200:
                low *= 0.98
                low_rsi = self._calculate_rsi_for_next_close(close_series, low, period)
                iterations += 1
            if low_rsi > target_rsi:
                _log.debug("Target RSI %s unreachable for bid within bounds", target_rsi)
                return None
            for _ in range(24):
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
        high_limit = current_price * 10.0
        high_rsi = self._calculate_rsi_for_next_close(close_series, high, period)
        iterations = 0
        while high < high_limit and high_rsi < target_rsi and iterations < 200:
            high *= 1.02
            high_rsi = self._calculate_rsi_for_next_close(close_series, high, period)
            iterations += 1
        if high_rsi < target_rsi:
            _log.debug("Target RSI %s unreachable for ask within bounds", target_rsi)
            return None
        for _ in range(24):
            mid = (low + high) / 2
            mid_rsi = self._calculate_rsi_for_next_close(close_series, mid, period)
            if mid_rsi >= target_rsi:
                high = mid
            else:
                low = mid
        return high

    async def get_prices_by_rsi(self, exchange, ticker, target_rsis: list[float], side="bid", interval="day", period=14, user_id=None) -> list[float | None]:
        """Estimate prices for multiple RSI targets by fetching candles once (P1 batch)."""
        current_rsi, df = await self.get_rsi(
            exchange,
            ticker,
            interval=interval,
            period=period,
            user_id=user_id,
        )
        if current_rsi is None or df is None or len(df) < period:
            return [None] * len(target_rsis)

        close_series = df["close"].astype(float).reset_index(drop=True)
        current_price = float(close_series.iloc[-1])
        ex_obj = self.exchange_adapter.get_exchange(exchange)

        prices = []
        for target_rsi in target_rsis:
            target_price = self._search_price_for_target_rsi(
                close_series,
                current_price,
                float(current_rsi),
                float(target_rsi),
                side,
                period,
            )
            if target_price is None:
                prices.append(None)
                continue

            buffer = 0.001
            if side == "bid":
                target_price *= 1 - buffer
            else:
                target_price *= 1 + buffer

            prices.append(ex_obj.adjust_price_to_tick(target_price, ticker))
        return prices

    async def get_price_by_rsi(self, exchange, ticker, target_rsi, side="bid", interval="day", period=14, user_id=None, _precomputed=None):
        """Estimate the next-close price that would place RSI near the target."""
        if _precomputed is not None:
            current_rsi, df = _precomputed
        else:
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
        if target_price is None:
            return None

        buffer = 0.001
        if side == "bid":
            target_price *= 1 - buffer
        else:
            target_price *= 1 + buffer

        return self.exchange_adapter.get_exchange(exchange).adjust_price_to_tick(target_price, ticker)

    async def analyze_watchlist(self, application):
        """Scan watchlists and send alerts based on RSI and (optionally) Bollinger Bands."""
        self.clean_expired_snoozes()
        users = self.user_manager.users
        tasks = []
        sem = asyncio.Semaphore(3)  # Rate Limit 방지를 위한 동시 호출 세마포어

        cycle_cache = {}

        async def analyze_single_ticker(user_id, user_data, exchange, ticker):
            async with sem:
                interval = user_data["preferences"].get("rsi_interval", "day")
                threshold = float(user_data["preferences"].get("signal_rsi_threshold", 30))
                use_bb = user_data["preferences"].get("signal_bb_alert", False)

                cache_key = (exchange, ticker, interval)
                if cache_key not in cycle_cache:
                    cycle_cache[cache_key] = await self.get_indicators(exchange, ticker, interval=interval, user_id=user_id)
                indicators = cycle_cache.get(cache_key)
                if indicators is None:
                    return

                rsi = indicators["rsi"]
                bb = indicators["bbands"]
                current_price = indicators["current_price"]

                rsi_triggered = rsi <= threshold
                bb_triggered = use_bb and current_price < bb.lower

                snooze_key = (user_id, exchange, ticker)
                if self._alert_snooze.get(snooze_key, 0) > time.time():
                    return

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

        for user_id, user_data in users.items():
            if not user_data.get("is_active") or not user_data["preferences"].get("signal_alerts"):
                continue

            for exchange, ex_data in user_data.get("exchanges", {}).items():
                watchlist = ex_data.get("watchlist", [])
                for ticker in watchlist:
                    tasks.append(analyze_single_ticker(user_id, user_data, exchange, ticker))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
