import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import get_admin_user

router = APIRouter()
KST = timezone(timedelta(hours=9))
PERIOD_DAYS = {"1d": 1, "7d": 7, "30d": 30, "all": None}


def _cutoff(days: int | None) -> float | None:
    if days is None:
        return None
    return time.time() - days * 86400


def _apply_time_filter(query, cutoff: float | None):
    if cutoff is not None:
        query._params["created_at"] = f"gte.{cutoff}"
    return query


@router.get("/api/analytics/overview")
async def analytics_overview(_=Depends(get_admin_user)):
    db = get_db()
    now_ts = time.time()
    mau_cutoff = now_ts - 30 * 86400

    q = db.table("command_logs").select("user_id,created_at")
    q._params["created_at"] = f"gte.{mau_cutoff}"
    q._params["limit"] = 10000
    rows = (await q.execute()).data or []

    dau_cutoff = now_ts - 86400
    wau_cutoff = now_ts - 7 * 86400

    dau = len({r["user_id"] for r in rows if r["created_at"] >= dau_cutoff})
    wau = len({r["user_id"] for r in rows if r["created_at"] >= wau_cutoff})
    mau = len({r["user_id"] for r in rows})

    return JSONResponse({
        "dau": dau,
        "wau": wau,
        "mau": mau,
        "total_commands_30d": len(rows),
    })


@router.get("/api/analytics/activity")
async def analytics_activity(days: int = 30, _=Depends(get_admin_user)):
    if days > 90:
        days = 90
    cutoff = time.time() - days * 86400
    db = get_db()
    q = db.table("command_logs").select("created_at")
    q._params["created_at"] = f"gte.{cutoff}"
    q._params["limit"] = 10000
    rows = (await q.execute()).data or []

    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        dt = datetime.fromtimestamp(r["created_at"], tz=KST)
        counts[dt.strftime("%Y-%m-%d")] += 1

    result = []
    for i in range(days - 1, -1, -1):
        day = (datetime.now(KST) - timedelta(days=i)).strftime("%Y-%m-%d")
        result.append({"date": day, "count": counts.get(day, 0)})

    return JSONResponse({"activity": result})


@router.get("/api/analytics/commands")
async def analytics_commands(period: str = "7d", _=Depends(get_admin_user)):
    days = PERIOD_DAYS.get(period, 7)
    cutoff = _cutoff(days)
    db = get_db()
    q = db.table("command_logs").select("command,source")
    q = _apply_time_filter(q, cutoff)
    q._params["limit"] = 10000
    rows = (await q.execute()).data or []

    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r.get("command", "unknown")] += 1

    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:15]
    return JSONResponse({
        "commands": [{"command": cmd, "count": cnt} for cmd, cnt in top],
        "total": len(rows),
    })


@router.get("/api/analytics/users")
async def analytics_users(period: str = "7d", _=Depends(get_admin_user)):
    days = PERIOD_DAYS.get(period, 7)
    cutoff = _cutoff(days)
    db = get_db()
    q = db.table("command_logs").select("user_id,created_at")
    q = _apply_time_filter(q, cutoff)
    q._params["limit"] = 10000
    rows = (await q.execute()).data or []

    user_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "last_active": 0.0})
    for r in rows:
        uid = r["user_id"]
        user_stats[uid]["count"] += 1
        ts = r.get("created_at", 0.0)
        if ts > user_stats[uid]["last_active"]:
            user_stats[uid]["last_active"] = ts

    usernames: dict[str, str] = {}
    if user_stats:
        users_q = db.table("users").select("user_id,username").in_("user_id", list(user_stats.keys()))
        usernames = {u["user_id"]: u.get("username", "") for u in (await users_q.execute()).data or []}

    result = []
    for uid, stats in sorted(user_stats.items(), key=lambda x: x[1]["count"], reverse=True):
        last_ts = stats["last_active"]
        last_fmt = datetime.fromtimestamp(last_ts, tz=KST).strftime("%Y-%m-%d %H:%M") if last_ts else "-"
        result.append({
            "user_id": uid,
            "username": usernames.get(uid, ""),
            "count": stats["count"],
            "last_active": last_fmt,
            "last_active_ts": last_ts,
        })

    return JSONResponse({"users": result})


@router.get("/api/analytics/heatmap")
async def analytics_heatmap(_=Depends(get_admin_user)):
    cutoff = time.time() - 90 * 86400
    db = get_db()
    q = db.table("command_logs").select("created_at")
    q._params["created_at"] = f"gte.{cutoff}"
    q._params["limit"] = 10000
    rows = (await q.execute()).data or []

    # matrix[weekday 0-6][hour 0-23]  (0=월요일, 6=일요일)
    matrix = [[0] * 24 for _ in range(7)]
    for r in rows:
        dt = datetime.fromtimestamp(r["created_at"], tz=KST)
        matrix[dt.weekday()][dt.hour] += 1

    max_val = max((matrix[d][h] for d in range(7) for h in range(24)), default=1)
    return JSONResponse({"matrix": matrix, "max": max_val})
