import pandas as pd
import ta
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from core.exchange_adapter import ExchangeAdapter

class SignalEngine:
    def __init__(self, user_manager, exchange_adapter):
        self.user_manager = user_manager
        self.exchange_adapter = exchange_adapter

    async def get_rsi(self, exchange, ticker, interval="day", period=14, user_id=None):
        """특정 종목의 RSI 지표와 데이터프레임 반환"""
        try:
            candles = await self.exchange_adapter.get_candles(exchange, ticker, interval=interval, count=period + 50, user_id=user_id)
            if not candles: return None, None
            df = pd.DataFrame(candles)
            df = df.rename(columns={
                "trade_price": "close", "opening_price": "open", "high_price": "high", "low_price": "low"
            })
            if "candle_date_time_kst" in df.columns:
                df = df.sort_values("candle_date_time_kst")
            
            rsi_series = ta.momentum.RSIIndicator(close=df['close'], window=period).rsi()
            return rsi_series.iloc[-1], df
        except Exception as e:
            print(f"❌ [{exchange.upper()}] {ticker} RSI 계산 오류: {e}")
            return None, None

    async def get_price_by_rsi(self, exchange, ticker, target_rsi, side="bid", interval="day", period=14, user_id=None):
        """목표 RSI에 도달하기 위한 예상 가격 역산 (수수료/슬리피지 보정 포함)"""
        current_rsi, df = await self.get_rsi(exchange, ticker, interval=interval, period=period, user_id=user_id)
        if df is None or len(df) < period: return None

        # Wilder's Smoothing RSI 역산 로직
        close_prices = df['close'].values
        diff = pd.Series(close_prices).diff()
        gain = diff.where(diff > 0, 0)
        loss = -diff.where(diff < 0, 0)

        # 지수 이동 평균(EMA) 방식의 Wilder's Smoothing 사용
        avg_gain = gain.rolling(window=period).mean().iloc[-1]
        avg_loss = loss.rolling(window=period).mean().iloc[-1]

        if avg_loss == 0 and target_rsi < 100: 
            # 하락이 전혀 없었던 경우, 매우 작은 값으로 설정하여 계산 가능케 함
            avg_loss = 1e-9

        target_rs = target_rsi / (100 - target_rsi)
        prev_close = close_prices[-1]

        # RSI 공식: (AvgGain * 13 + currentGain) / (AvgLoss * 13 + currentLoss) = target_rs
        if side == "bid": # 매수 시 (가격 하락 가정, currentGain=0)
            needed_loss = (avg_gain * (period - 1) / target_rs) - (avg_loss * (period - 1))
            target_price = prev_close - needed_loss
        else: # 매도 시 (가격 상승 가정, currentLoss=0)
            needed_gain = (target_rs * avg_loss * (period - 1)) - (avg_gain * (period - 1))
            target_price = prev_close + needed_gain

        # 수수료 및 슬리피지 보정 (매수 시 0.1% 더 낮게, 매도 시 0.1% 더 높게 타겟팅)
        buffer = 0.001 
        if side == "bid":
            target_price *= (1 - buffer)
        else:
            target_price *= (1 + buffer)

        return self.exchange_adapter.adjust_price_to_tick(target_price)

    async def analyze_watchlist(self, application):
        """모든 사용자의 관심 종목을 스캔하여 시그널 감시 (백그라운드 루프용)"""
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
                                f"🔔 *[매수 시그널 포착]*\n\n"
                                f"- 거래소: `{exchange.upper()}`\n"
                                f"- 종목: `{ticker}`\n"
                                f"- 현재 RSI: `{rsi:.2f}` (기준 {threshold:g} 이하)\n\n"
                                f"현재 가격대에서 진입을 고려해 보세요!"
                            )
                            # 퀵 액션 버튼 (매수 유도)
                            keyboard = [[InlineKeyboardButton("🕸️ 거미줄 셋팅하기", callback_data=f"grid_quick_{exchange}_{ticker}")]]
                            reply_markup = InlineKeyboardMarkup(keyboard)
                            await application.bot.send_message(chat_id=user_id, text=msg, reply_markup=reply_markup, parse_mode="Markdown")
                    
                    await asyncio.sleep(0.5) # API Rate Limit 방어
