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
    "cancel_requested": "취소중",
    "reserved": "예약",
    "stoploss": "손절",
}

_OPEN_STATUSES = ("wait", "partial", "pending_reorder", "reserved")
# 목록/집계 표시용: 봇이 거래소 취소를 확정하기 전의 cancel_requested 포함 (취소/일괄취소 API는 _OPEN_STATUSES 유지)
_LISTED_OPEN_STATUSES = _OPEN_STATUSES + ("cancel_requested",)
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
            q.in_("status", list(_LISTED_OPEN_STATUSES))
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
        # 템플릿 메타 매핑
        tpl_map = {}
        try:
            tpl_res = await db.table("strategy_templates").select("id,user_id,name,strategy_type,exchange,ticker,params").execute()
            tpl_map = {t["id"]: t for t in (tpl_res.data or [])}
        except Exception:
            pass

        def _matched_strategies(stype: str) -> tuple[str, ...]:
            st = (stype or "").lower()
            if st in ("rsitrade", "rsi"):
                return ("rsitrade", "rsitrade_sell", "rsi", "sgridrsi")
            if st in ("dca", "sdca"):
                return ("dca", "sdca")
            if st == "sgrid":
                return ("sgrid",)
            if st == "grid":
                return ("grid",)
            return (st,) if st else ()

        q = db.table("orders").select("*").order("created_at", desc=True)
        q._params["group_no"] = "not.is.null"
        if not is_admin:
            q._params["user_id"] = f"eq.{bot_user_id}"
        if template_id is not None:
            q._params["template_id"] = f"eq.{template_id}"
        if exchange:
            q._params["exchange"] = f"eq.{exchange}"

        res = await q.execute()
        orders = list(res.data or [])
        seen_uuids = {o.get("uuid") for o in orders if o.get("uuid")}

        # 체결 완료 후 orders에서 제거되어 trade_logs로 이동한 배치 주문도 병합
        try:
            tq = db.table("trade_logs").select("*").order("executed_at", desc=True)
            tq._params["group_no"] = "not.is.null"
            if not is_admin:
                tq._params["user_id"] = f"eq.{bot_user_id}"
            if template_id is not None:
                tq._params["template_id"] = f"eq.{template_id}"
            if exchange:
                tq._params["exchange"] = f"eq.{exchange}"
            t_res = await tq.execute()
            for tr in (t_res.data or []):
                tr_uuid = tr.get("uuid") or f"trade_{tr.get('id')}"
                if tr_uuid in seen_uuids:
                    continue
                seen_uuids.add(tr_uuid)
                vol = float(tr.get("volume") or 0)
                orders.append({
                    "uuid": tr_uuid,
                    "user_id": tr.get("user_id"),
                    "exchange": tr.get("exchange"),
                    "ticker": tr.get("ticker"),
                    "side": tr.get("side"),
                    "price": float(tr.get("price") or 0),
                    "volume": vol,
                    "filled_volume": vol,
                    "strategy": tr.get("strategy"),
                    "status": "done",
                    "created_at": tr.get("executed_at"),
                    "group_no": tr.get("group_no"),
                    "template_id": tr.get("template_id"),
                })
        except Exception:
            pass

        # 단일 종목 전략 템플릿(grid, rsitrade, dca 등)에서 template_id 없이 생성된 레거시 배치 매칭
        if template_id is not None and template_id in tpl_map:
            target_tpl = tpl_map[template_id]
            t_stype = (target_tpl.get("strategy_type") or "").lower()
            t_ex = (target_tpl.get("exchange") or "").lower()
            t_tk = (target_tpl.get("ticker") or "").upper()
            if t_stype != "kospi_top_dca" and t_ex and t_tk:
                allowed_strats = _matched_strategies(t_stype)
                try:
                    lq = db.table("orders").select("*").order("created_at", desc=True)
                    lq._params["group_no"] = "not.is.null"
                    lq._params["template_id"] = "is.null"
                    lq._params["exchange"] = f"eq.{t_ex}"
                    lq._params["ticker"] = f"eq.{t_tk}"
                    if not is_admin:
                        lq._params["user_id"] = f"eq.{bot_user_id}"
                    elif target_tpl.get("user_id"):
                        lq._params["user_id"] = f"eq.{target_tpl['user_id']}"
                    for lo in ((await lq.execute()).data or []):
                        if (lo.get("strategy") or "").lower() in allowed_strats:
                            u = lo.get("uuid")
                            if not u or u not in seen_uuids:
                                if u:
                                    seen_uuids.add(u)
                                lo["template_id"] = template_id
                                orders.append(lo)
                except Exception:
                    pass
                try:
                    ltq = db.table("trade_logs").select("*").order("executed_at", desc=True)
                    ltq._params["group_no"] = "not.is.null"
                    ltq._params["template_id"] = "is.null"
                    ltq._params["exchange"] = f"eq.{t_ex}"
                    ltq._params["ticker"] = f"eq.{t_tk}"
                    if not is_admin:
                        ltq._params["user_id"] = f"eq.{bot_user_id}"
                    elif target_tpl.get("user_id"):
                        ltq._params["user_id"] = f"eq.{target_tpl['user_id']}"
                    for ltr in ((await ltq.execute()).data or []):
                        if (ltr.get("strategy") or "").lower() in allowed_strats:
                            tr_uuid = ltr.get("uuid") or f"trade_{ltr.get('id')}"
                            if tr_uuid not in seen_uuids:
                                seen_uuids.add(tr_uuid)
                                vol = float(ltr.get("volume") or 0)
                                orders.append({
                                    "uuid": tr_uuid,
                                    "user_id": ltr.get("user_id"),
                                    "exchange": ltr.get("exchange"),
                                    "ticker": ltr.get("ticker"),
                                    "side": ltr.get("side"),
                                    "price": float(ltr.get("price") or 0),
                                    "volume": vol,
                                    "filled_volume": vol,
                                    "strategy": ltr.get("strategy"),
                                    "status": "done",
                                    "created_at": ltr.get("executed_at"),
                                    "group_no": ltr.get("group_no"),
                                    "template_id": template_id,
                                })
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
