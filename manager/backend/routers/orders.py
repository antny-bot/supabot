from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import get_current_user
from .. import bot_client

router = APIRouter()

_STATUS_LABELS = {
    "wait": "대기",
    "partial": "부분체결",
    "done": "체결완료",
    "cancel": "취소",
    "pending_reorder": "재주문대기",
    "reserved": "예약",
    "stoploss": "손절",
}

_OPEN_STATUSES = ("wait", "partial", "pending_reorder", "reserved")


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


@router.get("/api/orders")
async def api_list_orders(
    status: str | None = None,
    exchange: str | None = None,
    side: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    group_no: int | None = None,
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
        if side:
            q._params["side"] = f"eq.{side}"
        ts_from, ts_to = _parse_date_range(date_from, date_to)
        date_conds = []
        if ts_from is not None:
            date_conds.append(f"created_at.gte.{ts_from}")
        if ts_to is not None:
            date_conds.append(f"created_at.lte.{ts_to}")
        if date_conds:
            q._params["and"] = f"({','.join(date_conds)})"
        if group_no is not None:
            q._params["group_no"] = f"eq.{group_no}"
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


@router.post("/api/orders/{uuid}/cancel")
async def api_cancel_order(uuid: str, user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    if not is_admin and not bot_user_id:
        raise HTTPException(status_code=403, detail="연결된 봇 계정이 없습니다.")

    try:
        db = get_db()
        res = await db.table("orders").select("uuid,user_id,exchange,ticker,status").eq("uuid", uuid).execute()
        rows = res.data
        if not rows:
            raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
        order = rows[0]

        if not is_admin and order["user_id"] != bot_user_id:
            raise HTTPException(status_code=403, detail="권한이 없습니다.")

        if order["status"] not in _OPEN_STATUSES:
            return JSONResponse({"ok": False, "error": "이미 완료되거나 취소된 주문입니다."}, status_code=400)

        ok, err = bot_client.cancel_order(
            user_id=order["user_id"],
            exchange=order["exchange"],
            uuid=order["uuid"],
            ticker=order["ticker"],
        )
        if ok:
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "error": err}, status_code=502)
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
