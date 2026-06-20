import time

from core.bot_logger import get_logger
from core.metrics import metrics
from core.stock_resolver import is_kr_stock_name, resolve_kr_stock_name
from core.exchanges.common import CommonMixin
from core.exchanges.upbit import UpbitMixin, UpbitExchange
from core.exchanges.bithumb import BithumbMixin, BithumbExchange
from core.exchanges.toss import TossMixin, TossExchange
from core.exchanges.kis import KisMixin, KisExchange

_log = get_logger("exchange_adapter")


class ExchangeAdapter(CommonMixin, UpbitMixin, BithumbMixin, TossMixin, KisMixin):
    _CANDLE_TTL = {"day": 300, "default": 60}  # 일봉 5분, 분봉 1분

    def __init__(self, user_manager):
        self.user_manager = user_manager
        self._bithumb_session = None
        self._kis_session = None
        self._upbit_session = None
        self._toss_session = None
        self._kis_tokens = {}
        self._toss_tokens = {}
        self._candle_cache = {}  # {(exchange, ticker, interval, count): (fetched_at, candles)}
        self._exchanges = {
            "upbit": UpbitExchange(self),
            "bithumb": BithumbExchange(self),
            "kis": KisExchange(self),
            "toss": TossExchange(self),
        }

    def get_exchange(self, exchange):
        """거래소별 capability/동작을 캡슐화한 Exchange 객체 반환."""
        return self._exchanges.get(exchange)

    async def close(self):
        """장시간 실행 중 생성한 HTTP 세션을 정상 종료합니다."""
        if self._bithumb_session and not self._bithumb_session.closed:
            await self._bithumb_session.close()
        self._bithumb_session = None
        if self._kis_session and not self._kis_session.closed:
            await self._kis_session.close()
        self._kis_session = None
        if self._upbit_session and not self._upbit_session.closed:
            await self._upbit_session.close()
        self._upbit_session = None
        if self._toss_session and not self._toss_session.closed:
            await self._toss_session.close()
        self._toss_session = None

    def _get_client(self, user_id, exchange):
        """유저의 API 키를 사용하여 거래소 키 정보 반환"""
        user = self.user_manager.get_user(user_id)
        if not user or exchange not in user["exchanges"]:
            return None

        keys = user["exchanges"][exchange]
        if exchange == "kis":
            app_key = keys.get("app_key")
            app_secret = keys.get("app_secret")
            account_no = keys.get("account_no")
            product_code = keys.get("product_code")
            if not app_key or not app_secret or not account_no or not product_code:
                return None
            return keys

        if exchange == "toss":
            if not keys.get("client_id") or not keys.get("client_secret"):
                return None
            return keys

        access = keys.get("access_key")
        secret = keys.get("secret_key")

        if not access or not secret:
            return None

        return keys

    async def resolve_ticker(self, user_id: str, exchange: str, ticker: str) -> str:
        """KIS·Toss 거래소에서 한글 종목명을 종목코드로 변환. 나머지는 그대로 반환."""
        if exchange in ("kis", "toss") and is_kr_stock_name(ticker):
            code = await resolve_kr_stock_name(ticker, self, user_id, exchange)
            if code:
                return code
        return ticker

    async def _resolve(self, user_id: str, exchange: str, ticker: str) -> str:
        """내부 편의 메서드 — resolve_ticker 단축 호출."""
        return await self.resolve_ticker(user_id, exchange, ticker)

    async def get_balances(self, user_id, exchange):
        """유저별 특정 거래소의 잔고 조회"""
        client = self._get_client(user_id, exchange)
        if not client:
            return None
        return await self._exchanges[exchange].get_balances(user_id, client)

    async def create_order(self, user_id, exchange, ticker, side, price, volume, ord_type="limit"):
        """지정가/시장가 매수 및 매도 주문 생성"""
        ticker = await self._resolve(user_id, exchange, ticker)
        client = self._get_client(user_id, exchange)
        if not client:
            return None

        side = "bid" if side in ["bid", "buy", "매수"] else "ask"

        result = await self._exchanges[exchange].create_order(
            user_id, client, ticker, side, price, volume, ord_type=ord_type
        )

        ok = bool(result and "uuid" in result)
        metrics.record_order(exchange, ok)
        return result

    async def buy_limit_order(self, user_id, exchange, ticker, price, volume):
        """기존 코드 호환성을 위해 유지 (매수 전용)"""
        return await self.create_order(user_id, exchange, ticker, "bid", price, volume)

    async def cancel_order(self, user_id, exchange, order_id, ticker=None):
        """주문 취소"""
        if ticker and exchange in ("kis", "toss"):
            ticker = await self._resolve(user_id, exchange, ticker)
        client = self._get_client(user_id, exchange)
        if not client:
            return False
        return await self._exchanges[exchange].cancel_order(user_id, client, order_id, ticker=ticker)

    async def get_order_status(self, user_id, exchange, order_id, ticker=None):
        """주문 상세 정보 조회 및 상태 정규화"""
        if ticker and exchange in ("kis", "toss"):
            ticker = await self._resolve(user_id, exchange, ticker)
        client = self._get_client(user_id, exchange)
        if not client:
            return None
        return await self._exchanges[exchange].get_order_status(user_id, client, order_id, ticker=ticker)

    def get_min_order_amount(self, exchange):
        """거래소별 최소 주문 원화(KRW) 금액"""
        ex = self._exchanges.get(exchange)
        return ex.min_order_amount() if ex else 5000

    async def get_candles(self, exchange, ticker, interval="day", count=200, user_id=None):
        """거래소별 캔들(OHLCV) 데이터 조회 (TTL 캐시 적용)"""
        if user_id and exchange in ("kis", "toss"):
            ticker = await self._resolve(user_id, exchange, ticker)
        interval = str(interval or "day").lower()
        cache_key = (exchange, ticker, interval, count)
        ttl = self._CANDLE_TTL.get(interval, self._CANDLE_TTL["default"])
        entry = self._candle_cache.get(cache_key)
        if entry:
            fetched_at, cached = entry
            if time.time() - fetched_at < ttl:
                return cached

        candles = await self._exchanges[exchange].get_candles(ticker, interval, count, user_id=user_id)

        if candles:
            self._candle_cache[cache_key] = (time.time(), candles)
        return candles

    async def validate_api_keys(self, user_id, exchange):
        """해당 거래소의 API 키가 유효한지 실제 호출을 통해 확인"""
        try:
            if exchange == "toss":
                keys = self._get_client(user_id, exchange)
                if not keys:
                    return False
                account_seq = await self._get_toss_account_seq(user_id, keys)
                if not account_seq:
                    return False
                self.user_manager.update_toss_account_seq(user_id, account_seq)
                return True
            balances = await self.get_balances(user_id, exchange)
            if exchange == "kis":
                return isinstance(balances, dict)
            return balances is not None and isinstance(balances, list)
        except Exception:
            return False

    async def get_ticker(self, exchange, ticker, user_id=None):
        """특정 종목의 현재가 정보 조회"""
        if user_id and exchange in ("kis", "toss"):
            ticker = await self._resolve(user_id, exchange, ticker)
        return await self._exchanges[exchange].get_ticker(ticker, user_id=user_id)

    async def get_krw_ticker_prices(self, exchange):
        """원화 마켓 전체 현재가를 {코인: 가격} 형태로 반환"""
        ex = self._exchanges.get(exchange)
        return await ex.get_krw_ticker_prices() if ex else {}

    async def get_order_history(self, user_id, exchange, ticker=None):
        """사용자의 최근 완료(체결)된 주문 내역 조회"""
        if ticker and exchange in ("kis", "toss"):
            ticker = await self._resolve(user_id, exchange, ticker)
        client = self._get_client(user_id, exchange)
        if not client:
            return None
        return await self._exchanges[exchange].get_order_history(user_id, client, ticker=ticker)
