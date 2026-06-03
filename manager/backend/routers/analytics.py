"""
Analytics router.

데이터 소스:
  - command_log_daily : 전날까지의 집계 요약 (pg_cron이 매일 01:00 KST 생성)
  - command_logs      : 오늘(KST) 실시간 raw 로그

두 소스를 Python에서 union해 항상 오늘 데이터까지 포함한 결과를 반환한다.
"""
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import get_admin_user

router = APIRouter()
KST = timezone(timedelta(hours=9))
PERIOD_DAYS = {"1d": 1, "7d": 7, "30d": 30, "all": None}


# ── 공통 fetch 헬퍼 ───────────────────────────────────────────────────────────

def _kst_today() -> date:
    return datetime.now(KST).date()


def _kst_today_epoch() -> float:
    """오늘 KST 자정의 Unix timestamp"""
    today = _kst_today()
    return datetime(today.year, today.month, today.day, tzinfo=KST).timestamp()


async def _fetch_daily(db, days: int | None, columns: str) -> list[dict]:
    """command_log_daily에서 집계 행 조회"""
    q = db.table("command_log_daily").select(columns)
    if days is not None:
        cutoff_date = (_kst_today() - timedelta(days=days)).isoformat()
        q._params["date"] = f"gte.{cutoff_date}"
    q._params["limit"] = 20000
    return (await q.execute()).data or []


async def _fetch_today_raw(db, columns: str) -> list[dict]:
    """command_logs에서 오늘(KST) raw 로그 조회"""
    q = db.table("command_logs").select(columns)
    q._params["created_at"] = f"gte.{_kst_today_epoch()}"
    q._params["limit"] = 5000
    return (await q.execute()).data or []


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.get("/api/analytics/overview")
async def analytics_overview(_=Depends(get_admin_user)):
    db = get_db()
    today = _kst_today()

    daily = await _fetch_daily(db, 30, "date,user_id,count")
    raw   = await _fetch_today_raw(db, "user_id")

    today_users: set[str] = {r["user_id"] for r in raw}
    total_30d = len(raw)

    dau_users: set[str] = set(today_users)
    wau_users: set[str] = set(today_users)
    mau_users: set[str] = set(today_users)

    for r in daily:
        uid  = r["user_id"]
        cnt  = r.get("count", 0)
        days_ago = (today - date.fromisoformat(r["date"])).days
        total_30d += cnt
        mau_users.add(uid)
        if days_ago <= 7:
            wau_users.add(uid)
        if days_ago <= 1:
            dau_users.add(uid)

    return JSONResponse({
        "dau": len(dau_users),
        "wau": len(wau_users),
        "mau": len(mau_users),
        "total_commands_30d": total_30d,
    })


@router.get("/api/analytics/activity")
async def analytics_activity(days: int = 30, _=Depends(get_admin_user)):
    days = min(days, 90)
    db   = get_db()

    daily = await _fetch_daily(db, days, "date,count")
    raw   = await _fetch_today_raw(db, "created_at")

    counts: dict[str, int] = defaultdict(int)
    for r in daily:
        counts[r["date"]] += r.get("count", 0)

    today_str = _kst_today().isoformat()
    counts[today_str] += len(raw)

    result = []
    for i in range(days - 1, -1, -1):
        day = (_kst_today() - timedelta(days=i)).isoformat()
        result.append({"date": day, "count": counts.get(day, 0)})

    return JSONResponse({"activity": result})


@router.get("/api/analytics/commands")
async def analytics_commands(period: str = "7d", _=Depends(get_admin_user)):
    days = PERIOD_DAYS.get(period, 7)
    db   = get_db()

    daily = await _fetch_daily(db, days, "command,count")
    raw   = await _fetch_today_raw(db, "command")

    counts: dict[str, int] = defaultdict(int)
    for r in daily:
        counts[r["command"]] += r.get("count", 0)
    for r in raw:
        counts[r["command"]] += 1

    top   = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:15]
    total = sum(counts.values())

    return JSONResponse({
        "commands": [{"command": cmd, "count": cnt} for cmd, cnt in top],
        "total": total,
    })


@router.get("/api/analytics/users")
async def analytics_users(period: str = "7d", _=Depends(get_admin_user)):
    days = PERIOD_DAYS.get(period, 7)
    db   = get_db()

    daily = await _fetch_daily(db, days, "date,user_id,count")
    raw   = await _fetch_today_raw(db, "user_id,created_at")

    # user_id → {count, last_date}
    stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "last_date": "", "last_ts": 0.0})

    for r in daily:
        uid = r["user_id"]
        stats[uid]["count"] += r.get("count", 0)
        if r["date"] > stats[uid]["last_date"]:
            stats[uid]["last_date"] = r["date"]

    today_str = _kst_today().isoformat()
    for r in raw:
        uid = r["user_id"]
        stats[uid]["count"] += 1
        ts = r.get("created_at", 0.0)
        if today_str >= stats[uid]["last_date"]:
            stats[uid]["last_date"] = today_str
        if ts > stats[uid]["last_ts"]:
            stats[uid]["last_ts"] = ts

    # 유저명 조회
    usernames: dict[str, str] = {}
    if stats:
        rows = (await db.table("users").select("user_id,username")
                .in_("user_id", list(stats.keys())).execute()).data or []
        usernames = {u["user_id"]: u.get("username", "") for u in rows}

    result = []
    for uid, s in sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True):
        last_ts  = s["last_ts"]
        last_fmt = (datetime.fromtimestamp(last_ts, tz=KST).strftime("%Y-%m-%d %H:%M")
                    if last_ts else s["last_date"])
        result.append({
            "user_id":      uid,
            "username":     usernames.get(uid, ""),
            "count":        s["count"],
            "last_active":  last_fmt,
            "last_active_ts": last_ts,
        })

    return JSONResponse({"users": result})


@router.get("/api/analytics/heatmap")
async def analytics_heatmap(_=Depends(get_admin_user)):
    db = get_db()

    # 최근 90일 요약 — hour_of_day·weekday 컬럼 활용
    daily = await _fetch_daily(db, 90, "weekday,hour_of_day,count")
    raw   = await _fetch_today_raw(db, "created_at")

    matrix = [[0] * 24 for _ in range(7)]

    for r in daily:
        wd  = r.get("weekday",     0)
        hr  = r.get("hour_of_day", 0)
        cnt = r.get("count",       0)
        if 0 <= wd <= 6 and 0 <= hr <= 23:
            matrix[wd][hr] += cnt

    for r in raw:
        dt = datetime.fromtimestamp(r["created_at"], tz=KST)
        matrix[dt.weekday()][dt.hour] += 1

    max_val = max((matrix[d][h] for d in range(7) for h in range(24)), default=1)
    return JSONResponse({"matrix": matrix, "max": max_val})
