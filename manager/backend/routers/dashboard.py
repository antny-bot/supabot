import json
import os
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, RedirectResponse

from ..bot_client import get_bot_backup_status
from ..db import get_db, get_supabase_health_stats
from ._auth import get_current_user

router = APIRouter()


def _iso_cutoff() -> str:
    kst = timezone(timedelta(hours=9))
    return (datetime.now(kst) - timedelta(days=1)).isoformat()


async def _calc_24h_pnl_and_status(db, user_id: str | None = None) -> tuple[int, str]:
    cutoff = time.time() - 86400
    try:
        q = db.table("trade_logs").select("side,price,volume,fee_amount")
        q._params["executed_at"] = f"gte.{cutoff}"
        if user_id:
            q._params["user_id"] = f"eq.{user_id}"
        trades = (await q.execute()).data or []

        ask_total = 0.0
        bid_total = 0.0
        fee_total = 0.0
        for t in trades:
            krw = float(t.get("price") or 0) * float(t.get("volume") or 0)
            fee = float(t.get("fee_amount") or t.get("fee") or 0)
            fee_total += fee
            if t.get("side") == "ask":
                ask_total += krw
            elif t.get("side") == "bid":
                bid_total += krw
        pnl_24h = round(ask_total - bid_total - fee_total)
    except Exception:
        pnl_24h = 0

    # 봇 활성 상태 점검 (1차: system_config bot_heartbeat, 2차: operational_events)
    bot_status = "offline"
    try:
        latest_ts_str = None
        hb_q = db.table("system_config").select("value").eq("key", "bot_heartbeat").limit(1)
        hb_data = (await hb_q.execute()).data
        if hb_data and hb_data[0].get("value"):
            latest_ts_str = hb_data[0]["value"]
        else:
            status_q = db.table("operational_events").select("created_at").order("id", desc=True).limit(1)
            ev_data = (await status_q.execute()).data
            if ev_data and ev_data[0].get("created_at"):
                latest_ts_str = ev_data[0]["created_at"]

        if latest_ts_str:
            dt = datetime.fromisoformat(latest_ts_str.replace("Z", "+00:00"))
            now_utc = datetime.now(timezone.utc)
            diff_min = (now_utc - dt).total_seconds() / 60
            if diff_min <= 10:
                bot_status = "online"
            elif diff_min <= 30:
                bot_status = "idle"
            else:
                bot_status = "offline"
        else:
            bot_status = "online"
    except Exception:
        bot_status = "online"

    return pnl_24h, bot_status


async def _build_backup_health(db) -> dict:
    """백업 스케줄러 상태 및 Health 지표 계산."""
    state = {}
    cfg = {}
    try:
        ok, bot_res = await get_bot_backup_status()
        if ok and isinstance(bot_res, dict):
            state = bot_res.get("state") or {}
            cfg = bot_res.get("config") or {}
    except Exception:
        pass

    if not state or not cfg:
        # 로컬 폴백
        STATE_FILE = "data/backup_state.json"
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except Exception:
                pass
        try:
            rows = (await db.table("system_config").select("key,value").execute()).data or []
            row_dict = {r["key"]: r["value"] for r in rows}
            if "backup_enabled" in row_dict:
                cfg["enabled"] = row_dict["backup_enabled"].lower() in ("true", "1", "yes")
            if "backup_schedule_type" in row_dict:
                cfg["schedule_type"] = row_dict["backup_schedule_type"]
            if "backup_interval_hours" in row_dict:
                cfg["interval_hours"] = int(row_dict["backup_interval_hours"])
            if "backup_days_of_week" in row_dict:
                v = row_dict["backup_days_of_week"]
                if isinstance(v, str):
                    try:
                        v = json.loads(v)
                    except Exception:
                        v = [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
                cfg["days_of_week"] = v
            if "backup_time_of_day" in row_dict:
                cfg["time_of_day"] = row_dict["backup_time_of_day"]
        except Exception:
            pass

    enabled = cfg.get("enabled", True)
    last_status = state.get("last_status", "none")
    last_success_at = state.get("last_success_at")
    last_error = state.get("last_error")
    gdrive_enabled = cfg.get("gdrive_enabled", False)
    total_rows = state.get("total_rows", 0)

    if not enabled:
        health_grade = "DISABLED"
        health_message = "정기 백업이 비활성화되어 있습니다."
    elif last_status == "error":
        health_grade = "CRITICAL"
        health_message = "최근 백업 실패 (관리자 확인 필요)"
    elif last_status == "partial_error":
        health_grade = "WARNING"
        health_message = "로컬 백업 완료 (Google Drive 업로드 실패)"
    elif last_status == "success":
        health_grade = "HEALTHY"
        gdrive_desc = "Google Drive" if gdrive_enabled else "로컬"
        health_message = f"정기 백업 정상 가동 중 ({gdrive_desc}, {total_rows:,}행 백업)"
    else:
        health_grade = "WARNING"
        health_message = "백업 이력 없음 (첫 실행 대기 중)"

    return {
        "enabled": enabled,
        "health_grade": health_grade,
        "health_message": health_message,
        "last_status": last_status,
        "last_success_at": last_success_at,
        "last_backup_file": state.get("last_backup_file"),
        "last_backup_size": state.get("last_backup_size", 0),
        "last_error": last_error,
        "schedule_type": cfg.get("schedule_type", "interval"),
        "interval_hours": cfg.get("interval_hours", 24),
        "days_of_week": cfg.get("days_of_week", [0, 1, 2, 3, 4, 5, 6]),
        "time_of_day": cfg.get("time_of_day", "04:00"),
        "gdrive_enabled": gdrive_enabled,
        "total_rows": total_rows,
    }


async def _build_stats(db):
    stats = {
        "users_total": 0,
        "users_active": 0,
        "users_pending": 0,
        "orders_open": 0,
        "trades_24h": 0,
        "errors_24h": 0,
        "realized_pnl_24h": 0,
        "bot_status": "offline",
    }

    stats["users_total"] = (await db.table("users").select("*", count="exact").execute()).count or 0
    stats["users_active"] = (await db.table("users").select("*", count="exact").eq("status", "active").execute()).count or 0
    stats["users_pending"] = (await db.table("users").select("*", count="exact").eq("status", "pending").execute()).count or 0

    open_statuses = ["wait", "partial", "pending_reorder", "reserved", "cancel_requested"]
    stats["orders_open"] = (await db.table("orders").select("*", count="exact").in_("status", open_statuses).execute()).count or 0

    cutoff = time.time() - 86400
    trades_q = db.table("trade_logs").select("*", count="exact")
    trades_q._params["executed_at"] = f"gte.{cutoff}"
    stats["trades_24h"] = (await trades_q.execute()).count or 0

    errors_q = db.table("operational_events").select("*", count="exact").eq("level", "error")
    errors_q._params["created_at"] = f"gte.{_iso_cutoff()}"
    stats["errors_24h"] = (await errors_q.execute()).count or 0

    pnl_24h, b_status = await _calc_24h_pnl_and_status(db)
    stats["realized_pnl_24h"] = pnl_24h
    stats["bot_status"] = b_status

    return stats


async def _build_user_stats(db, user_id: str) -> dict:
    stats = {
        "orders_open": 0,
        "trades_24h": 0,
        "realized_pnl_24h": 0,
        "bot_status": "offline",
    }

    open_statuses = ["wait", "partial", "pending_reorder", "reserved", "cancel_requested"]
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

    pnl_24h, b_status = await _calc_24h_pnl_and_status(db, user_id)
    stats["realized_pnl_24h"] = pnl_24h
    stats["bot_status"] = b_status

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
            backup_health = await _build_backup_health(db)

            events = (
                await db.table("operational_events")
                .select("id,level,source,message,details,created_at,read_at,archived_at")
                .is_("read_at", "null")
                .is_("archived_at", "null")
                .order("id", desc=True)
                .limit(10)
                .execute()
            ).data
            try:
                db_health = await get_supabase_health_stats(db)
            except Exception:
                db_health = None
            return JSONResponse({
                "stats": stats,
                "recent_events": events,
                "mfa_enabled": mfa_enabled,
                "db_health": db_health,
                "backup_health": backup_health,
            })

        if not bot_user_id:
            return JSONResponse({"error": "Linked bot account not found."}, status_code=403)

        stats = await _build_user_stats(db, bot_user_id)
        return JSONResponse({
            "stats": stats,
            "recent_events": [],
            "mfa_enabled": mfa_enabled,
        })
    except Exception as e:
        return JSONResponse({"error": "Internal error"}, status_code=500)


@router.get("/admin/dashboard")
async def dashboard_legacy():
    return RedirectResponse("/dashboard", status_code=302)
