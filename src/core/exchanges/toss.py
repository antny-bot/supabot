import time

import aiohttp

from core.bot_logger import get_logger
from core.metrics import metrics

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
