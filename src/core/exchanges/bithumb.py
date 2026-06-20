import hashlib
import time
import urllib.parse
import uuid

import aiohttp
import jwt

from core.bot_logger import get_logger
from core.metrics import metrics
from core.exchanges.base import BaseExchange

_log = get_logger("exchange_adapter")


class BithumbMixin:
    """빗썸 거래소 연동 (V1/V2 JWT 인증, REST 호출)."""

    async def _get_bithumb_session(self):
        if not self._bithumb_session or self._bithumb_session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._bithumb_session = aiohttp.ClientSession(timeout=timeout)
        return self._bithumb_session

    def _get_bithumb_jwt(self, keys, query_string=None):
        """빗썸 V2 API 인증을 위한 JWT 토큰 생성"""
        access_key = keys.get("access_key")
        secret_key = keys.get("secret_key")

        payload = {
            "access_key": access_key,
            "nonce": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000)
        }

        if query_string:
            query_hash = hashlib.sha512(query_string.encode('utf-8')).hexdigest()
            payload["query_hash"] = query_hash
            payload["query_hash_alg"] = "SHA512"

        return jwt.encode(payload, secret_key, algorithm="HS256")

    async def _request_bithumb(self, method, path, keys=None, params=None, body=None):
        """빗썸 V1/V2 REST API 호출 헬퍼"""
        base_url = "https://api.bithumb.com"
        url = f"{base_url}{path}"

        query_string = None
        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"
        elif body:
            query_string = urllib.parse.urlencode({k: v for k, v in body.items() if v is not None})

        headers = {}
        if keys:
            token = self._get_bithumb_jwt(keys, query_string)
            headers["Authorization"] = f"Bearer {token}"
            if body:
                headers["Content-Type"] = "application/json; charset=utf-8"

        try:
            session = await self._get_bithumb_session()
            _t0 = time.monotonic()
            if method.upper() == "POST":
                async with session.post(url, json=body, headers=headers) as resp:
                    result = await resp.json()
            elif method.upper() == "DELETE":
                async with session.delete(url, headers=headers) as resp:
                    result = await resp.json()
            else:
                async with session.get(url, headers=headers) as resp:
                    result = await resp.json()
            metrics.record_latency("bithumb", (time.monotonic() - _t0) * 1000)
            return result
        except Exception as e:
            _log.error("Bithumb API exception", exc_info=e, extra={"event": "bithumb_api_exception", "path": path})
            return None


class BithumbExchange(BaseExchange):
    """빗썸 — 저수준 호출은 adapter(BithumbMixin)에 위임하는 얇은 래퍼."""

    name = "bithumb"

    def min_order_amount(self) -> float:
        return 1000

    async def get_balances(self, user_id, client):
        res = await self.adapter._request_bithumb("GET", "/v1/accounts", keys=client)
        if res and isinstance(res, list):
            return res
        return None

    async def create_order(self, user_id, client, ticker, side, price, volume, ord_type="limit"):
        body = {
            "market": ticker,
            "side": side,
            "order_type": ord_type,
            "price": str(price),
            "volume": str(volume),
        }
        if ord_type == "price":
            body["volume"] = None
        elif ord_type == "market":
            body["price"] = None
        body = {k: v for k, v in body.items() if v is not None}
        res = await self.adapter._request_bithumb("POST", "/v2/orders", keys=client, body=body)
        if res and ('order_id' in res or 'uuid' in res):
            return {"uuid": res.get('order_id') or res.get('uuid'), **res}
        return res

    async def cancel_order(self, user_id, client, order_id, ticker=None):
        params = {"order_id": order_id}
        res = await self.adapter._request_bithumb("DELETE", "/v2/order", keys=client, params=params)
        return True if res and not self.adapter._is_error_response(res) else False

    async def get_order_status(self, user_id, client, order_id, ticker=None):
        params = {"uuid": order_id}
        res = await self.adapter._request_bithumb("GET", "/v1/order", keys=client, params=params)
        if res:
            state = res.get('state', '').lower()
            status = res.get('status', '').lower()
            exec_vol = float(res.get('executed_volume', 0))
            total_vol = float(res.get('volume', 0))
            norm_state = self.adapter._normalize_order_state(state or status, exec_vol)
            return {
                "state": norm_state,
                "ticker": res.get('market'),
                "side": res.get('side'),
                "executed_volume": exec_vol,
                "remaining_volume": total_vol - exec_vol,
                "fee_amount": float(res.get('paid_fee') or 0),
            }
        return None

    async def get_candles(self, ticker, interval, count, user_id=None):
        if interval == "day":
            path = "/v1/candles/days"
        else:
            unit = interval if interval in ["1", "3", "5", "10", "15", "30", "60", "240"] else "60"
            path = f"/v1/candles/minutes/{unit}"
        params = {"market": ticker, "count": str(count)}
        return await self.adapter._request_bithumb("GET", path, params=params)

    async def get_ticker(self, ticker, user_id=None):
        params = {"markets": ticker}
        res = await self.adapter._request_bithumb("GET", "/v1/ticker", params=params)
        return res[0] if res and isinstance(res, list) else None

    async def get_order_history(self, user_id, client, ticker=None):
        params = {"state": "done"}
        if ticker:
            params["market"] = ticker
        res = await self.adapter._request_bithumb("GET", "/v1/orders", keys=client, params=params)
        return res if isinstance(res, list) else None

    async def get_krw_ticker_prices(self):
        markets = await self.adapter._request_bithumb("GET", "/v1/market/all")
        if not isinstance(markets, list):
            return {}
        krw_markets = [m["market"] for m in markets if str(m.get("market", "")).startswith("KRW-")]
        prices = {}
        for i in range(0, len(krw_markets), 100):
            chunk = ",".join(krw_markets[i:i + 100])
            tickers = await self.adapter._request_bithumb("GET", "/v1/ticker", params={"markets": chunk})
            if not isinstance(tickers, list):
                continue
            for ticker in tickers:
                market = ticker.get("market", "")
                if market.startswith("KRW-"):
                    prices[market.split("-")[1]] = float(ticker.get("trade_price", 0))
        return prices
