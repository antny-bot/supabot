import time
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import get_current_user

router = APIRouter()

_PERIODS = {"1d": 86400, "7d": 604800, "30d": 2592000, "all": None}


def _fmt_ts(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return "—"


def _parse_date_range(date_from: str | None, date_to: str | None) -> tuple[float | None, float | None]:
    ts_from = ts_to = None
    if date_from:
        ts_from = datetime.strptime(date_from, "%Y-%m-%d").timestamp()
    if date_to:
        ts_to = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).timestamp()
    return ts_from, ts_to


@router.get("/api/trades")
async def api_list_trades(
    period: str = "7d",
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user)
):
    if period not in _PERIODS:
        period = "7d"

    if page < 1: page = 1
    if page_size > 200: page_size = 200

    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    if not is_admin and not bot_user_id:
        return JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)

    try:
        db = get_db()
        q = db.table("trade_logs").select("*", count="exact").order("executed_at", desc=True)

        if date_from or date_to:
            ts_from, ts_to = _parse_date_range(date_from, date_to)
            date_conds = []
            if ts_from is not None:
                date_conds.append(f"executed_at.gte.{ts_from}")
            if ts_to is not None:
                date_conds.append(f"executed_at.lte.{ts_to}")
            if date_conds:
                q._params["and"] = f"({','.join(date_conds)})"
        else:
            window = _PERIODS[period]
            if window:
                q._params["executed_at"] = f"gte.{time.time() - window}"
        if not is_admin:
            q._params["user_id"] = f"eq.{bot_user_id}"
            
        # 페이지네이션 적용
        offset = (page - 1) * page_size
        q._params["limit"] = page_size
        q._params["offset"] = offset
        
        res = await q.execute()
        trades = res.data
        total_count = res.count or 0

        summary = {"total": total_count, "buy": 0, "sell": 0, "volume_krw": 0.0}
        
        # 요약 통계는 현재 페이지가 아닌 전체(또는 기간 내 전체)에 대해 필요할 수 있으나,
        # 성능을 위해 현재는 간소화하거나 별도 쿼리가 필요할 수 있음.
        # 일단 현재 리스트된 데이터에 대한 통계만 반환 (UI 요구사항에 따라 조절 가능)
        ex_agg: dict = defaultdict(lambda: {"count": 0, "krw": 0.0})
        st_agg: dict = defaultdict(lambda: {"count": 0, "krw": 0.0})

        for t in trades:
            price = t.get("price") or 0
            volume = t.get("volume") or 0
            krw = price * volume
            t["krw"] = krw
            t["executed_fmt"] = _fmt_ts(t.get("executed_at"))
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
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "summary": summary,
            "by_exchange": [{"name": k, **v} for k, v in sorted(ex_agg.items())],
            "by_strategy": [{"name": k, **v} for k, v in sorted(st_agg.items())],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
