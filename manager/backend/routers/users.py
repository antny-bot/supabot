from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..bot_client import notify
from ..db import get_db

router = APIRouter()

_STATUS_LABELS = {
    "pending": "대기",
    "active": "활성",
    "inactive": "비활성",
    "blocked": "차단",
    "deleted": "삭제",
}

_NOTIFY_MESSAGES = {
    "active": "✅ 계정이 승인되었습니다. 봇을 사용할 수 있습니다.",
    "inactive": "⏸ 계정이 비활성화되었습니다.",
    "blocked": "🚫 계정이 차단되었습니다. 관리자에게 문의하세요.",
    "deleted": "❌ 계정이 삭제되었습니다.",
}


def _require_login(request: Request):
    return request.session.get("user_email")


def _get_users(status_filter: str | None = None) -> list[dict]:
    db = get_db()
    q = db.table("users").select("*").order("created_at", desc=True)
    if status_filter:
        q._params["status"] = f"eq.{status_filter}"
    rows = q.execute().data
    for r in rows:
        r["status_label"] = _STATUS_LABELS.get(r.get("status", ""), r.get("status", ""))
    return rows


def _set_user_status(user_id: str, status: str) -> dict | None:
    db = get_db()
    db.table("users").update({"status": status}).eq("user_id", user_id).execute()
    rows = db.table("users").select("*").eq("user_id", user_id).execute().data
    if rows:
        r = rows[0]
        r["status_label"] = _STATUS_LABELS.get(r.get("status", ""), r.get("status", ""))
        return r
    return None


@router.get("/api/users")
async def api_list_users(request: Request, status: str | None = None):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        return JSONResponse(_get_users(status))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/users/{user_id}/approve")
async def api_approve_user(user_id: str, request: Request):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        user = _set_user_status(user_id, "active")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["active"])
        return JSONResponse(user)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/users/{user_id}/deactivate")
async def api_deactivate_user(user_id: str, request: Request):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        user = _set_user_status(user_id, "inactive")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["inactive"])
        return JSONResponse(user)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/users/{user_id}/activate")
async def api_activate_user(user_id: str, request: Request):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        user = _set_user_status(user_id, "active")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["active"])
        return JSONResponse(user)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/users/{user_id}/block")
async def api_block_user(user_id: str, request: Request):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        user = _set_user_status(user_id, "blocked")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["blocked"])
        return JSONResponse(user)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/api/users/{user_id}")
async def api_delete_user(user_id: str, request: Request):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        user = _set_user_status(user_id, "deleted")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["deleted"])
        return JSONResponse(user)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
