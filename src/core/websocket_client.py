import asyncio
import json
import time
import aiohttp
from core.bot_logger import get_logger

_log = get_logger("websocket_client")

class RealtimeTickerEngine:
    def __init__(self, user_manager):
        self.user_manager = user_manager
        self._tickers = {}  # { (exchange, ticker): {"trade_price": float, "timestamp": float} }
        self._running = False
        self._upbit_task = None
        self._bithumb_task = None
        self._subscribed_upbit = set()
        self._subscribed_bithumb = set()

    def get_price(self, exchange: str, ticker: str) -> float | None:
        """인메모리 실시간 시세 캐시 반환"""
        key = (exchange.lower(), ticker.upper())
        data = self._tickers.get(key)
        if data:
            # 수집된 지 3분 이내인 가격만 신뢰 (웹소켓 정지 대비 안전장치)
            if time.time() - data["timestamp"] < 180:
                return data["trade_price"]
        return None

    def _get_active_watchlists(self):
        """모든 유저들의 watchlist에서 고유한 티커 목록 추출"""
        upbit_list = set()
        bithumb_list = set()
        
        for user in self.user_manager.users.values():
            if not user.get("is_active", True):  # 활성 유저만
                continue
            
            # Upbit watchlist
            up_watch = user.get("exchanges", {}).get("upbit", {}).get("watchlist", [])
            for tk in up_watch:
                upbit_list.add(tk.upper())
                
            # Bithumb watchlist
            bit_watch = user.get("exchanges", {}).get("bithumb", {}).get("watchlist", [])
            for tk in bit_watch:
                bithumb_list.add(tk.upper())
                
        # 기본 감시 종목 강제 편입
        upbit_list.add("KRW-BTC")
        bithumb_list.add("KRW-BTC")
        
        return upbit_list, bithumb_list

    async def _upbit_loop(self):
        url = "wss://api.upbit.com/websocket/v1"
        while self._running:
            try:
                upbit_watch, _ = self._get_active_watchlists()
                self._subscribed_upbit = upbit_watch
                
                if not upbit_watch:
                    await asyncio.sleep(5)
                    continue
                    
                _log.info(f"Connecting to Upbit WebSocket... Subscribing: {list(upbit_watch)}")
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(url) as ws:
                        # 구독 패킷 전송
                        sub_data = [
                            {"ticket": "supabot-realtime-ticker"},
                            {"type": "ticker", "codes": list(upbit_watch)}
                        ]
                        await ws.send_str(json.dumps(sub_data))
                        
                        while self._running:
                            curr_watch, _ = self._get_active_watchlists()
                            if curr_watch != self._subscribed_upbit:
                                _log.info("Upbit watchlist changed. Reconnecting WebSocket to subscribe new tickers...")
                                break
                                
                            try:
                                msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    data = json.loads(msg.data)
                                    self._update_upbit_ticker(data)
                                elif msg.type == aiohttp.WSMsgType.BINARY:
                                    data = json.loads(msg.data.decode('utf-8'))
                                    self._update_upbit_ticker(data)
                                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                    break
                            except asyncio.TimeoutError:
                                continue
            except Exception as e:
                _log.error("Error in Upbit WebSocket loop", exc_info=e)
                await asyncio.sleep(10)

    def _update_upbit_ticker(self, data):
        if not isinstance(data, dict) or "code" not in data or "trade_price" not in data:
            return
        ticker = data["code"]
        price = float(data["trade_price"])
        self._tickers[("upbit", ticker)] = {
            "trade_price": price,
            "timestamp": time.time()
        }

    async def _bithumb_loop(self):
        url = "wss://pubwss.bithumb.com/pub/ws"
        while self._running:
            try:
                _, bithumb_watch = self._get_active_watchlists()
                self._subscribed_bithumb = bithumb_watch
                
                if not bithumb_watch:
                    await asyncio.sleep(5)
                    continue
                
                # 빗썸 포맷으로 심볼 변환: KRW-BTC -> BTC_KRW
                bithumb_symbols = []
                for tk in bithumb_watch:
                    if "-" in tk:
                        base, quote = tk.split("-")
                        bithumb_symbols.append(f"{quote}_{base}")
                
                _log.info(f"Connecting to Bithumb WebSocket... Subscribing: {bithumb_symbols}")
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(url) as ws:
                        sub_data = {
                            "type": "ticker",
                            "symbols": bithumb_symbols,
                            "tickTypes": ["30M"]
                        }
                        await ws.send_str(json.dumps(sub_data))
                        
                        while self._running:
                            _, curr_watch = self._get_active_watchlists()
                            if curr_watch != self._subscribed_bithumb:
                                _log.info("Bithumb watchlist changed. Reconnecting WebSocket to subscribe new tickers...")
                                break
                                
                            try:
                                msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    data = json.loads(msg.data)
                                    self._update_bithumb_ticker(data)
                                elif msg.type == aiohttp.WSMsgType.BINARY:
                                    data = json.loads(msg.data.decode('utf-8'))
                                    self._update_bithumb_ticker(data)
                                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                    break
                            except asyncio.TimeoutError:
                                continue
            except Exception as e:
                _log.error("Error in Bithumb WebSocket loop", exc_info=e)
                await asyncio.sleep(10)

    def _update_bithumb_ticker(self, data):
        if not isinstance(data, dict) or "content" not in data:
            return
        content = data["content"]
        if "symbol" not in content or "closePrice" not in content:
            return
            
        symbol = content["symbol"]
        if "_" in symbol:
            base, quote = symbol.split("_")
            ticker = f"{quote}-{base}"
        else:
            return
            
        price = float(content["closePrice"])
        self._tickers[("bithumb", ticker)] = {
            "trade_price": price,
            "timestamp": time.time()
        }

    def start(self):
        """웹소켓 실시간 엔진 시작"""
        if self._running:
            return
        self._running = True
        self._upbit_task = asyncio.create_task(self._upbit_loop())
        self._bithumb_task = asyncio.create_task(self._bithumb_loop())
        _log.info("Realtime WebSocket Ticker Engine started")

    def stop(self):
        """웹소켓 실시간 엔진 정지"""
        self._running = False
        if self._upbit_task:
            self._upbit_task.cancel()
        if self._bithumb_task:
            self._bithumb_task.cancel()
        _log.info("Realtime WebSocket Ticker Engine stopped")

ticker_engine = None

def init_ticker_engine(user_manager) -> RealtimeTickerEngine:
    global ticker_engine
    if ticker_engine is None:
        ticker_engine = RealtimeTickerEngine(user_manager)
        ticker_engine.start()
    return ticker_engine
