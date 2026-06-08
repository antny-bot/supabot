from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..auth import invite_auth_user, send_password_reset_email
from ..bot_client import notify
from ..db import get_db
from ._auth import get_admin_user

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


async def _get_users(status_filter: str | None = None) -> list[dict]:
    db = get_db()
    q = db.table("users").select("*").order("created_at", desc=True)
    if status_filter:
        q._params["status"] = f"eq.{status_filter}"
    rows = (await q.execute()).data
    for r in rows:
        r["status_label"] = _STATUS_LABELS.get(r.get("status", ""), r.get("status", ""))
    return rows


async def _set_user_status(user_id: str, status: str) -> dict | None:
    db = get_db()
    await db.table("users").update({"status": status}).eq("user_id", user_id).execute()
    rows = (await db.table("users").select("*").eq("user_id", user_id).execute()).data
    if rows:
        r = rows[0]
        r["status_label"] = _STATUS_LABELS.get(r.get("status", ""), r.get("status", ""))
        return r
    return None


@router.get("/api/users")
async def api_list_users(status: str | None = None, _=Depends(get_admin_user)):
    try:
        return JSONResponse(await _get_users(status))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/users/{user_id}/approve")
async def api_approve_user(user_id: str, _=Depends(get_admin_user)):
    try:
        user = await _set_user_status(user_id, "active")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["active"])
        return JSONResponse(user)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/users/{user_id}/deactivate")
async def api_deactivate_user(user_id: str, _=Depends(get_admin_user)):
    try:
        user = await _set_user_status(user_id, "inactive")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["inactive"])
        return JSONResponse(user)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/users/{user_id}/activate")
async def api_activate_user(user_id: str, _=Depends(get_admin_user)):
    try:
        user = await _set_user_status(user_id, "active")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["active"])
        return JSONResponse(user)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/users/{user_id}/block")
async def api_block_user(user_id: str, _=Depends(get_admin_user)):
    try:
        user = await _set_user_status(user_id, "blocked")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["blocked"])
        return JSONResponse(user)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/api/users/{user_id}")
async def api_delete_user(user_id: str, _=Depends(get_admin_user)):
    try:
        user = await _set_user_status(user_id, "deleted")
        if user:
            notify(user_id, _NOTIFY_MESSAGES["deleted"])
        return JSONResponse(user)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/users/{user_id}/invite-auth-account")
async def api_invite_auth_account(user_id: str, _=Depends(get_admin_user)):
    try:
        db = get_db()
        rows = (await db.table("users").select("manager_email,manager_invited_at").eq("user_id", user_id).execute()).data
        if not rows:
            return JSONResponse({"error": "User not found"}, status_code=404)
        email = rows[0].get("manager_email")
        if not email:
            return JSONResponse({"error": "먼저 매니저 이메일을 설정해야 합니다."}, status_code=400)
        if rows[0].get("manager_invited_at"):
            return JSONResponse({"error": "이미 초대 메일을 발송했습니다. 비밀번호 재설정을 이용하세요."}, status_code=409)
        ok, err = invite_auth_user(email)
        if not ok:
            return JSONResponse({"error": f"초대 메일 발송 실패: {err}"}, status_code=409)
        invited_at = datetime.now(timezone.utc).isoformat()
        await db.table("users").update({"manager_invited_at": invited_at}).eq("user_id", user_id).execute()
        updated = (await db.table("users").select("*").eq("user_id", user_id).execute()).data
        if updated:
            r = updated[0]
            r["status_label"] = _STATUS_LABELS.get(r.get("status", ""), r.get("status", ""))
            return JSONResponse(r)
        return JSONResponse({"error": "User not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/users/{user_id}/reset-auth-password")
async def api_reset_auth_password(user_id: str, _=Depends(get_admin_user)):
    try:
        db = get_db()
        rows = (await db.table("users").select("manager_email,manager_invited_at").eq("user_id", user_id).execute()).data
        if not rows:
            return JSONResponse({"error": "User not found"}, status_code=404)
        email = rows[0].get("manager_email")
        if not email:
            return JSONResponse({"error": "먼저 매니저 이메일을 설정해야 합니다."}, status_code=400)
        if not rows[0].get("manager_invited_at"):
            return JSONResponse({"error": "아직 초대 메일을 발송하지 않았습니다. 초대 메일 발송을 먼저 이용하세요."}, status_code=400)
        ok, err = send_password_reset_email(email)
        if not ok:
            return JSONResponse({"error": f"비밀번호 재설정 메일 발송 실패: {err}"}, status_code=409)
        return JSONResponse({"email": email, "ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.patch("/api/users/{user_id}/email")
async def api_set_user_email(user_id: str, request: Request, _=Depends(get_admin_user)):
    try:
        body = await request.json()
        email = body.get("email", "").strip().lower() or None
        db = get_db()
        if email:
            existing = (await db.table("users").select("user_id").eq("manager_email", email).execute()).data
            if existing and existing[0]["user_id"] != user_id:
                return JSONResponse({"error": "이메일이 이미 다른 유저에게 사용 중입니다."}, status_code=409)
        await db.table("users").update({"manager_email": email}).eq("user_id", user_id).execute()
        rows = (await db.table("users").select("*").eq("user_id", user_id).execute()).data
        if rows:
            r = rows[0]
            r["status_label"] = _STATUS_LABELS.get(r.get("status", ""), r.get("status", ""))
            return JSONResponse(r)
        return JSONResponse({"error": "User not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
