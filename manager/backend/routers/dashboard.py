import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


def _require_login(request: Request):
    return request.session.get("user_email")


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


@router.get("/api/dashboard")
async def api_dashboard(request: Request):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        db = get_db()
        stats = _build_stats(db)
        events = (
            db.table("operational_events").select("level,source,message,created_at")
            .order("id", desc=True).limit(10).execute().data
        )
        return JSONResponse({"stats": stats, "recent_events": events})
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
