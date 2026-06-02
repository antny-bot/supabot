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


def _fmt_hold(seconds: float) -> str:
    try:
        s = int(abs(seconds))
        days, rem = divmod(s, 86400)
        hours, _ = divmod(rem, 3600)
        if days:
            return f"{days}일 {hours}시간"
        return f"{hours}시간"
    except Exception:
        return "—"


async def _fetch_trades(db, is_admin, bot_user_id, window, limit=2000):
    q = db.table("trade_logs").select("*").order("executed_at", desc=True).limit(limit)
    if window:
        q._params["executed_at"] = f"gte.{time.time() - window}"
    if not is_admin:
        q._params["user_id"] = f"eq.{bot_user_id}"
    return (await q.execute()).data


async def _fetch_orders_for_uuids(db, is_admin, bot_user_id, uuids):
    if not uuids:
        return []
    in_val = ",".join(uuids[:500])
    q = db.table("orders").select("uuid,linked_to,side,strategy,created_at")
    q._params["uuid"] = f"in.({in_val})"
    if not is_admin:
        q._params["user_id"] = f"eq.{bot_user_id}"
    return (await q.execute()).data


def _build_pnl_rows(trades):
    """(exchange, ticker) 별 매수/매도 집계"""
    agg: dict = defaultdict(lambda: {
        "bid_krw": 0.0, "ask_krw": 0.0, "fee_amount": 0.0,
        "bid_count": 0, "ask_count": 0,
    })
    for t in trades:
        price = float(t.get("price") or 0)
        volume = float(t.get("volume") or 0)
        fee = float(t.get("fee_amount") or 0)
        krw = price * volume
        key = (t.get("exchange", ""), t.get("ticker", ""))
        if t.get("side") == "bid":
            agg[key]["bid_krw"] += krw
            agg[key]["bid_count"] += 1
        elif t.get("side") == "ask":
            agg[key]["ask_krw"] += krw
            agg[key]["ask_count"] += 1
        agg[key]["fee_amount"] += fee
    rows = []
    for (exchange, ticker), v in agg.items():
        bid_krw = v["bid_krw"]
        ask_krw = v["ask_krw"]
        fee = v["fee_amount"]
        pnl = ask_krw - bid_krw - fee
        roi_pct = round(pnl / bid_krw * 100, 2) if bid_krw else 0.0
        rows.append({
            "exchange": exchange,
            "ticker": ticker,
            "bid_krw": round(bid_krw),
            "ask_krw": round(ask_krw),
            "fee_amount": round(fee),
            "pnl": round(pnl),
            "roi_pct": roi_pct,
            "bid_count": v["bid_count"],
            "ask_count": v["ask_count"],
        })
    return rows


def _build_pairs(trades, orders_by_uuid):
    bid_by_uuid = {t["uuid"]: t for t in trades if t.get("side") == "bid" and t.get("uuid")}
    pairs = []
    for t in trades:
        if t.get("side") != "ask" or not t.get("uuid"):
            continue
        order = orders_by_uuid.get(t["uuid"])
        if not order or not order.get("linked_to"):
            continue
        bid_trade = bid_by_uuid.get(order["linked_to"])
        if not bid_trade:
            continue
        bid_krw = float(bid_trade.get("price", 0)) * float(bid_trade.get("volume", 0))
        ask_krw = float(t.get("price", 0)) * float(t.get("volume", 0))
        fee = float(bid_trade.get("fee_amount") or 0) + float(t.get("fee_amount") or 0)
        pnl = ask_krw - bid_krw - fee
        roi_pct = round(pnl / bid_krw * 100, 2) if bid_krw else 0.0
        hold_s = float(t.get("executed_at", 0)) - float(bid_trade.get("executed_at", 0))
        pairs.append({
            "ticker": t.get("ticker", ""),
            "exchange": t.get("exchange", ""),
            "strategy": order.get("strategy", "manual"),
            "buy_price": float(bid_trade.get("price", 0)),
            "sell_price": float(t.get("price", 0)),
            "volume": float(t.get("volume", 0)),
            "bid_krw": round(bid_krw),
            "ask_krw": round(ask_krw),
            "fee_amount": round(fee),
            "pnl": round(pnl),
            "roi_pct": roi_pct,
            "hold_time_s": hold_s,
            "hold_time_fmt": _fmt_hold(hold_s),
            "buy_at_fmt": _fmt_ts(bid_trade.get("executed_at")),
            "sell_at_fmt": _fmt_ts(t.get("executed_at")),
        })
    return sorted(pairs, key=lambda p: p["hold_time_s"], reverse=True)


def _auth_guard(request: Request):
    if not _require_login(request):
        return None, JSONResponse({"error": "Unauthorized"}, status_code=401)
    session_user = get_session_user(request)
    is_admin = session_user["is_admin"]
    bot_user_id = session_user["bot_user_id"]
    if not is_admin and not bot_user_id:
        return None, JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)
    return (is_admin, bot_user_id), None


@router.get("/api/reports/pnl")
async def api_reports_pnl(request: Request, period: str = "30d"):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    if period not in _PERIODS:
        period = "30d"
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, _PERIODS[period])
        rows = _build_pnl_rows(trades)
        rows.sort(key=lambda r: r["pnl"], reverse=True)
        total_bid = sum(r["bid_krw"] for r in rows)
        total_ask = sum(r["ask_krw"] for r in rows)
        total_fee = sum(r["fee_amount"] for r in rows)
        total_pnl = total_ask - total_bid - total_fee
        return JSONResponse({
            "rows": rows,
            "summary": {
                "total_bid": round(total_bid),
                "total_ask": round(total_ask),
                "total_fee": round(total_fee),
                "total_pnl": round(total_pnl),
            },
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/reports/strategy")
async def api_reports_strategy(request: Request, period: str = "30d"):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    if period not in _PERIODS:
        period = "30d"
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, _PERIODS[period])

        # P&L by strategy
        st_agg: dict = defaultdict(lambda: {
            "bid_krw": 0.0, "ask_krw": 0.0, "fee_amount": 0.0, "trade_count": 0,
        })
        # ticker wins by strategy
        ticker_pnl: dict = defaultdict(lambda: defaultdict(float))  # strategy -> ticker_key -> pnl
        for t in trades:
            price = float(t.get("price") or 0)
            volume = float(t.get("volume") or 0)
            fee = float(t.get("fee_amount") or 0)
            krw = price * volume
            st = t.get("strategy") or "manual"
            st_agg[st]["trade_count"] += 1
            st_agg[st]["fee_amount"] += fee
            if t.get("side") == "bid":
                st_agg[st]["bid_krw"] += krw
                ticker_key = f"{t.get('exchange')}:{t.get('ticker')}"
                ticker_pnl[st][ticker_key] -= krw
            elif t.get("side") == "ask":
                st_agg[st]["ask_krw"] += krw
                ticker_key = f"{t.get('exchange')}:{t.get('ticker')}"
                ticker_pnl[st][ticker_key] += krw

        rows = []
        for st, v in st_agg.items():
            bid_krw = v["bid_krw"]
            ask_krw = v["ask_krw"]
            fee = v["fee_amount"]
            pnl = ask_krw - bid_krw - fee
            roi_pct = round(pnl / bid_krw * 100, 2) if bid_krw else 0.0
            tickers = ticker_pnl.get(st, {})
            paired = [p for p in tickers.values() if p != 0]
            wins = sum(1 for p in paired if p > 0)
            win_rate = round(wins / len(paired) * 100, 1) if paired else 0.0
            rows.append({
                "strategy": st,
                "bid_krw": round(bid_krw),
                "ask_krw": round(ask_krw),
                "fee_amount": round(fee),
                "pnl": round(pnl),
                "roi_pct": roi_pct,
                "trade_count": v["trade_count"],
                "win_rate": win_rate,
            })
        rows.sort(key=lambda r: r["pnl"], reverse=True)
        return JSONResponse({"rows": rows})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/reports/roi-ranking")
async def api_reports_roi_ranking(request: Request, period: str = "30d"):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    if period not in _PERIODS:
        period = "30d"
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, _PERIODS[period])
        rows = _build_pnl_rows(trades)
        rows.sort(key=lambda r: r["roi_pct"], reverse=True)
        for i, r in enumerate(rows):
            r["rank"] = i + 1
        return JSONResponse({"rows": rows})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/reports/monthly")
async def api_reports_monthly(request: Request):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)

        month_agg: dict = defaultdict(lambda: {"bid_krw": 0.0, "ask_krw": 0.0, "fee_amount": 0.0})
        for t in trades:
            try:
                month = datetime.fromtimestamp(float(t.get("executed_at", 0))).strftime("%Y-%m")
            except (TypeError, ValueError):
                continue
            price = float(t.get("price") or 0)
            volume = float(t.get("volume") or 0)
            fee = float(t.get("fee_amount") or 0)
            krw = price * volume
            month_agg[month]["fee_amount"] += fee
            if t.get("side") == "bid":
                month_agg[month]["bid_krw"] += krw
            elif t.get("side") == "ask":
                month_agg[month]["ask_krw"] += krw

        rows = []
        for month in sorted(month_agg.keys()):
            v = month_agg[month]
            bid_krw = v["bid_krw"]
            ask_krw = v["ask_krw"]
            fee = v["fee_amount"]
            pnl = ask_krw - bid_krw - fee
            rows.append({
                "month": month,
                "bid_krw": round(bid_krw),
                "ask_krw": round(ask_krw),
                "fee_amount": round(fee),
                "pnl": round(pnl),
                "bar_pct": 0,  # filled below
            })

        if rows:
            max_abs = max(abs(r["pnl"]) for r in rows) or 1
            for r in rows:
                r["bar_pct"] = round(abs(r["pnl"]) / max_abs * 100)

        return JSONResponse({"rows": rows})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/reports/pairs")
async def api_reports_pairs(request: Request, period: str = "30d"):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    if period not in _PERIODS:
        period = "30d"
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, _PERIODS[period])
        uuids = list({t["uuid"] for t in trades if t.get("uuid")})
        orders = await _fetch_orders_for_uuids(db, is_admin, bot_user_id, uuids)
        orders_by_uuid = {o["uuid"]: o for o in orders}
        pairs = _build_pairs(trades, orders_by_uuid)
        return JSONResponse({"pairs": pairs})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/reports/win-stats")
async def api_reports_win_stats(request: Request, period: str = "30d"):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    if period not in _PERIODS:
        period = "30d"
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, _PERIODS[period])
        uuids = list({t["uuid"] for t in trades if t.get("uuid")})
        orders = await _fetch_orders_for_uuids(db, is_admin, bot_user_id, uuids)
        orders_by_uuid = {o["uuid"]: o for o in orders}
        pairs = _build_pairs(trades, orders_by_uuid)

        if not pairs:
            return JSONResponse({"stats": {
                "total_pairs": 0, "win_count": 0, "loss_count": 0,
                "win_rate": 0.0, "avg_win_pct": 0.0, "avg_loss_pct": 0.0, "rr_ratio": 0.0,
            }})

        wins = [p for p in pairs if p["pnl"] > 0]
        losses = [p for p in pairs if p["pnl"] <= 0]
        win_rate = round(len(wins) / len(pairs) * 100, 1)
        avg_win_pct = round(sum(p["roi_pct"] for p in wins) / len(wins), 2) if wins else 0.0
        avg_loss_pct = round(sum(p["roi_pct"] for p in losses) / len(losses), 2) if losses else 0.0
        rr_ratio = round(avg_win_pct / abs(avg_loss_pct), 2) if avg_loss_pct else 0.0

        return JSONResponse({"stats": {
            "total_pairs": len(pairs),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": win_rate,
            "avg_win_pct": avg_win_pct,
            "avg_loss_pct": avg_loss_pct,
            "rr_ratio": rr_ratio,
        }})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
