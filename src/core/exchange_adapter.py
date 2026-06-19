import time

from core.bot_logger import get_logger
from core.metrics import metrics
from core.stock_resolver import is_kr_stock_name, resolve_kr_stock_name
from core.exchanges.common import CommonMixin
from core.exchanges.upbit import UpbitMixin
from core.exchanges.bithumb import BithumbMixin
from core.exchanges.toss import TossMixin
from core.exchanges.kis import KisMixin

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

        if exchange == "upbit":
            res = await self._request_upbit("GET", "/v1/accounts", keys=client)
            return res if isinstance(res, list) else None
        elif exchange == "bithumb":
            res = await self._request_bithumb("GET", "/v1/accounts", keys=client)
            if res and isinstance(res, list):
                return res
            return None
        elif exchange == "kis":
            return await self._get_kis_balances(user_id, client)
        elif exchange == "toss":
            res = await self._request_toss(user_id, "GET", "/api/v1/holdings")
            if not isinstance(res, dict):
                return None
            result = res.get("result", {})
            items = result.get("items", [])
            mv = (result.get("marketValue") or {}).get("amount") or {}
            market_value_krw = float(mv.get("krw") or 0)

            bp_res = await self._request_toss(user_id, "GET", "/api/v1/buying-power", params={"currency": "KRW"})
            cash_krw = 0.0
            if isinstance(bp_res, dict):
                cash_krw = float((bp_res.get("result") or {}).get("cashBuyingPower") or 0)

            stocks = []
            for item in items:
                qty = float(item.get("quantity") or 0)
                if qty <= 0:
                    continue
                stocks.append({
                    "code": item.get("symbol", ""),
                    "name": item.get("name", ""),
                    "quantity": qty,
                    "price": float(item.get("lastPrice") or 0),
                    "value": float((item.get("marketValue") or {}).get("amount") or 0),
                    "currency": item.get("currency", "KRW"),
                })
            return {"cash": cash_krw, "stocks": stocks, "total_eval": cash_krw + market_value_krw}
        return None

    async def create_order(self, user_id, exchange, ticker, side, price, volume, ord_type="limit"):
        """지정가/시장가 매수 및 매도 주문 생성"""
        ticker = await self._resolve(user_id, exchange, ticker)
        client = self._get_client(user_id, exchange)
        if not client:
            return None

        side = "bid" if side in ["bid", "buy", "매수"] else "ask"

        result = None
        if exchange == "upbit":
            args = [
                "--market", ticker,
                "--side", side,
                "--ord-type", ord_type,
            ]
            if ord_type != "price":
                args.extend(["--volume", str(volume)])
            if ord_type != "market":
                args.extend(["--price", str(price)])
            res = await self._run_upbit_cli("orders", "create", args=args, keys=client)
            if res and not self._is_error_response(res):
                result = res
            else:
                result = None
        elif exchange == "bithumb":
            body = {
                "market": ticker,
                "side": side,
                "order_type": ord_type,
                "price": str(price),
                "volume": str(volume)
            }
            if ord_type == "price":
                body["volume"] = None
            elif ord_type == "market":
                body["price"] = None
            body = {k: v for k, v in body.items() if v is not None}
            res = await self._request_bithumb("POST", "/v2/orders", keys=client, body=body)
            if res and ('order_id' in res or 'uuid' in res):
                result = {"uuid": res.get('order_id') or res.get('uuid'), **res}
            else:
                result = res
        elif exchange == "kis":
            result = await self._create_kis_order(user_id, client, ticker, side, price, volume, ord_type=ord_type)
        elif exchange == "toss":
            toss_side = "BUY" if side == "bid" else "SELL"
            toss_order_type = "MARKET" if ord_type == "market" else "LIMIT"
            body = {
                "symbol": ticker,
                "side": toss_side,
                "orderType": toss_order_type,
                "quantity": str(int(float(volume))),
            }
            if toss_order_type == "LIMIT":
                body["price"] = str(price)
            res = await self._request_toss(user_id, "POST", "/api/v1/orders", body=body)
            if isinstance(res, dict) and res.get("result", {}).get("orderId"):
                order_id = res["result"]["orderId"]
                result = {"uuid": order_id, **res.get("result", {})}
            else:
                result = res

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

        if exchange == "upbit":
            params = {"uuid": order_id}
            res = await self._request_upbit("DELETE", "/v1/order", keys=client, params=params)
            return True if res and not self._is_error_response(res) else False
        elif exchange == "bithumb":
            params = {"order_id": order_id}
            res = await self._request_bithumb("DELETE", "/v2/order", keys=client, params=params)
            return True if res and not self._is_error_response(res) else False
        elif exchange == "kis":
            return await self._cancel_kis_order(user_id, client, order_id)
        elif exchange == "toss":
            res = await self._request_toss(user_id, "POST", f"/api/v1/orders/{order_id}/cancel", body={})
            return isinstance(res, dict) and res.get("result", {}).get("orderId") is not None
        return False

    async def get_order_status(self, user_id, exchange, order_id, ticker=None):
        """주문 상세 정보 조회 및 상태 정규화"""
        if ticker and exchange in ("kis", "toss"):
            ticker = await self._resolve(user_id, exchange, ticker)
        client = self._get_client(user_id, exchange)
        if not client:
            return None

        if exchange == "upbit":
            params = {"uuid": order_id}
            res = await self._request_upbit("GET", "/v1/order", keys=client, params=params)
            if res and not self._is_error_response(res):
                state = res.get('state', '').lower()
                exec_vol = float(res.get('executed_volume', 0))
                total_vol = float(res.get('volume', 0))
                norm_state = state
                if state == "wait" and exec_vol > 0: norm_state = "partial"
                return {
                    "state": norm_state,
                    "ticker": res.get('market'),
                    "side": res.get('side'),
                    "executed_volume": exec_vol,
                    "remaining_volume": total_vol - exec_vol,
                    "fee_amount": float(res.get('paid_fee') or 0),
                }
            return None
        elif exchange == "bithumb":
            params = {"uuid": order_id}
            res = await self._request_bithumb("GET", "/v1/order", keys=client, params=params)
            if res:
                state = res.get('state', '').lower()
                status = res.get('status', '').lower()
                exec_vol = float(res.get('executed_volume', 0))
                total_vol = float(res.get('volume', 0))
                norm_state = self._normalize_order_state(state or status, exec_vol)
                return {
                    "state": norm_state,
                    "ticker": res.get('market'),
                    "side": res.get('side'),
                    "executed_volume": exec_vol,
                    "remaining_volume": total_vol - exec_vol,
                    "fee_amount": float(res.get('paid_fee') or 0),
                }
            return None
        elif exchange == "kis":
            return await self._get_kis_order_status(user_id, client, order_id, ticker)
        elif exchange == "toss":
            res = await self._request_toss(user_id, "GET", f"/api/v1/orders/{order_id}")
            if not isinstance(res, dict):
                return None
            order = res.get("result", {})
            if not order:
                return None
            toss_status = order.get("status", "")
            exec_qty = float((order.get("execution") or {}).get("filledQuantity") or 0)
            total_qty = float(order.get("quantity") or 0)
            norm_state = self._normalize_toss_status(toss_status)
            toss_side = order.get("side", "")
            side = "bid" if toss_side == "BUY" else "ask"
            return {
                "state": norm_state,
                "ticker": order.get("symbol", ticker),
                "side": side,
                "executed_volume": exec_qty,
                "remaining_volume": max(total_qty - exec_qty, 0),
                "fee_amount": float((order.get("execution") or {}).get("commission") or 0),
            }
        return None

    def get_min_order_amount(self, exchange):
        """거래소별 최소 주문 원화(KRW) 금액"""
        if exchange == "upbit": return 5000
        if exchange == "bithumb": return 1000
        if exchange == "kis": return 1
        if exchange == "toss": return 1
        return 5000

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

        candles = None
        if exchange == "upbit":
            if interval == "day":
                args = ["--market", ticker, "--count", str(count)]
                candles = await self._run_upbit_cli("candles", "list-days", args=args)
            else:
                unit = interval if interval in ["1", "3", "5", "10", "15", "30", "60", "240"] else "60"
                args = ["--market", ticker, "--unit", unit, "--count", str(count)]
                candles = await self._run_upbit_cli("candles", "list-minutes", args=args)
        elif exchange == "bithumb":
            if interval == "day":
                path = "/v1/candles/days"
            else:
                unit = interval if interval in ["1", "3", "5", "10", "15", "30", "60", "240"] else "60"
                path = f"/v1/candles/minutes/{unit}"
            params = {"market": ticker, "count": str(count)}
            candles = await self._request_bithumb("GET", path, params=params)
        elif exchange == "kis":
            if interval != "day" or user_id is None:
                return None
            candles = await self._get_kis_daily_candles(user_id, ticker, count)
        elif exchange == "toss":
            if user_id is None:
                return None
            candles = await self._get_toss_candles(user_id, ticker, interval, count)

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
        if exchange == "upbit":
            params = {"markets": ticker}
            res = await self._request_upbit("GET", "/v1/ticker", params=params)
            return res[0] if res and isinstance(res, list) else None
        elif exchange == "bithumb":
            path = "/v1/ticker"
            params = {"markets": ticker}
            res = await self._request_bithumb("GET", path, params=params)
            return res[0] if res and isinstance(res, list) else None
        elif exchange == "kis":
            if user_id is None:
                return None
            return await self._get_kis_ticker(user_id, ticker)
        elif exchange == "toss":
            if user_id is None:
                return None
            params = {"symbols": ticker}
            res = await self._request_toss(user_id, "GET", "/api/v1/prices", params=params, need_account=False)
            if not isinstance(res, dict):
                return None
            items = res.get("result") or []
            if not items:
                return None
            item = items[0]
            price = float(item.get("lastPrice") or 0)
            change_rate = float(item.get("changeRate") or item.get("changeRatio") or 0)
            return {
                "market": ticker,
                "stock_name": item.get("name") or item.get("stockName") or item.get("issueName") or "",
                "trade_price": price,
                "change_rate": change_rate / 100 if abs(change_rate) > 1 else change_rate,
                "change_price": float(item.get("changePrice") or item.get("priceChange") or 0),
                "high_price": float(item.get("highPrice") or item.get("high") or 0),
                "low_price": float(item.get("lowPrice") or item.get("low") or 0),
                "acc_trade_price_24h": float(item.get("tradingValue") or item.get("volume") or item.get("tradeAmount") or 0),
            }
        return None

    async def get_krw_ticker_prices(self, exchange):
        """원화 마켓 전체 현재가를 {코인: 가격} 형태로 반환"""
        if exchange == "upbit":
            markets = await self._request_upbit("GET", "/v1/market/all")
            if not isinstance(markets, list):
                return {}
            krw_markets = [m["market"] for m in markets if str(m.get("market", "")).startswith("KRW-")]
            prices = {}
            for i in range(0, len(krw_markets), 100):
                chunk = ",".join(krw_markets[i:i + 100])
                tickers = await self._request_upbit("GET", "/v1/ticker", params={"markets": chunk})
                if not isinstance(tickers, list):
                    continue
                for ticker in tickers:
                    market = ticker.get("market", "")
                    if market.startswith("KRW-"):
                        prices[market.split("-")[1]] = float(ticker.get("trade_price", 0))
            return prices

        if exchange == "bithumb":
            markets = await self._request_bithumb("GET", "/v1/market/all")
            if not isinstance(markets, list):
                return {}
            krw_markets = [m["market"] for m in markets if str(m.get("market", "")).startswith("KRW-")]
            prices = {}
            for i in range(0, len(krw_markets), 100):
                chunk = ",".join(krw_markets[i:i + 100])
                tickers = await self._request_bithumb("GET", "/v1/ticker", params={"markets": chunk})
                if not isinstance(tickers, list):
                    continue
                for ticker in tickers:
                    market = ticker.get("market", "")
                    if market.startswith("KRW-"):
                        prices[market.split("-")[1]] = float(ticker.get("trade_price", 0))
            return prices

        if exchange == "kis":
            return {}

        if exchange == "toss":
            return {}

        return {}

    async def get_order_history(self, user_id, exchange, ticker=None):
        """사용자의 최근 완료(체결)된 주문 내역 조회"""
        if ticker and exchange in ("kis", "toss"):
            ticker = await self._resolve(user_id, exchange, ticker)
        client = self._get_client(user_id, exchange)
        if not client: return None
        if exchange == "upbit":
            params = {"state": "done"}
            if ticker:
                params["market"] = ticker
            res = await self._request_upbit("GET", "/v1/orders", keys=client, params=params)
            return res if isinstance(res, list) else None
        elif exchange == "bithumb":
            params = {"state": "done"}
            if ticker: params["market"] = ticker
            res = await self._request_bithumb("GET", "/v1/orders", keys=client, params=params)
            return res if isinstance(res, list) else None
        elif exchange == "kis":
            return await self._get_kis_order_history(user_id, client, ticker)
        elif exchange == "toss":
            params = {"status": "CLOSED"}
            if ticker:
                params["symbol"] = ticker
            res = await self._request_toss(user_id, "GET", "/api/v1/orders", params=params)
            if not isinstance(res, dict):
                return None
            orders = (res.get("result") or {}).get("orders") or []
            result = []
            for o in orders:
                exec_info = o.get("execution") or {}
                qty = float(o.get("quantity") or 0)
                exec_qty = float(exec_info.get("filledQuantity") or 0)
                toss_side = o.get("side", "")
                side = "bid" if toss_side == "BUY" else "ask"
                result.append({
                    "uuid": o.get("orderId"),
                    "market": o.get("symbol", ticker),
                    "side": side,
                    "price": float(o.get("price") or 0),
                    "volume": qty,
                    "executed_volume": exec_qty,
                    "status": self._normalize_toss_status(o.get("status", "")),
                    "created_at": o.get("orderedAt", ""),
                    "fee_amount": float(exec_info.get("commission") or 0),
                })
            return result
        return None
