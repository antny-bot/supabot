from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import get_db

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


def _require_login(request: Request):
    return request.session.get("user_email")


def _fmt_ts(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return "—"


@router.get("/api/orders")
async def api_list_orders(request: Request, status: str | None = None, exchange: str | None = None):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        q = get_db().table("orders").select("*").order("created_at", desc=True).limit(300)
        if status == "open":
            q._params["status"] = "in.({})".format(",".join(_OPEN_STATUSES))
        elif status:
            q._params["status"] = f"eq.{status}"
        if exchange:
            q._params["exchange"] = f"eq.{exchange}"
        orders = q.execute().data
        for o in orders:
            o["status_label"] = _STATUS_LABELS.get(o.get("status", ""), o.get("status", ""))
            o["created_fmt"] = _fmt_ts(o.get("created_at"))
            vol = o.get("volume") or 0
            filled = o.get("filled_volume") or 0
            o["fill_pct"] = round(filled / vol * 100) if vol else 0
        return JSONResponse(orders)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
