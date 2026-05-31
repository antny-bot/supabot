from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..bot_client import notify
from ..db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

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


@router.get("/admin/users", response_class=HTMLResponse)
async def list_users(request: Request, status: str | None = None):
    if not _require_login(request):
        return RedirectResponse("/login", status_code=303)
    try:
        users = _get_users(status)
        error = None
    except Exception as e:
        users = []
        error = str(e)
    return templates.TemplateResponse(
        request,
        "users.html",
        {
            "users": users,
            "status_filter": status or "",
            "status_labels": _STATUS_LABELS,
            "error": error,
        },
    )


def _user_row_response(request: Request, user: dict | None, error: str | None = None):
    if user is None:
        return HTMLResponse(f'<tr><td colspan="6" class="text-danger">{error}</td></tr>')
    return templates.TemplateResponse(
        request,
        "user_row.html",
        {"user": user},
    )


@router.post("/admin/users/{user_id}/approve", response_class=HTMLResponse)
async def approve_user(user_id: str, request: Request):
    if not _require_login(request):
        return HTMLResponse("Unauthorized", status_code=401)
    try:
        user = _set_user_status(user_id, "active")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["active"])
    except Exception as e:
        return _user_row_response(request, None, str(e))
    return _user_row_response(request, user)


@router.post("/admin/users/{user_id}/deactivate", response_class=HTMLResponse)
async def deactivate_user(user_id: str, request: Request):
    if not _require_login(request):
        return HTMLResponse("Unauthorized", status_code=401)
    try:
        user = _set_user_status(user_id, "inactive")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["inactive"])
    except Exception as e:
        return _user_row_response(request, None, str(e))
    return _user_row_response(request, user)


@router.post("/admin/users/{user_id}/activate", response_class=HTMLResponse)
async def activate_user(user_id: str, request: Request):
    if not _require_login(request):
        return HTMLResponse("Unauthorized", status_code=401)
    try:
        user = _set_user_status(user_id, "active")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["active"])
    except Exception as e:
        return _user_row_response(request, None, str(e))
    return _user_row_response(request, user)


@router.post("/admin/users/{user_id}/block", response_class=HTMLResponse)
async def block_user(user_id: str, request: Request):
    if not _require_login(request):
        return HTMLResponse("Unauthorized", status_code=401)
    try:
        user = _set_user_status(user_id, "blocked")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["blocked"])
    except Exception as e:
        return _user_row_response(request, None, str(e))
    return _user_row_response(request, user)


@router.delete("/admin/users/{user_id}", response_class=HTMLResponse)
async def delete_user(user_id: str, request: Request):
    if not _require_login(request):
        return HTMLResponse("Unauthorized", status_code=401)
    try:
        user = _set_user_status(user_id, "deleted")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["deleted"])
    except Exception as e:
        return _user_row_response(request, None, str(e))
    return _user_row_response(request, user)
