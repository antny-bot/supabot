"""Manager Backend REST API 호출 클라이언트.

텔레그램 봇이 사용자를 대리하여 Manager Backend의 REST API(/api/orders, /api/templates 등)를
HMAC 헤더 서명 방식으로 안전하게 호출한다.
"""
import asyncio
import hashlib
import hmac
import os
import time
from typing import Any, Optional
import aiohttp

from core.bot_logger import get_logger

_log = get_logger("manager_api_client")


def _generate_hmac_headers(bot_user_id: str, path: str, is_admin: bool = False) -> dict[str, str]:
    api_key = os.getenv("MANAGER_API_KEY", "").strip()
    timestamp_str = str(int(time.time()))
    normalized_path = path.split("?")[0]  # 쿼리스트링 제외한 path
    msg = f"{timestamp_str}:{bot_user_id}:{normalized_path}".encode("utf-8")
    sig = hmac.new(api_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    return {
        "X-Bot-User-Id": str(bot_user_id),
        "X-Timestamp": timestamp_str,
        "X-Signature": sig,
        "X-Is-Admin": "true" if is_admin else "false",
    }


async def request_manager_api(
    method: str,
    path: str,
    user_id: str,
    is_admin: bool = False,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Manager REST API를 비동기 호출하고 응답 dict를 반환한다.

    네트워크나 HTTP 실패 시에도 크래시 없이 {"ok": False, "error": str}를 반환한다.
    """
    base_url = os.getenv("MANAGER_BACKEND_URL", "http://localhost:8000").rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base_url}{path}"

    headers = _generate_hmac_headers(user_id, path, is_admin=is_admin)

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method.upper(),
                url,
                headers=headers,
                params=params,
                json=json_body,
            ) as response:
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    data = await response.json()
                else:
                    text = await response.text()
                    data = {"raw_text": text}

                if response.status >= 400:
                    err_msg = data.get("detail") or data.get("error") or f"HTTP {response.status}"
                    return {"ok": False, "status_code": response.status, "error": str(err_msg), "data": data}

                return {"ok": True, "status_code": response.status, "data": data}
    except asyncio.TimeoutError:
        _log.warning("Manager API request timeout: %s %s", method, path)
        return {"ok": False, "error": "Manager API timeout (10s)"}
    except Exception as e:
        _log.warning("Manager API request failed: %s %s, error=%s", method, path, e)
        return {"ok": False, "error": str(e)}
