import asyncio
import hashlib
import json
import time
import urllib.parse
import uuid

import aiohttp
import jwt

from core.bot_logger import get_logger
from core.metrics import metrics
from core.exchanges.base import BaseExchange

_log = get_logger("exchange_adapter")


class UpbitMixin:
    """업비트 거래소 연동 (JWT 인증, REST 호출, CLI 호출)."""

    async def _get_upbit_session(self):
        if not self._upbit_session or self._upbit_session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._upbit_session = aiohttp.ClientSession(timeout=timeout)
        return self._upbit_session

    def _get_upbit_jwt(self, keys, query_string=None):
        """업비트 API 인증을 위한 JWT 토큰 생성"""
        access_key = keys.get("access_key")
        secret_key = keys.get("secret_key")

        payload = {
            "access_key": access_key,
            "nonce": str(uuid.uuid4()),
        }

        if query_string:
            query_hash = hashlib.sha512(query_string.encode('utf-8')).hexdigest()
            payload["query_hash"] = query_hash
            payload["query_hash_alg"] = "SHA512"

        return jwt.encode(payload, secret_key, algorithm="HS256")

    async def _request_upbit(self, method, path, keys=None, params=None, body=None):
        """업비트 REST API 호출 헬퍼"""
        base_url = "https://api.upbit.com"
        url = f"{base_url}{path}"

        query_string = None
        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"
        elif body:
            query_string = urllib.parse.urlencode({k: v for k, v in body.items() if v is not None})

        headers = {}
        if keys:
            token = self._get_upbit_jwt(keys, query_string)
            headers["Authorization"] = f"Bearer {token}"
            if body:
                headers["Content-Type"] = "application/json; charset=utf-8"

        try:
            session = await self._get_upbit_session()
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
            metrics.record_latency("upbit", (time.monotonic() - _t0) * 1000)
            return result
        except Exception as e:
            _log.error("Upbit API exception", exc_info=e, extra={"event": "upbit_api_exception", "path": path})
            return None

    async def _run_upbit_cli(self, resource, command, args=None, keys=None):
        """업비트 CLI subprocess 호출 래퍼"""
        cli_args = ["upbit", resource, command]
        if args:
            cli_args.extend(args)
        if keys:
            access_key = keys.get("access_key")
            secret_key = keys.get("secret_key")
            if access_key:
                cli_args.extend(["--access-key", access_key])
            if secret_key:
                cli_args.extend(["--secret-key", secret_key])

        try:
            _t0 = time.monotonic()
            process = await asyncio.create_subprocess_exec(
                *cli_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            metrics.record_latency("upbit", (time.monotonic() - _t0) * 1000)

            if process.returncode != 0:
                _log.error(
                    "Upbit CLI failed",
                    extra={
                        "event": "upbit_cli_failed",
                        "resource": resource,
                        "command": command,
                        "returncode": process.returncode,
                        "stderr": stderr.decode("utf-8", errors="ignore").strip(),
                    },
                )
                return None

            payload = stdout.decode("utf-8", errors="ignore").strip()
            if not payload:
                return None
            return json.loads(payload)
        except Exception as e:
            _log.error(
                "Upbit CLI exception",
                exc_info=e,
                extra={"event": "upbit_cli_exception", "resource": resource, "command": command},
            )
            return None


class UpbitExchange(BaseExchange):
    """업비트 — 저수준 호출은 adapter(UpbitMixin)에 위임하는 얇은 래퍼."""

    name = "upbit"

    async def get_balances(self, user_id, client):
        res = await self.adapter._request_upbit("GET", "/v1/accounts", keys=client)
        return res if isinstance(res, list) else None

    async def create_order(self, user_id, client, ticker, side, price, volume, ord_type="limit"):
        args = ["--market", ticker, "--side", side, "--ord-type", ord_type]
        if ord_type != "price":
            args.extend(["--volume", str(volume)])
        if ord_type != "market":
            args.extend(["--price", str(price)])
        res = await self.adapter._run_upbit_cli("orders", "create", args=args, keys=client)
        if res and not self.adapter._is_error_response(res):
            return res
        return None

    async def cancel_order(self, user_id, client, order_id, ticker=None):
        params = {"uuid": order_id}
        res = await self.adapter._request_upbit("DELETE", "/v1/order", keys=client, params=params)
        return True if res and not self.adapter._is_error_response(res) else False

    async def get_order_status(self, user_id, client, order_id, ticker=None):
        params = {"uuid": order_id}
        res = await self.adapter._request_upbit("GET", "/v1/order", keys=client, params=params)
        if res and not self.adapter._is_error_response(res):
            state = res.get('state', '').lower()
            exec_vol = float(res.get('executed_volume', 0))
            total_vol = float(res.get('volume', 0))
            norm_state = state
            if state == "wait" and exec_vol > 0:
                norm_state = "partial"
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
            args = ["--market", ticker, "--count", str(count)]
            return await self.adapter._run_upbit_cli("candles", "list-days", args=args)
        unit = interval if interval in ["1", "3", "5", "10", "15", "30", "60", "240"] else "60"
        args = ["--market", ticker, "--unit", unit, "--count", str(count)]
        return await self.adapter._run_upbit_cli("candles", "list-minutes", args=args)

    async def get_ticker(self, ticker, user_id=None):
        params = {"markets": ticker}
        res = await self.adapter._request_upbit("GET", "/v1/ticker", params=params)
        return res[0] if res and isinstance(res, list) else None

    async def get_order_history(self, user_id, client, ticker=None):
        params = {"state": "done"}
        if ticker:
            params["market"] = ticker
        res = await self.adapter._request_upbit("GET", "/v1/orders", keys=client, params=params)
        return res if isinstance(res, list) else None

    async def get_krw_ticker_prices(self):
        markets = await self.adapter._request_upbit("GET", "/v1/market/all")
        if not isinstance(markets, list):
            return {}
        krw_markets = [m["market"] for m in markets if str(m.get("market", "")).startswith("KRW-")]
        prices = {}
        for i in range(0, len(krw_markets), 100):
            chunk = ",".join(krw_markets[i:i + 100])
            tickers = await self.adapter._request_upbit("GET", "/v1/ticker", params={"markets": chunk})
            if not isinstance(tickers, list):
                continue
            for ticker in tickers:
                market = ticker.get("market", "")
                if market.startswith("KRW-"):
                    prices[market.split("-")[1]] = float(ticker.get("trade_price", 0))
        return prices
