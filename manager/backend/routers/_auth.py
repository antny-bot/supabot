import hmac
import hashlib
import os
import time
from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse


def _extract_bot_auth_user(request: Request) -> dict | None:
    bot_user_id = request.headers.get("X-Bot-User-Id")
    timestamp_str = request.headers.get("X-Timestamp")
    signature = request.headers.get("X-Signature")
    is_admin_hdr = request.headers.get("X-Is-Admin", "false")

    if not (bot_user_id and timestamp_str and signature):
        return None

    api_key = os.getenv("MANAGER_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        timestamp = float(timestamp_str)
    except (ValueError, TypeError):
        return None

    # 5분(300초) 유효성 검증
    if abs(time.time() - timestamp) > 300:
        return None

    expected_msg = f"{timestamp_str}:{bot_user_id}:{request.url.path}".encode("utf-8")
    expected_sig = hmac.new(api_key.encode("utf-8"), expected_msg, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        return None

    is_admin = is_admin_hdr.lower() in ("true", "1")
    return {
        "email": f"bot_{bot_user_id}@telegram.local",
        "is_admin": is_admin,
        "bot_user_id": bot_user_id,
    }


def _require_login(request: Request):
    """Old style check, kept for compatibility during transition."""
    email = request.session.get("user_email")
    if email:
        return email
    bot_user = _extract_bot_auth_user(request)
    if bot_user:
        return bot_user["email"]
    return None


async def get_current_user(request: Request) -> dict:
    """Dependency to get the current logged-in user or HMAC authenticated bot proxy user."""
    email = request.session.get("user_email")
    if email:
        return {
            "email": email,
            "is_admin": bool(request.session.get("is_admin", False)),
            "bot_user_id": request.session.get("bot_user_id"),
        }

    bot_user = _extract_bot_auth_user(request)
    if bot_user:
        return bot_user

    raise HTTPException(status_code=401, detail="Unauthorized")


async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency to ensure the user is an admin."""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return current_user


def _require_admin(request: Request):
    """Old style check, kept for compatibility during transition."""
    bot_user = _extract_bot_auth_user(request)
    if bot_user:
        if not bot_user.get("is_admin"):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        return None

    if not request.session.get("user_email"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if not request.session.get("is_admin"):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    return None


def get_session_user(request: Request) -> dict:
    """Old style check, kept for compatibility during transition."""
    email = request.session.get("user_email")
    if email:
        return {
            "email": email,
            "is_admin": bool(request.session.get("is_admin", False)),
            "bot_user_id": request.session.get("bot_user_id"),
        }

    bot_user = _extract_bot_auth_user(request)
    if bot_user:
        return bot_user

    return {
        "email": None,
        "is_admin": False,
        "bot_user_id": None,
    }
