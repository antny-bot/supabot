import json
import asyncio
import aiohttp
import jwt
import uuid
import hashlib
import urllib.parse
import time

class ExchangeAdapter:
    def __init__(self, user_manager):
        self.user_manager = user_manager
        self._bithumb_session = None
        self._kis_session = None
        self._kis_tokens = {}

    async def close(self):
        """장시간 실행 중 생성한 HTTP 세션을 정상 종료합니다."""
        if self._bithumb_session and not self._bithumb_session.closed:
            await self._bithumb_session.close()
        self._bithumb_session = None
        if self._kis_session and not self._kis_session.closed:
            await self._kis_session.close()
        self._kis_session = None

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

    async def _run_upbit_cli(self, resource, command, args=None, keys=None):
        """upbit CLI를 실행하고 결과를 JSON으로 반환"""
        cmd = ["upbit", resource, command, "--format", "json"]
        if args:
            cmd.extend(args)
        
        if keys:
            access = keys.get("access_key")
            secret = keys.get("secret_key")
            if access and secret:
                cmd.extend(["--access-key", access, "--secret-key", secret])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                print(f"❌ Upbit CLI Error: {stderr.decode().strip()}")
                return None
            
            return json.loads(stdout.decode())
        except Exception as e:
            print(f"❌ Upbit CLI Exception: {e}")
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
            if method.upper() == "POST":
                async with session.post(url, json=body, headers=headers) as resp:
                    return await resp.json()
            elif method.upper() == "DELETE":
                async with session.delete(url, headers=headers) as resp:
                    return await resp.json()
            else:
                async with session.get(url, headers=headers) as resp:
                    return await resp.json()
        except Exception as e:
            print(f"❌ Bithumb API Exception ({path}): {e}")
            return None

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
            print(f"❌ KIS token exception: {e}")
            return None

        token = res.get("access_token") if isinstance(res, dict) else None
        if not token:
            print(f"❌ KIS token error: {res}")
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
            if method.upper() == "POST":
                async with session.post(f"{base_url}{path}", json=body, headers=headers) as resp:
                    return await resp.json()
            async with session.get(f"{base_url}{path}", params=params, headers=headers) as resp:
                return await resp.json()
        except Exception as e:
            print(f"❌ KIS API exception ({path}): {e}")
            return None

    async def get_balances(self, user_id, exchange):
        """유저별 특정 거래소의 잔고 조회"""
        client = self._get_client(user_id, exchange)
        if not client:
            return None

        if exchange == "upbit":
            return await self._run_upbit_cli("accounts", "list", keys=client)
        elif exchange == "bithumb":
            res = await self._request_bithumb("GET", "/v1/accounts", keys=client)
            if res and isinstance(res, list):
                return res
            return None
        elif exchange == "kis":
            return await self._get_kis_balances(user_id, client)
        return None

    async def create_order(self, user_id, exchange, ticker, side, price, volume, ord_type="limit"):
        """지정가/시장가 매수 및 매도 주문 생성"""
        client = self._get_client(user_id, exchange)
        if not client:
            return None

        side = "bid" if side in ["bid", "buy", "매수"] else "ask"

        if exchange == "upbit":
            args = [
                "--market", ticker,
                "--side", side,
                "--ord-type", ord_type,
                "--price", str(price),
                "--volume", str(volume)
            ]
            return await self._run_upbit_cli("orders", "create", args=args, keys=client)
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
                return {"uuid": res.get('order_id') or res.get('uuid'), **res}
            return res
        elif exchange == "kis":
            return await self._create_kis_order(user_id, client, ticker, side, price, volume)
        return None

    async def buy_limit_order(self, user_id, exchange, ticker, price, volume):
        """기존 코드 호환성을 위해 유지 (매수 전용)"""
        return await self.create_order(user_id, exchange, ticker, "bid", price, volume)

    async def cancel_order(self, user_id, exchange, order_id, ticker=None):
        """주문 취소"""
        client = self._get_client(user_id, exchange)
        if not client:
            return False

        if exchange == "upbit":
            args = ["--uuid", order_id]
            res = await self._run_upbit_cli("orders", "cancel", args=args, keys=client)
            return True if res else False
        elif exchange == "bithumb":
            params = {"order_id": order_id}
            res = await self._request_bithumb("DELETE", "/v2/order", keys=client, params=params)
            return True if res and not self._is_error_response(res) else False
        elif exchange == "kis":
            return await self._cancel_kis_order(user_id, client, order_id)
        return False

    async def get_order_status(self, user_id, exchange, order_id, ticker=None):
        """주문 상세 정보 조회 및 상태 정규화"""
        client = self._get_client(user_id, exchange)
        if not client:
            return None

        if exchange == "upbit":
            args = ["--uuid", order_id]
            res = await self._run_upbit_cli("orders", "retrieve", args=args, keys=client)
            if res:
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
                    "remaining_volume": total_vol - exec_vol
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
                    "remaining_volume": total_vol - exec_vol
                }
            return None
        elif exchange == "kis":
            return await self._get_kis_order_status(user_id, client, order_id, ticker)
        return None

    def get_min_order_amount(self, exchange):
        """거래소별 최소 주문 원화(KRW) 금액"""
        if exchange == "upbit": return 5000
        if exchange == "bithumb": return 1000
        if exchange == "kis": return 1
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

    async def get_candles(self, exchange, ticker, interval="day", count=200, user_id=None):
        """거래소별 캔들(OHLCV) 데이터 조회"""
        interval = str(interval or "day").lower()
        if exchange == "upbit":
            if interval == "day":
                args = ["--market", ticker, "--count", str(count)]
                return await self._run_upbit_cli("candles", "list-days", args=args)
            unit = interval if interval in ["1", "3", "5", "10", "15", "30", "60", "240"] else "60"
            args = ["--market", ticker, "--unit", str(unit), "--count", str(count)]
            return await self._run_upbit_cli("candles", "list-minutes", args=args)
        elif exchange == "bithumb":
            if interval == "day":
                path = "/v1/candles/days"
            else:
                unit = interval if interval in ["1", "3", "5", "10", "15", "30", "60", "240"] else "60"
                path = f"/v1/candles/minutes/{unit}"
            params = {"market": ticker, "count": str(count)}
            return await self._request_bithumb("GET", path, params=params)
        elif exchange == "kis":
            if interval != "day" or user_id is None:
                return None
            return await self._get_kis_daily_candles(user_id, ticker, count)
        return None

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

    async def validate_api_keys(self, user_id, exchange):
        """해당 거래소의 API 키가 유효한지 실제 호출을 통해 확인"""
        try:
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

    async def _create_kis_order(self, user_id, keys, ticker, side, price, volume):
        env = keys.get("env", "paper")
        order_side = "buy" if side in ["bid", "buy", "매수"] else "sell"
        if env == "real":
            tr_id = "TTTC0802U" if order_side == "buy" else "TTTC0801U"
        else:
            tr_id = "VTTC0802U" if order_side == "buy" else "VTTC0801U"
        body = {
            "CANO": keys.get("account_no"),
            "ACNT_PRDT_CD": keys.get("product_code", "01"),
            "PDNO": self._normalize_kis_ticker(ticker),
            "ORD_DVSN": "00",
            "ORD_QTY": str(int(float(volume))),
            "ORD_UNPR": str(int(float(price))),
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
        if exchange == "upbit":
            args = ["--markets", ticker]
            res = await self._run_upbit_cli("tickers", "list-by-trading-pairs", args=args)
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
        return None

    async def get_krw_ticker_prices(self, exchange):
        """원화 마켓 전체 현재가를 {코인: 가격} 형태로 반환"""
        if exchange == "upbit":
            tickers = await self._run_upbit_cli(
                "tickers",
                "list-by-quote-currencies",
                args=["--quote-currencies", "KRW"],
            )
            if not tickers:
                return {}
            return {t["market"].split("-")[1]: float(t["trade_price"]) for t in tickers}

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

        return {}

    async def get_order_history(self, user_id, exchange, ticker=None):
        """사용자의 최근 완료(체결)된 주문 내역 조회"""
        client = self._get_client(user_id, exchange)
        if not client: return None
        if exchange == "upbit":
            args = ["--state", "done"]
            if ticker: args.extend(["--market", ticker])
            return await self._run_upbit_cli("orders", "list", args=args, keys=client)
        elif exchange == "bithumb":
            params = {"state": "done"}
            if ticker: params["market"] = ticker
            res = await self._request_bithumb("GET", "/v1/orders", keys=client, params=params)
            return res if isinstance(res, list) else None
        elif exchange == "kis":
            return await self._get_kis_order_history(user_id, client, ticker)
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
