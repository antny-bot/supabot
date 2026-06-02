from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import get_current_user

router = APIRouter()

_STATUS_LABELS = {
    "wait": "대기",
    "partial": "부분체결",
    "done": "체결완료",
    "cancel": "취소",
    "pending_reorder": "재주문대기",
    "stoploss": "손절",
}

_OPEN_STATUSES = ("wait", "partial", "pending_reorder")


def _fmt_ts(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return "—"


@router.get("/api/orders")
async def api_list_orders(
    status: str | None = None, 
    exchange: str | None = None,
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user)
):
    if page < 1: page = 1
    if page_size > 200: page_size = 200

    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    if not is_admin and not bot_user_id:
        return JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)

    try:
        db = get_db()
        q = db.table("orders").select("*", count="exact").order("created_at", desc=True)
        if status == "open":
            q._params["status"] = "in.({})".format(",".join(_OPEN_STATUSES))
        elif status:
            q._params["status"] = f"eq.{status}"
        if exchange:
            q._params["exchange"] = f"eq.{exchange}"
        if not is_admin:
            q._params["user_id"] = f"eq.{bot_user_id}"
            
        offset = (page - 1) * page_size
        q._params["limit"] = page_size
        q._params["offset"] = offset

        res = await q.execute()
        orders = res.data
        total_count = res.count or 0
        
        for o in orders:
            o["status_label"] = _STATUS_LABELS.get(o.get("status", ""), o.get("status", ""))
            o["created_fmt"] = _fmt_ts(o.get("created_at"))
            price = float(o.get("price") or 0)
            vol = float(o.get("volume") or 0)
            filled = float(o.get("filled_volume") or 0)
            o["order_value"] = price * vol
            o["fill_pct"] = round(filled / vol * 100) if vol else 0
            
        return JSONResponse({
            "orders": orders,
            "total": total_count,
            "page": page,
            "page_size": page_size
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
