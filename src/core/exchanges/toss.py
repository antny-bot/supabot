import asyncio
import time

import aiohttp

from core.bot_logger import get_logger
from core.metrics import metrics
from core.exchanges.regular_session import RegularSessionExchange
from core.exchanges.common import CommonMixin
from core.parsers import (
    is_kis_regular_session,
    kis_next_check_timestamp,
    is_us_regular_session,
    us_next_check_timestamp,
)

_log = get_logger("exchange_adapter")


class TossMixin:
    """토스증권 거래소 연동 (OAuth2 토큰, REST 호출, 캔들)."""

    _TOSS_BASE_URL = "https://openapi.tossinvest.com"

    async def _get_toss_session(self):
        if not self._toss_session or self._toss_session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._toss_session = aiohttp.ClientSession(timeout=timeout)
        return self._toss_session

    async def _get_toss_token(self, user_id, keys):
        cache_key = f"{user_id}:{keys.get('client_id')}"
        cached = self._toss_tokens.get(cache_key)
        if cached and cached["expires_at"] > time.time() + 60:
            return cached["token"]

        data = {
            "grant_type": "client_credentials",
            "client_id": keys.get("client_id"),
            "client_secret": keys.get("client_secret"),
        }
        try:
            session = await self._get_toss_session()
            async with session.post(
                f"{self._TOSS_BASE_URL}/oauth2/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as resp:
                res = await resp.json()
        except Exception as e:
            _log.error("Toss token exception", exc_info=e, extra={"event": "toss_token_exception"})
            return None

        token = res.get("access_token") if isinstance(res, dict) else None
        if not token:
            _log.error("Toss token error: no access_token", extra={"event": "toss_token_error"})
            return None

        expires_in = int(res.get("expires_in", 86400))
        self._toss_tokens[cache_key] = {"token": token, "expires_at": time.time() + expires_in}
        return token

    async def _request_toss(self, user_id, method, path, params=None, body=None, need_account=True):
        keys = self._get_client(user_id, "toss")
        if not keys:
            return None

        token = await self._get_toss_token(user_id, keys)
        if not token:
            return None

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        if need_account:
            account_seq = keys.get("account_seq")
            if not account_seq:
                return None
            headers["X-Tossinvest-Account"] = str(account_seq)

        try:
            session = await self._get_toss_session()
            _t0 = time.monotonic()
            url = f"{self._TOSS_BASE_URL}{path}"
            if method.upper() == "POST":
                async with session.post(url, json=body, headers=headers) as resp:
                    result = await resp.json()
            else:
                async with session.get(url, params=params, headers=headers) as resp:
                    result = await resp.json()
            metrics.record_latency("toss", (time.monotonic() - _t0) * 1000)
            return result
        except Exception as e:
            _log.error("Toss API exception", exc_info=e, extra={"event": "toss_api_exception", "path": path})
            return None

    async def _get_toss_account_seq(self, user_id, keys):
        """첫 validate 시 accountSeq를 조회해 user에 저장한다."""
        token = await self._get_toss_token(user_id, keys)
        if not token:
            return None
        headers = {"Authorization": f"Bearer {token}"}
        try:
            session = await self._get_toss_session()
            async with session.get(f"{self._TOSS_BASE_URL}/api/v1/accounts", headers=headers) as resp:
                res = await resp.json()
        except Exception as e:
            _log.error("Toss accounts exception", exc_info=e, extra={"event": "toss_accounts_exception"})
            return None
        accounts = res.get("result") if isinstance(res, dict) else None
        if not accounts:
            return None
        return accounts[0].get("accountSeq")

    @staticmethod
    def _normalize_toss_status(status):
        if status in ("FILLED",):
            return "done"
        if status in ("CANCELED", "REJECTED", "REPLACED", "CANCEL_REJECTED", "REPLACE_REJECTED"):
            return "cancel"
        if status in ("PARTIAL_FILLED",):
            return "partial"
        return "wait"

    async def _get_toss_candles(self, user_id, ticker, interval, count):
        toss_interval = "1d" if interval == "day" else "1m"
        params = {"symbol": ticker, "interval": toss_interval, "count": min(count, 200)}
        res = await self._request_toss(user_id, "GET", "/api/v1/candles", params=params, need_account=False)
        if not isinstance(res, dict):
            return None
        raw_candles = (res.get("result") or {}).get("candles") or []
        candles = []
        for item in raw_candles:
            try:
                candles.append({
                    "candle_date_time_kst": item.get("timestamp", ""),
                    "trade_price": float(item.get("closePrice") or 0),
                    "opening_price": float(item.get("openPrice") or 0),
                    "high_price": float(item.get("highPrice") or 0),
                    "low_price": float(item.get("lowPrice") or 0),
                    "candle_acc_trade_volume": float(item.get("volume") or 0),
                })
            except (TypeError, ValueError):
                continue
        return candles or None


class TossExchange(RegularSessionExchange):
    """토스증권 — 저수준 호출은 adapter(TossMixin)에 위임하는 얇은 래퍼.

    국내/해외(미국) 주식을 모두 다루므로 틱 단위·수량 보정에서 종목코드로
    해외 여부를 판별해 분기한다(`is_us_stock`).
    """

    name = "toss"

    def min_order_amount(self) -> float:
        return 1

    def requires_numeric_ticker(self) -> bool:
        return True

    def round_volume(self, raw: float):
        return int(raw)

    def requires_integer_volume(self) -> bool:
        return True

    def format_volume(self, volume) -> str:
        return f"{int(float(volume))}주"

    @staticmethod
    def is_us_stock(ticker) -> bool:
        return str(ticker or "").isalpha()

    def session_for(self, ticker=None):
        if self.is_us_stock(ticker):
            return is_us_regular_session, us_next_check_timestamp
        return is_kis_regular_session, kis_next_check_timestamp

    def adjust_price_to_tick(self, price, ticker=None):
        if self.is_us_stock(ticker):
            return CommonMixin.adjust_us_price_to_tick(price)
        return CommonMixin.adjust_krx_price_to_tick(price)

    def required_credential_fields(self) -> list:
        return ["client_id", "client_secret"]

    async def get_balances(self, user_id, client):
        res = await self.adapter._request_toss(user_id, "GET", "/api/v1/holdings")
        if not isinstance(res, dict):
            return None
        result = res.get("result", {})
        items = result.get("items", [])
        mv = (result.get("marketValue") or {}).get("amount") or {}
        market_value_krw = float(mv.get("krw") or 0)

        bp_res = await self.adapter._request_toss(user_id, "GET", "/api/v1/buying-power", params={"currency": "KRW"})
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

    async def create_order(self, user_id, client, ticker, side, price, volume, ord_type="limit"):
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
        res = await self.adapter._request_toss(user_id, "POST", "/api/v1/orders", body=body)
        if isinstance(res, dict) and res.get("result", {}).get("orderId"):
            order_id = res["result"]["orderId"]
            return {"uuid": order_id, **res.get("result", {})}
        return res

    async def cancel_order(self, user_id, client, order_id, ticker=None):
        res = await self.adapter._request_toss(user_id, "POST", f"/api/v1/orders/{order_id}/cancel", body={})
        return isinstance(res, dict) and res.get("result", {}).get("orderId") is not None

    async def get_order_status(self, user_id, client, order_id, ticker=None):
        res = await self.adapter._request_toss(user_id, "GET", f"/api/v1/orders/{order_id}")
        if not isinstance(res, dict):
            return None
        order = res.get("result", {})
        if not order:
            return None
        toss_status = order.get("status", "")
        exec_qty = float((order.get("execution") or {}).get("filledQuantity") or 0)
        total_qty = float(order.get("quantity") or 0)
        norm_state = self.adapter._normalize_toss_status(toss_status)
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

    async def get_candles(self, ticker, interval, count, user_id=None):
        if user_id is None:
            return None
        return await self.adapter._get_toss_candles(user_id, ticker, interval, count)

    async def get_ticker(self, ticker, user_id=None):
        if user_id is None:
            return None
        params = {"symbols": ticker}
        items = []
        for attempt in range(2):
            res = await self.adapter._request_toss(user_id, "GET", "/api/v1/prices", params=params, need_account=False)
            items = res.get("result") or [] if isinstance(res, dict) else []
            if items:
                break
            if attempt == 0:
                # 장시간 유지되는 단일 aiohttp 세션이 유휴 커넥션을 재사용하다 끊기는 경우를
                # 대비한 1회 재시도 — 읽기 전용 조회라 재시도해도 안전함.
                _log.warning(
                    "Toss price empty, retrying",
                    extra={"event": "toss_price_retry", "ticker": ticker},
                )
                await asyncio.sleep(0.5)
        if not items:
            _log.warning(
                "Toss price empty after retry",
                extra={"event": "toss_price_empty", "ticker": ticker},
            )
            return None
        item = items[0]
        price = float(item.get("lastPrice") or 0)
        currency = item.get("currency") or "KRW"

        # /api/v1/prices는 symbol·lastPrice·currency만 제공 — 고가/저가/거래량/등락은
        # 일봉 캔들(오늘+전일)로 별도 계산해야 함 (docs/toss.json PriceResponse 참고).
        high = low = volume = change_price = 0.0
        change_rate = 0.0
        candles = await self.adapter.get_candles("toss", ticker, interval="day", count=2, user_id=user_id)
        if candles:
            today = candles[0]
            high = today.get("high_price", 0.0)
            low = today.get("low_price", 0.0)
            volume = today.get("candle_acc_trade_volume", 0.0)
            if len(candles) > 1:
                prev_close = candles[1].get("trade_price", 0.0)
                if prev_close:
                    change_price = price - prev_close
                    change_rate = change_price / prev_close

        return {
            "market": ticker,
            "stock_name": item.get("name") or item.get("stockName") or item.get("issueName") or "",
            "trade_price": price,
            "currency": currency,
            "change_rate": change_rate,
            "change_price": change_price,
            "high_price": high,
            "low_price": low,
            "acc_trade_price_24h": price * volume if currency == "KRW" else volume,
        }

    async def get_order_history(self, user_id, client, ticker=None):
        params = {"status": "CLOSED"}
        if ticker:
            params["symbol"] = ticker
        res = await self.adapter._request_toss(user_id, "GET", "/api/v1/orders", params=params)
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
                "status": self.adapter._normalize_toss_status(o.get("status", "")),
                "created_at": o.get("orderedAt", ""),
                "fee_amount": float(exec_info.get("commission") or 0),
            })
        return result
