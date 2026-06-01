from fastapi import Request
from fastapi.responses import JSONResponse


def _require_login(request: Request):
    return request.session.get("user_email")


def _require_admin(request: Request):
    if not request.session.get("user_email"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if not request.session.get("is_admin"):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    return None


def get_session_user(request: Request) -> dict:
    return {
        "email": request.session.get("user_email"),
        "is_admin": bool(request.session.get("is_admin", False)),
        "bot_user_id": request.session.get("bot_user_id"),
    }
