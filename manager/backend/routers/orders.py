import logging
import inspect
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from .. import bot_client
from ..db import get_db, get_stock_name_map
from ._auth import get_current_user

logger = logging.getLogger("manager.orders")
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
_HISTORY_STATUSES = ("done", "cancel", "error", "expired", "stoploss")


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
    strategy: str | None = None,
    template_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    group_no: int | None = None,
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user),
):
    if page < 1:
        page = 1
    if page_size > 200:
        page_size = 200

    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    if not is_admin and not bot_user_id:
        return JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)

    try:
        db = get_db()
        q = db.table("orders").select("*", count="exact").order("created_at", desc=True)
        if status == "open":
            q.in_("status", list(_OPEN_STATUSES))
        elif status == "history":
            q.in_("status", list(_HISTORY_STATUSES))
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
        if template_id is not None:
            q._params["template_id"] = f"eq.{template_id}"
        if strategy:
            q._params["strategy"] = f"eq.{strategy}"
        if not is_admin:
            q._params["user_id"] = f"eq.{bot_user_id}"

        offset = (page - 1) * page_size
        q._params["limit"] = page_size
        q._params["offset"] = offset

        res = await q.execute()
        orders = res.data
        total_count = res.count or 0

        stock_map = await get_stock_name_map()
        for o in orders:
            ticker = o.get("ticker", "")
            o["ticker"] = stock_map.get(ticker, ticker)
            o["status_label"] = _STATUS_LABELS.get(o.get("status", ""), o.get("status", ""))
            o["created_fmt"] = _fmt_ts(o.get("created_at"))
            price = float(o.get("price") or 0)
            vol = float(o.get("volume") or 0)
            filled = float(o.get("filled_volume") or 0)
            o["order_value"] = price * vol
            o["fill_pct"] = round(filled / vol * 100) if vol else 0
            if o.get("strategy") == "kospi_top_dca":
                o["order_kind"] = "모으기 매수" if o.get("side") == "bid" else "이탈 분할매도"
            else:
                o["order_kind"] = "일반"

        return JSONResponse({
            "orders": orders,
            "total": total_count,
            "page": page,
            "page_size": page_size,
        })
    except Exception as e:
        return JSONResponse({"error": "Internal error"}, status_code=500)


@router.post("/api/orders/cancel-all")
async def api_cancel_all_orders(
    user: dict = Depends(get_current_user),
):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    if not is_admin and not bot_user_id:
        raise HTTPException(status_code=403, detail="연결된 봇 계정이 없습니다.")

    try:
        db = get_db()
        q = db.table("orders").select("uuid,user_id,exchange,ticker,status")
        q.in_("status", list(_OPEN_STATUSES))
        if not is_admin:
            q._params["user_id"] = f"eq.{bot_user_id}"

        res = await q.execute()
        open_orders = res.data or []

        cancelled_count = 0
        failed_count = 0
        errors = []

        for order in open_orders:
            try:
                _res = bot_client.cancel_order(
                    user_id=order["user_id"],
                    exchange=order["exchange"],
                    uuid=order["uuid"],
                    ticker=order["ticker"],
                )
                ok, err = (await _res) if inspect.isawaitable(_res) else _res
                if ok:
                    cancelled_count += 1
                else:
                    failed_count += 1
                    errors.append(f"{order['ticker']}: {err}")
            except Exception as item_err:
                failed_count += 1
                errors.append(f"{order['ticker']}: {str(item_err)}")

        return JSONResponse({
            "ok": True,
            "total": len(open_orders),
            "cancelled_count": cancelled_count,
            "failed_count": failed_count,
            "errors": errors[:5],
        })
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": "Internal error"}, status_code=500)


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

        _res = bot_client.cancel_order(
            user_id=order["user_id"],
            exchange=order["exchange"],
            uuid=order["uuid"],
            ticker=order["ticker"],
        )
        ok, err = (await _res) if inspect.isawaitable(_res) else _res
        if ok:
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "error": err}, status_code=502)
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": "Internal error"}, status_code=500)


@router.post("/api/orders/{uuid}/sync")
async def api_sync_order(uuid: str, user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    if not is_admin and not bot_user_id:
        raise HTTPException(status_code=403, detail="연결된 봇 계정이 없습니다.")

    try:
        db = get_db()
        res = await db.table("orders").select("uuid,user_id,exchange,ticker").eq("uuid", uuid).execute()
        rows = res.data
        if not rows:
            raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
        order = rows[0]

        if not is_admin and order["user_id"] != bot_user_id:
            raise HTTPException(status_code=403, detail="권한이 없습니다.")

        _res = bot_client.sync_order(
            user_id=order["user_id"],
            exchange=order["exchange"],
            uuid=order["uuid"],
            ticker=order["ticker"],
        )
        ok, err, data = (await _res) if inspect.isawaitable(_res) else _res
        if ok:
            return JSONResponse({"ok": True, "data": data})
        return JSONResponse({"ok": False, "error": err}, status_code=502)
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": "Internal error"}, status_code=500)


@router.post("/api/orders/{uuid}/force-update")
async def api_force_update_order(
    uuid: str,
    payload: dict,
    user: dict = Depends(get_current_user),
):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    if not is_admin and not bot_user_id:
        raise HTTPException(status_code=403, detail="연결된 봇 계정이 없습니다.")

    try:
        db = get_db()
        res = await db.table("orders").select("uuid,user_id").eq("uuid", uuid).execute()
        rows = res.data
        if not rows:
            raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
        order = rows[0]

        if not is_admin and order["user_id"] != bot_user_id:
            raise HTTPException(status_code=403, detail="권한이 없습니다.")

        state = payload.get("state")
        filled_volume = float(payload.get("filled_volume", 0.0))

        if state not in ("wait", "partial", "done", "cancel", "pending_reorder", "reserved", "stoploss"):
            raise HTTPException(status_code=400, detail="유효하지 않은 주문 상태입니다.")

        _res = bot_client.force_update_order(
            uuid=uuid,
            state=state,
            filled_volume=filled_volume,
        )
        ok, err = (await _res) if inspect.isawaitable(_res) else _res
        if ok:
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "error": err}, status_code=502)
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": "Internal error"}, status_code=500)

@router.get("/api/orders/batches")
async def api_list_order_batches(
    template_id: int | None = None,
    exchange: str | None = None,
    page: int = 1,
    page_size: int = 20,
    user: dict = Depends(get_current_user),
):
    """전략 템플릿별 배치(group_no) 묶음 주문 트래킹 API."""
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    if not is_admin and not bot_user_id:
        return JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)

    try:
        db = get_db()
        q = db.table("orders").select("*").order("created_at", desc=True)
        q._params["group_no"] = "not.is.null"
        if not is_admin:
            q._params["user_id"] = f"eq.{bot_user_id}"
        if template_id is not None:
            q._params["template_id"] = f"eq.{template_id}"
        if exchange:
            q._params["exchange"] = f"eq.{exchange}"

        res = await q.execute()
        orders = res.data or []

        # 템플릿 메타 매핑
        tpl_map = {}
        try:
            tpl_res = await db.table("strategy_templates").select("id,name,strategy_type,exchange").execute()
            tpl_map = {t["id"]: t for t in (tpl_res.data or [])}
        except Exception:
            pass

        stock_map = await get_stock_name_map()

        from collections import defaultdict
        batches_dict = defaultdict(list)
        for o in orders:
            g_no = o.get("group_no")
            t_id = o.get("template_id")
            key = (t_id, g_no)
            batches_dict[key].append(o)

        batch_list = []
        for (t_id, g_no), ords in batches_dict.items():
            tpl = tpl_map.get(t_id, {})
            first_ord = ords[0]
            latest_ts = max(float(o.get("created_at") or 0) for o in ords)

            total_orders = len(ords)
            buy_count = sum(1 for o in ords if o.get("side") == "bid")
            sell_count = sum(1 for o in ords if o.get("side") == "ask")
            done_count = sum(1 for o in ords if o.get("status") == "done")
            wait_count = sum(1 for o in ords if o.get("status") == "wait")
            reserved_count = sum(1 for o in ords if o.get("status") == "reserved")
            partial_count = sum(1 for o in ords if o.get("status") == "partial")
            cancel_count = sum(1 for o in ords if o.get("status") == "cancel")

            total_val = sum(float(o.get("price") or 0) * float(o.get("volume") or 0) for o in ords)
            filled_val = sum(float(o.get("price") or 0) * float(o.get("filled_volume") or 0) for o in ords)
            fill_pct = round(done_count / total_orders * 100) if total_orders else 0

            formatted_orders = []
            for o in ords:
                ticker = o.get("ticker", "")
                p = float(o.get("price") or 0)
                v = float(o.get("volume") or 0)
                fv = float(o.get("filled_volume") or 0)
                formatted_orders.append({
                    "uuid": o.get("uuid"),
                    "ticker": stock_map.get(ticker, ticker),
                    "raw_ticker": ticker,
                    "side": o.get("side"),
                    "price": p,
                    "volume": v,
                    "filled_volume": fv,
                    "order_value": p * v,
                    "fill_pct": round(fv / v * 100) if v else 0,
                    "status": o.get("status"),
                    "status_label": _STATUS_LABELS.get(o.get("status", ""), o.get("status", "")),
                    "created_fmt": _fmt_ts(o.get("created_at")),
                })

            batch_list.append({
                "group_no": g_no,
                "template_id": t_id,
                "template_name": tpl.get("name") or (f"전략 템플릿 #{t_id}" if t_id else "전략 배치"),
                "strategy": first_ord.get("strategy") or tpl.get("strategy_type", "kospi_top_dca"),
                "exchange": first_ord.get("exchange") or tpl.get("exchange", "toss"),
                "created_at": latest_ts,
                "created_fmt": _fmt_ts(latest_ts),
                "total_orders": total_orders,
                "buy_count": buy_count,
                "sell_count": sell_count,
                "done_count": done_count,
                "wait_count": wait_count,
                "reserved_count": reserved_count,
                "partial_count": partial_count,
                "cancel_count": cancel_count,
                "total_order_value": total_val,
                "total_filled_value": filled_val,
                "fill_pct": fill_pct,
                "orders": formatted_orders,
            })

        batch_list.sort(key=lambda b: (b.get("group_no") or 0, b.get("created_at") or 0), reverse=True)

        total_batches = len(batch_list)
        safe_page_size = max(1, min(page_size, 100))
        total_pages = max(1, (total_batches + safe_page_size - 1) // safe_page_size)
        safe_page = min(max(1, page), total_pages)
        start_idx = (safe_page - 1) * safe_page_size
        end_idx = start_idx + safe_page_size
        paged_batches = batch_list[start_idx:end_idx]

        return JSONResponse({
            "batches": paged_batches,
            "total": total_batches,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": total_pages,
        })
    except Exception as e:
        logger.error(f"Failed to fetch order batches: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
