import json
import asyncio
import aiohttp
import jwt
import uuid
import hashlib
import urllib.parse
import time

from core.bot_logger import get_logger
from core.metrics import metrics
from core.stock_resolver import is_kr_stock_name, resolve_kr_stock_name

_log = get_logger("exchange_adapter")


class ExchangeAdapter:
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

    async def _get_bithumb_session(self):
        if not self._bithumb_session or self._bithumb_session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._bithumb_session = aiohttp.ClientSession(timeout=timeout)
        return self._bithumb_session

    async def _get_kis_session(self):
        if not self._kis_session or self._kis_session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._kis_session = aiohttp.ClientSession(timeout=timeout)
        return self._kis_session

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

    @staticmethod
    def _get_kis_base_url(env):
        if env == "real":
            return "https://openapi.koreainvestment.com:9443"
        return "https://openapivts.koreainvestment.com:29443"

    async def _get_kis_token(self, user_id, keys):
        env = keys.get("env", "paper")
        cache_key = f"{user_id}:{env}:{keys.get('app_key')}"
        cached = self._kis_tokens.get(cache_key)
        if cached and cached["expires_at"] > time.time() + 60:
            return cached["token"]

        base_url = self._get_kis_base_url(env)
        body = {
            "grant_type": "client_credentials",
            "appkey": keys.get("app_key"),
            "appsecret": keys.get("app_secret"),
        }
        try:
            session = await self._get_kis_session()
            async with session.post(f"{base_url}/oauth2/tokenP", json=body) as resp:
                res = await resp.json()
        except Exception as e:
            _log.error("KIS token exception", exc_info=e, extra={"event": "kis_token_exception"})
            return None

        token = res.get("access_token") if isinstance(res, dict) else None
        if not token:
            _log.error("KIS token error: no access_token in response", extra={"event": "kis_token_error"})
            return None

        expires_in = int(res.get("expires_in", 86400))
        self._kis_tokens[cache_key] = {"token": token, "expires_at": time.time() + expires_in}
        return token

    async def _request_kis(self, user_id, method, path, tr_id, params=None, body=None):
        keys = self._get_client(user_id, "kis")
        if not keys:
            return None

        token = await self._get_kis_token(user_id, keys)
        if not token:
            return None

        base_url = self._get_kis_base_url(keys.get("env", "paper"))
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": keys.get("app_key"),
            "appsecret": keys.get("app_secret"),
            "tr_id": tr_id,
            "custtype": "P",
        }

        try:
            session = await self._get_kis_session()
            _t0 = time.monotonic()
            if method.upper() == "POST":
                async with session.post(f"{base_url}{path}", json=body, headers=headers) as resp:
                    result = await resp.json()
            else:
                async with session.get(f"{base_url}{path}", params=params, headers=headers) as resp:
                    result = await resp.json()
            metrics.record_latency("kis", (time.monotonic() - _t0) * 1000)
            return result
        except Exception as e:
            _log.error("KIS API exception", exc_info=e, extra={"event": "kis_api_exception", "path": path})
            return None

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

    @staticmethod
    def get_tick_size(price):
        """업비트/빗썸 호가 단위 계산"""
        if price >= 2000000: return 1000
        if price >= 1000000: return 500
        if price >= 500000: return 100
        if price >= 100000: return 50
        if price >= 10000: return 10
        if price >= 1000: return 5
        if price >= 100: return 1
        if price >= 10: return 0.1
        if price >= 1: return 0.01
        if price >= 0.1: return 0.001
        return 0.0001

    @staticmethod
    def adjust_price_to_tick(price):
        """가격을 호가 단위에 맞게 보정 (내림 처리)"""
        tick_size = ExchangeAdapter.get_tick_size(price)
        adjusted = price - (price % tick_size)
        if tick_size >= 1:
            return int(adjusted)
        return round(adjusted, 4)

    @staticmethod
    def get_krx_tick_size(price):
        """KIS/Toss(KRX 상장 주식) 호가 단위 계산 (업비트/빗썸 호가 단위와 다름)"""
        if price >= 500000: return 1000
        if price >= 200000: return 500
        if price >= 50000: return 100
        if price >= 20000: return 50
        if price >= 5000: return 10
        if price >= 2000: return 5
        return 1

    @staticmethod
    def adjust_krx_price_to_tick(price):
        """KIS/Toss 주문 가격을 KRX 호가 단위에 맞게 보정 (내림 처리)"""
        tick_size = ExchangeAdapter.get_krx_tick_size(price)
        adjusted = price - (price % tick_size)
        return int(adjusted)

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

    async def _get_kis_daily_candles(self, user_id, ticker, count=200):
        end_date = time.strftime("%Y%m%d")
        start_date = time.strftime("%Y%m%d", time.localtime(time.time() - 60 * 60 * 24 * max(count * 2, 60)))
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": self._normalize_kis_ticker(ticker),
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }
        res = await self._request_kis(
            user_id,
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            "FHKST03010100",
            params=params,
        )
        rows = []
        if isinstance(res, dict):
            rows = res.get("output2") or []
        candles = []
        for item in rows[:count]:
            try:
                candles.append({
                    "candle_date_time_kst": str(item.get("stck_bsop_date", "")),
                    "trade_price": float(item.get("stck_clpr", 0) or 0),
                    "opening_price": float(item.get("stck_oprc", 0) or 0),
                    "high_price": float(item.get("stck_hgpr", 0) or 0),
                    "low_price": float(item.get("stck_lwpr", 0) or 0),
                })
            except (TypeError, ValueError):
                continue
        return candles

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
                })
            except (TypeError, ValueError):
                continue
        return candles or None

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

    async def _get_kis_ticker(self, user_id, ticker):
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": self._normalize_kis_ticker(ticker),
        }
        res = await self._request_kis(
            user_id,
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            params=params,
        )
        output = res.get("output", {}) if isinstance(res, dict) else {}
        if not output:
            return None
        return {
            "market": self._normalize_kis_ticker(ticker),
            "stock_name": output.get("hts_kor_isnm", ""),
            "trade_price": float(output.get("stck_prpr", 0) or 0),
            "change_rate": float(output.get("prdy_ctrt", 0) or 0) / 100,
            "change_price": float(output.get("prdy_vrss", 0) or 0),
            "high_price": float(output.get("stck_hgpr", 0) or 0),
            "low_price": float(output.get("stck_lwpr", 0) or 0),
            "acc_trade_price_24h": float(output.get("acml_tr_pbmn", 0) or 0),
        }

    async def _get_kis_balances(self, user_id, keys):
        params = {
            "CANO": keys.get("account_no"),
            "ACNT_PRDT_CD": keys.get("product_code", "01"),
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        tr_id = "TTTC8434R" if keys.get("env") == "real" else "VTTC8434R"
        res = await self._request_kis(
            user_id,
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id,
            params=params,
        )
        if not isinstance(res, dict) or res.get("rt_cd") not in [None, "0"]:
            return None
        stocks = []
        total_stock_value = 0
        for item in res.get("output1", []) or []:
            qty = float(item.get("hldg_qty", 0) or 0)
            if qty <= 0:
                continue
            value = float(item.get("evlu_amt", 0) or 0)
            total_stock_value += value
            stocks.append({
                "code": item.get("pdno", ""),
                "name": item.get("prdt_name", ""),
                "quantity": qty,
                "price": float(item.get("prpr", 0) or 0),
                "value": value,
            })

        if isinstance(res.get("output2"), list):
            summary = (res.get("output2") or [{}])[0]
        elif isinstance(res.get("output2"), dict):
            summary = res.get("output2")
        else:
            summary = {}
        cash = float(summary.get("dnca_tot_amt", 0) or summary.get("nass_amt", 0) or 0)
        total_eval = float(summary.get("tot_evlu_amt", 0) or cash + total_stock_value)
        return {
            "cash": cash,
            "stocks": stocks,
            "total_eval": total_eval,
            "env": keys.get("env", "paper"),
        }

    async def _create_kis_order(self, user_id, keys, ticker, side, price, volume, ord_type="limit"):
        env = keys.get("env", "paper")
        order_side = "buy" if side in ["bid", "buy", "매수"] else "sell"
        if env == "real":
            tr_id = "TTTC0802U" if order_side == "buy" else "TTTC0801U"
        else:
            tr_id = "VTTC0802U" if order_side == "buy" else "VTTC0801U"
        is_market = ord_type == "market"
        body = {
            "CANO": keys.get("account_no"),
            "ACNT_PRDT_CD": keys.get("product_code", "01"),
            "PDNO": self._normalize_kis_ticker(ticker),
            "ORD_DVSN": "01" if is_market else "00",
            "ORD_QTY": str(int(float(volume))),
            "ORD_UNPR": "0" if is_market else str(int(float(price))),
        }
        if int(float(volume)) <= 0:
            return {"error": "KIS 주문 수량은 1주 이상이어야 합니다."}
        res = await self._request_kis(
            user_id,
            "POST",
            "/uapi/domestic-stock/v1/trading/order-cash",
            tr_id,
            body=body,
        )
        if not isinstance(res, dict) or res.get("rt_cd") != "0":
            return res
        output = res.get("output", {})
        order_no = output.get("ODNO")
        org_no = output.get("KRX_FWDG_ORD_ORGNO", "")
        if not order_no:
            return res
        return {"uuid": f"{org_no}:{order_no}", **res}

    async def _cancel_kis_order(self, user_id, keys, order_id):
        env = keys.get("env", "paper")
        tr_id = "TTTC0803U" if env == "real" else "VTTC0803U"
        org_no, order_no = self._split_kis_order_id(order_id)
        body = {
            "CANO": keys.get("account_no"),
            "ACNT_PRDT_CD": keys.get("product_code", "01"),
            "KRX_FWDG_ORD_ORGNO": org_no,
            "ORGN_ODNO": order_no,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02",
            "ORD_QTY": "0",
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y",
        }
        res = await self._request_kis(
            user_id,
            "POST",
            "/uapi/domestic-stock/v1/trading/order-rvsecncl",
            tr_id,
            body=body,
        )
        return isinstance(res, dict) and res.get("rt_cd") == "0"

    async def _get_kis_order_status(self, user_id, keys, order_id, ticker=None):
        orders = await self._get_kis_order_history(user_id, keys, ticker)
        if not orders:
            return None
        _, order_no = self._split_kis_order_id(order_id)
        for order in orders:
            if str(order.get("order_no", "")) == order_no:
                volume = float(order.get("volume", 0) or 0)
                executed = float(order.get("executed_volume", 0) or 0)
                state = self._normalize_order_state(order.get("status"), executed)
                return {
                    "state": state,
                    "ticker": order.get("market", ticker),
                    "side": order.get("side"),
                    "executed_volume": executed,
                    "remaining_volume": max(volume - executed, 0),
                }
        return None

    async def _get_kis_order_history(self, user_id, keys, ticker=None):
        params = {
            "CANO": keys.get("account_no"),
            "ACNT_PRDT_CD": keys.get("product_code", "01"),
            "INQR_STRT_DT": time.strftime("%Y%m%d", time.localtime(time.time() - 60 * 60 * 24 * 30)),
            "INQR_END_DT": time.strftime("%Y%m%d"),
            "SLL_BUY_DVSN_CD": "00",
            "INQR_DVSN": "00",
            "PDNO": self._normalize_kis_ticker(ticker) if ticker else "",
            "CCLD_DVSN": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        tr_id = "TTTC8001R" if keys.get("env") == "real" else "VTTC8001R"
        res = await self._request_kis(
            user_id,
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            tr_id,
            params=params,
        )
        if not isinstance(res, dict):
            return None
        orders = []
        for item in res.get("output1", []) or []:
            qty = float(item.get("ord_qty", 0) or 0)
            executed = float(item.get("tot_ccld_qty", 0) or 0)
            side_code = str(item.get("sll_buy_dvsn_cd", ""))
            side_name = str(item.get("sll_buy_dvsn_cd_name", ""))
            side = "bid" if side_code == "02" or "매수" in side_name else "ask"
            orders.append({
                "order_no": str(item.get("odno", "")),
                "market": item.get("pdno", ticker),
                "side": side,
                "price": float(item.get("ord_unpr", 0) or item.get("avg_prvs", 0) or 0),
                "volume": qty,
                "executed_volume": executed,
                "status": "done" if qty > 0 and executed >= qty else "wait",
                "created_at": item.get("ord_dt", ""),
                "fee_amount": float(item.get("sll_cmsn") or item.get("tot_ccld_cmsn") or item.get("cmsn_amnt") or 0),
            })
        return orders

    @staticmethod
    def _normalize_kis_ticker(ticker):
        return str(ticker or "").replace("KRW-", "").strip().upper()

    @staticmethod
    def _split_kis_order_id(order_id):
        text = str(order_id)
        if ":" in text:
            org_no, order_no = text.split(":", 1)
            return org_no, order_no
        return "", text

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
                "currency": item.get("currency") or "KRW",
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

    @staticmethod
    def _normalize_order_state(state, executed_volume=0):
        state = (state or "").lower()
        if state in ["done", "completed"]:
            return "done"
        if state in ["cancel", "canceled", "cancelled"]:
            return "cancel"
        if executed_volume > 0:
            return "partial"
        return "wait"

    @staticmethod
    def _is_error_response(res):
        if not isinstance(res, dict):
            return False
        if "error" in res:
            return True
        status = str(res.get("status", ""))
        return status.startswith("4") or status.startswith("5")
