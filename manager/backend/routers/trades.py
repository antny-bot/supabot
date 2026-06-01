import time
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import _require_login, get_session_user

router = APIRouter()

_PERIODS = {"1d": 86400, "7d": 604800, "30d": 2592000, "all": None}


def _fmt_ts(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return "—"


@router.get("/api/trades")
async def api_list_trades(request: Request, period: str = "7d"):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if period not in _PERIODS:
        period = "7d"

    session_user = get_session_user(request)
    is_admin = session_user["is_admin"]
    bot_user_id = session_user["bot_user_id"]

    if not is_admin and not bot_user_id:
        return JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)

    try:
        q = get_db().table("trade_logs").select("*").order("executed_at", desc=True).limit(500)
        window = _PERIODS[period]
        if window:
            q._params["executed_at"] = f"gte.{time.time() - window}"
        if not is_admin:
            q._params["user_id"] = f"eq.{bot_user_id}"
        trades = q.execute().data

        summary = {"total": 0, "buy": 0, "sell": 0, "volume_krw": 0.0}
        ex_agg: dict = defaultdict(lambda: {"count": 0, "krw": 0.0})
        st_agg: dict = defaultdict(lambda: {"count": 0, "krw": 0.0})

        for t in trades:
            price = t.get("price") or 0
            volume = t.get("volume") or 0
            krw = price * volume
            t["krw"] = krw
            t["executed_fmt"] = _fmt_ts(t.get("executed_at"))
            summary["total"] += 1
            if t.get("side") == "bid":
                summary["buy"] += 1
            elif t.get("side") == "ask":
                summary["sell"] += 1
            summary["volume_krw"] += krw
            ex = t.get("exchange") or "—"
            ex_agg[ex]["count"] += 1
            ex_agg[ex]["krw"] += krw
            st = t.get("strategy") or "manual"
            st_agg[st]["count"] += 1
            st_agg[st]["krw"] += krw

        return JSONResponse({
            "trades": trades,
            "summary": summary,
            "by_exchange": [{"name": k, **v} for k, v in sorted(ex_agg.items())],
            "by_strategy": [{"name": k, **v} for k, v in sorted(st_agg.items())],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
