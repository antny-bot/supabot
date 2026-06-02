from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse


def _require_login(request: Request):
    """Old style check, kept for compatibility during transition."""
    return request.session.get("user_email")


async def get_current_user(request: Request) -> dict:
    """Dependency to get the current logged-in user."""
    email = request.session.get("user_email")
    if not email:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    return {
        "email": email,
        "is_admin": bool(request.session.get("is_admin", False)),
        "bot_user_id": request.session.get("bot_user_id"),
    }


async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency to ensure the user is an admin."""
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return current_user


def _require_admin(request: Request):
    """Old style check, kept for compatibility during transition."""
    if not request.session.get("user_email"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if not request.session.get("is_admin"):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    return None


def get_session_user(request: Request) -> dict:
    """Old style check, kept for compatibility during transition."""
    return {
        "email": request.session.get("user_email"),
        "is_admin": bool(request.session.get("is_admin", False)),
        "bot_user_id": request.session.get("bot_user_id"),
    }
