import hashlib
import time
import urllib.parse
import uuid

import aiohttp
import jwt

from core.bot_logger import get_logger
from core.metrics import metrics

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
