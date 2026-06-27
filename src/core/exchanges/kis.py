import time

import aiohttp

from core.bot_logger import get_logger
from core.metrics import metrics
from core.exchanges.regular_session import RegularSessionExchange
from core.parsers import is_kis_regular_session, kis_next_check_timestamp

_log = get_logger("exchange_adapter")


class KisMixin:
    """한국투자증권(KIS) 거래소 연동 (OAuth 토큰, REST 호출, 주문/잔고/캔들)."""

    async def _get_kis_session(self):
        if not self._kis_session or self._kis_session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._kis_session = aiohttp.ClientSession(timeout=timeout)
        return self._kis_session

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
            order_no = str(item.get("odno", ""))
            org_no = str(item.get("ord_gno_brno", ""))
            orders.append({
                "uuid": f"{org_no}:{order_no}" if order_no else None,
                "order_no": order_no,
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


class KisExchange(RegularSessionExchange):
    """한국투자증권(KIS) — 저수준 호출은 adapter(KisMixin)에 위임하는 얇은 래퍼."""

    name = "kis"

    def min_order_amount(self) -> float:
        return 1

    def supports_minute_candles(self) -> bool:
        return False

    def session_for(self, ticker=None):
        return is_kis_regular_session, kis_next_check_timestamp

    def requires_numeric_ticker(self) -> bool:
        return True

    def round_volume(self, raw: float):
        return int(raw)

    def requires_integer_volume(self) -> bool:
        return True

    def format_volume(self, volume) -> str:
        return f"{int(float(volume))}주"

    def adjust_price_to_tick(self, price, ticker=None):
        from core.exchanges.common import CommonMixin
        return CommonMixin.adjust_krx_price_to_tick(price)

    def env_label(self, client=None):
        env = (client or {}).get("env", "paper")
        return "실전" if env == "real" else "모의"

    def required_credential_fields(self) -> list:
        return ["app_key", "app_secret", "account_no", "product_code"]

    async def get_balances(self, user_id, client):
        return await self.adapter._get_kis_balances(user_id, client)

    async def create_order(self, user_id, client, ticker, side, price, volume, ord_type="limit"):
        return await self.adapter._create_kis_order(user_id, client, ticker, side, price, volume, ord_type=ord_type)

    async def cancel_order(self, user_id, client, order_id, ticker=None):
        return await self.adapter._cancel_kis_order(user_id, client, order_id)

    async def get_order_status(self, user_id, client, order_id, ticker=None):
        return await self.adapter._get_kis_order_status(user_id, client, order_id, ticker)

    async def get_candles(self, ticker, interval, count, user_id=None):
        if interval != "day" or user_id is None:
            return None
        return await self.adapter._get_kis_daily_candles(user_id, ticker, count)

    async def get_ticker(self, ticker, user_id=None):
        if user_id is None:
            return None
        return await self.adapter._get_kis_ticker(user_id, ticker)

    async def get_order_history(self, user_id, client, ticker=None):
        return await self.adapter._get_kis_order_history(user_id, client, ticker)

    async def get_open_orders(self, user_id, client, ticker=None):
        """미체결(아직 done이 아닌) 주문만 추출 — _get_kis_order_history는 CCLD_DVSN="00"(전체)
        조회라 오늘자 체결+미체결 주문을 모두 포함하므로 추가 API 호출 없이 필터링한다."""
        orders = await self.adapter._get_kis_order_history(user_id, client, ticker)
        if not orders:
            return orders
        return [o for o in orders if o.get("status") != "done"]
