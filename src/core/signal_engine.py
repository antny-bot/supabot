import asyncio

import pandas as pd
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.indicators import RSIIndicator


class SignalEngine:
    def __init__(self, user_manager, exchange_adapter):
        self.user_manager = user_manager
        self.exchange_adapter = exchange_adapter

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
            df = pd.DataFrame(candles)
            df = df.rename(
                columns={
                    "trade_price": "close",
                    "opening_price": "open",
                    "high_price": "high",
                    "low_price": "low",
                }
            )
            if "candle_date_time_kst" in df.columns:
                df = df.sort_values("candle_date_time_kst")

            closes = df["close"].astype(float).reset_index(drop=True)
            rsi_value = RSIIndicator(period=period).compute(closes)
            return rsi_value, df
        except Exception as e:
            print(f"❌ [{exchange.upper()}] {ticker} RSI 계산 오류: {e}")
            return None, None

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
        """Scan watchlists and send alerts for oversold RSI levels."""
        users = self.user_manager.users
        for user_id, user_data in users.items():
            if not user_data.get("is_active") or not user_data["preferences"].get("signal_alerts"):
                continue

            for exchange, ex_data in user_data.get("exchanges", {}).items():
                watchlist = ex_data.get("watchlist", [])
                for ticker in watchlist:
                    interval = user_data["preferences"].get("rsi_interval", "day")
                    rsi, _ = await self.get_rsi(exchange, ticker, interval=interval, user_id=user_id)

                    if rsi is not None:
                        threshold = float(user_data["preferences"].get("signal_rsi_threshold", 30))
                        if rsi <= threshold:
                            msg = (
                                f"🔔 매수 시그널 포착\n\n"
                                f"- 거래소: {exchange.upper()}\n"
                                f"- 종목: {ticker}\n"
                                f"- 현재 RSI: {rsi:.2f} (기준 {threshold:g} 이하)\n\n"
                                "현재 가격대에서 진입을 고려해 보세요!"
                            )
                            keyboard = [[InlineKeyboardButton("🕸️ 거미줄 셋팅하기", callback_data=f"grid_quick_{exchange}_{ticker}")]]
                            reply_markup = InlineKeyboardMarkup(keyboard)
                            await application.bot.send_message(
                                chat_id=user_id,
                                text=msg,
                                reply_markup=reply_markup,
                            )

                    await asyncio.sleep(0.5)
