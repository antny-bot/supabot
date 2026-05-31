from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

_STATUS_LABELS = {
    "wait": "대기",
    "partial": "부분체결",
    "done": "체결완료",
    "cancel": "취소",
    "pending_reorder": "재주문대기",
}

_OPEN_STATUSES = ("wait", "partial", "pending_reorder")


def _require_login(request: Request):
    return request.session.get("user_email")


def _fmt_ts(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return "—"


@router.get("/admin/orders", response_class=HTMLResponse)
async def list_orders(request: Request, status: str | None = None, exchange: str | None = None):
    if not _require_login(request):
        return RedirectResponse("/login", status_code=303)
    orders = []
    error = None
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
    except Exception as e:
        error = str(e)
    return templates.TemplateResponse(
        request,
        "orders.html",
        {
            "orders": orders,
            "status_filter": status or "",
            "exchange_filter": exchange or "",
            "status_labels": _STATUS_LABELS,
            "error": error,
        },
    )
