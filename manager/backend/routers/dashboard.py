import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..db import get_db
from ._auth import _require_login, get_session_user

router = APIRouter()


def _build_stats(db):
    stats = {
        "users_total": 0,
        "users_active": 0,
        "users_pending": 0,
        "orders_open": 0,
        "trades_24h": 0,
        "errors_24h": 0,
    }
    users = db.table("users").select("status").execute().data
    stats["users_total"] = len(users)
    stats["users_active"] = sum(1 for u in users if u.get("status") == "active")
    stats["users_pending"] = sum(1 for u in users if u.get("status") == "pending")

    orders = db.table("orders").select("status").execute().data
    stats["orders_open"] = sum(
        1 for o in orders if o.get("status") in ("wait", "partial", "pending_reorder")
    )

    cutoff = time.time() - 86400
    trades = (
        db.table("trade_logs").select("executed_at")
        .order("executed_at", desc=True).limit(500).execute().data
    )
    stats["trades_24h"] = sum(1 for t in trades if (t.get("executed_at") or 0) >= cutoff)

    all_errors = (
        db.table("operational_events").select("level,created_at")
        .order("id", desc=True).limit(500).execute().data
    )
    stats["errors_24h"] = sum(
        1 for e in all_errors
        if e.get("level") == "error" and str(e.get("created_at", "")) >= _iso_cutoff()
    )
    return stats


def _build_user_stats(db, user_id: str) -> dict:
    stats = {"orders_open": 0, "trades_24h": 0}
    orders = db.table("orders").select("status").eq("user_id", user_id).execute().data
    stats["orders_open"] = sum(
        1 for o in orders if o.get("status") in ("wait", "partial", "pending_reorder")
    )
    cutoff = time.time() - 86400
    trades = (
        db.table("trade_logs").select("executed_at")
        .eq("user_id", user_id)
        .order("executed_at", desc=True).limit(500).execute().data
    )
    stats["trades_24h"] = sum(1 for t in trades if (t.get("executed_at") or 0) >= cutoff)
    return stats


@router.get("/api/dashboard")
async def api_dashboard(request: Request):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    session_user = get_session_user(request)
    is_admin = session_user["is_admin"]
    bot_user_id = session_user["bot_user_id"]

    try:
        db = get_db()
        if is_admin:
            stats = _build_stats(db)
            events = (
                db.table("operational_events").select("level,source,message,created_at")
                .order("id", desc=True).limit(10).execute().data
            )
            return JSONResponse({"stats": stats, "recent_events": events})
        else:
            if not bot_user_id:
                return JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)
            stats = _build_user_stats(db, bot_user_id)
            return JSONResponse({"stats": stats, "recent_events": []})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Legacy HTML route (kept for fallback)
@router.get("/admin/dashboard")
async def dashboard(request: Request):
    if not _require_login(request):
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/dashboard", status_code=302)


def _iso_cutoff() -> str:
    from datetime import datetime, timedelta, timezone
    kst = timezone(timedelta(hours=9))
    return (datetime.now(kst) - timedelta(days=1)).isoformat()
