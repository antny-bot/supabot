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
