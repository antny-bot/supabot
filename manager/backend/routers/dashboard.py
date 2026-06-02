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
    
    # DB 레벨에서 카운트 최적화
    stats["users_total"] = (await db.table("users").select("*", count="exact").execute()).count or 0
    stats["users_active"] = (await db.table("users").select("*", count="exact").eq("status", "active").execute()).count or 0
    stats["users_pending"] = (await db.table("users").select("*", count="exact").eq("status", "pending").execute()).count or 0

    # Open Orders 카운트 (DB에서 필터링하여 카운트만 가져옴)
    # Supabase/PostgREST에서는 복합 필터링이 가능하므로 in_(...) 활용
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
        if is_admin:
            stats = await _build_stats(db)
            events = (
                await db.table("operational_events").select("level,source,message,created_at")
                .order("id", desc=True).limit(10).execute()
            ).data
            return JSONResponse({"stats": stats, "recent_events": events})
        else:
            if not bot_user_id:
                return JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)
            stats = await _build_user_stats(db, bot_user_id)
            return JSONResponse({"stats": stats, "recent_events": []})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/admin/dashboard")
async def dashboard_legacy():
    return RedirectResponse("/dashboard", status_code=302)
