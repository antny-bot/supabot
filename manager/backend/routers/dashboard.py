import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, RedirectResponse

from ..db import get_db
from ._auth import get_current_user

router = APIRouter()


def _iso_cutoff() -> str:
    kst = timezone(timedelta(hours=9))
    return (datetime.now(kst) - timedelta(days=1)).isoformat()


async def _build_stats(db):
    stats = {
        "users_total": 0,
        "users_active": 0,
        "users_pending": 0,
        "orders_open": 0,
        "trades_24h": 0,
        "errors_24h": 0,
    }

    stats["users_total"] = (await db.table("users").select("*", count="exact").execute()).count or 0
    stats["users_active"] = (await db.table("users").select("*", count="exact").eq("status", "active").execute()).count or 0
    stats["users_pending"] = (await db.table("users").select("*", count="exact").eq("status", "pending").execute()).count or 0

    open_statuses = ["wait", "partial", "pending_reorder"]
    stats["orders_open"] = (await db.table("orders").select("*", count="exact").in_("status", open_statuses).execute()).count or 0

    cutoff = time.time() - 86400
    trades_q = db.table("trade_logs").select("*", count="exact")
    trades_q._params["executed_at"] = f"gte.{cutoff}"
    stats["trades_24h"] = (await trades_q.execute()).count or 0

    errors_q = db.table("operational_events").select("*", count="exact").eq("level", "error")
    errors_q._params["created_at"] = f"gte.{_iso_cutoff()}"
    stats["errors_24h"] = (await errors_q.execute()).count or 0

    return stats


async def _build_user_stats(db, user_id: str) -> dict:
    stats = {"orders_open": 0, "trades_24h": 0}

    open_statuses = ["wait", "partial", "pending_reorder"]
    stats["orders_open"] = (
        await db.table("orders").select("*", count="exact")
        .eq("user_id", user_id)
        .in_("status", open_statuses)
        .execute()
    ).count or 0

    cutoff = time.time() - 86400
    trades_q = db.table("trade_logs").select("*", count="exact").eq("user_id", user_id)
    trades_q._params["executed_at"] = f"gte.{cutoff}"
    stats["trades_24h"] = (await trades_q.execute()).count or 0

    return stats


@router.get("/api/dashboard")
async def api_dashboard(user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    try:
        db = get_db()
        mfa_enabled = False
        if bot_user_id:
            rows = (await db.table("users").select("mfa_enabled").eq("user_id", bot_user_id).execute()).data
            mfa_enabled = bool(rows and rows[0].get("mfa_enabled", False))

        if is_admin:
            stats = await _build_stats(db)
            events = (
                await db.table("operational_events")
                .select("id,level,source,message,details,created_at,read_at,archived_at")
                .is_("read_at", "null")
                .is_("archived_at", "null")
                .order("id", desc=True)
                .limit(10)
                .execute()
            ).data
            return JSONResponse({"stats": stats, "recent_events": events, "mfa_enabled": mfa_enabled})

        if not bot_user_id:
            return JSONResponse({"error": "Linked bot account not found."}, status_code=403)

        stats = await _build_user_stats(db, bot_user_id)
        return JSONResponse({"stats": stats, "recent_events": [], "mfa_enabled": mfa_enabled})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/admin/dashboard")
async def dashboard_legacy():
    return RedirectResponse("/dashboard", status_code=302)
