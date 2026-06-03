import time
from collections import defaultdict
from datetime import datetime

import httpx

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import _require_login, get_session_user

router = APIRouter()

_PERIODS = {"1d": 86400, "7d": 604800, "30d": 2592000, "all": None}
_EPSILON = 1e-12


def _fmt_ts(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return "??"


def _fmt_hold(seconds: float) -> str:
    try:
        s = int(abs(seconds))
        days, rem = divmod(s, 86400)
        hours, _ = divmod(rem, 3600)
        if days:
            return f"{days}d {hours}h"
        return f"{hours}h"
    except Exception:
        return "??"


def _safe_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _round_money(value: float) -> int:
    return round(value)


def _position_key(trade: dict) -> tuple[str, str, str]:
    return (
        str(trade.get("user_id") or ""),
        str(trade.get("exchange") or ""),
        str(trade.get("ticker") or ""),
    )


def _new_position() -> dict:
    return {
        "quantity": 0.0,
        "cost_krw": 0.0,
        "opened_at": None,
        "oversold_count": 0,
    }


async def _fetch_trades(db, is_admin, bot_user_id, window, limit=5000):
    q = db.table("trade_logs").select("*").order("executed_at", desc=True).limit(limit)
    if window:
        q._params["executed_at"] = f"gte.{time.time() - window}"
    if not is_admin:
        q._params["user_id"] = f"eq.{bot_user_id}"
    return (await q.execute()).data


def _iter_trades_asc(trades):
    return sorted(
        trades,
        key=lambda t: (
            _safe_float(t.get("executed_at")),
            str(t.get("uuid") or ""),
            str(t.get("side") or ""),
        ),
    )


def _build_report_state(trades, window_start=None):
    positions: dict[tuple[str, str], dict] = defaultdict(_new_position)
    realized_events: list[dict] = []

    for trade in _iter_trades_asc(trades):
        side = str(trade.get("side") or "")
        price = _safe_float(trade.get("price"))
        volume = _safe_float(trade.get("volume"))
        fee = _safe_float(trade.get("fee_amount"))
        executed_at = _safe_float(trade.get("executed_at"))
        if price <= 0 or volume <= 0:
            continue

        key = _position_key(trade)
        position = positions[key]

        if side == "bid":
            if position["quantity"] <= _EPSILON:
                position["opened_at"] = executed_at
            position["quantity"] += volume
            position["cost_krw"] += price * volume + fee
            continue

        if side != "ask":
            continue

        available_qty = position["quantity"]
        matched_qty = min(volume, available_qty) if available_qty > _EPSILON else 0.0
        if matched_qty <= _EPSILON:
            position["oversold_count"] += 1
            continue

        avg_cost = position["cost_krw"] / available_qty if available_qty > _EPSILON else 0.0
        realized_cost = avg_cost * matched_qty
        gross_ask = price * matched_qty
        matched_fee = fee * (matched_qty / volume)
        pnl = gross_ask - matched_fee - realized_cost
        roi_pct = round(pnl / realized_cost * 100, 2) if realized_cost > _EPSILON else 0.0
        hold_started_at = position["opened_at"] or executed_at
        hold_time_s = executed_at - hold_started_at

        position["quantity"] -= matched_qty
        position["cost_krw"] -= realized_cost
        if position["quantity"] <= _EPSILON:
            position["quantity"] = 0.0
            position["cost_krw"] = 0.0
            position["opened_at"] = None

        if volume - matched_qty > _EPSILON:
            position["oversold_count"] += 1

        if window_start is not None and executed_at < window_start:
            continue

        realized_events.append({
            "exchange": key[1],
            "ticker": key[2],
            "strategy": str(trade.get("strategy") or "manual"),
            "executed_at": executed_at,
            "month": datetime.fromtimestamp(executed_at).strftime("%Y-%m"),
            "buy_price": avg_cost,
            "sell_price": price,
            "volume": matched_qty,
            "bid_krw": realized_cost,
            "ask_krw": gross_ask,
            "fee_amount": matched_fee,
            "pnl": pnl,
            "roi_pct": roi_pct,
            "hold_time_s": hold_time_s,
            "hold_time_fmt": _fmt_hold(hold_time_s),
            "buy_at_fmt": _fmt_ts(hold_started_at),
            "sell_at_fmt": _fmt_ts(executed_at),
        })

    return positions, realized_events


def _build_pnl_rows(realized_events):
    agg: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "bid_krw": 0.0,
        "ask_krw": 0.0,
        "fee_amount": 0.0,
        "bid_count": 0,
        "ask_count": 0,
    })
    for event in realized_events:
        key = (event["exchange"], event["ticker"])
        agg[key]["bid_krw"] += event["bid_krw"]
        agg[key]["ask_krw"] += event["ask_krw"]
        agg[key]["fee_amount"] += event["fee_amount"]
        agg[key]["bid_count"] += 1
        agg[key]["ask_count"] += 1

    rows = []
    for (exchange, ticker), value in agg.items():
        bid_krw = value["bid_krw"]
        ask_krw = value["ask_krw"]
        fee_amount = value["fee_amount"]
        pnl = ask_krw - fee_amount - bid_krw
        roi_pct = round(pnl / bid_krw * 100, 2) if bid_krw > _EPSILON else 0.0
        rows.append({
            "exchange": exchange,
            "ticker": ticker,
            "bid_krw": _round_money(bid_krw),
            "ask_krw": _round_money(ask_krw),
            "fee_amount": _round_money(fee_amount),
            "pnl": _round_money(pnl),
            "roi_pct": roi_pct,
            "bid_count": value["bid_count"],
            "ask_count": value["ask_count"],
        })
    return rows


def _build_strategy_rows(realized_events):
    agg: dict[str, dict] = defaultdict(lambda: {
        "bid_krw": 0.0,
        "ask_krw": 0.0,
        "fee_amount": 0.0,
        "trade_count": 0,
        "win_count": 0,
    })
    for event in realized_events:
        strategy = event["strategy"] or "manual"
        pnl = event["pnl"]
        agg[strategy]["bid_krw"] += event["bid_krw"]
        agg[strategy]["ask_krw"] += event["ask_krw"]
        agg[strategy]["fee_amount"] += event["fee_amount"]
        agg[strategy]["trade_count"] += 1
        if pnl > 0:
            agg[strategy]["win_count"] += 1

    rows = []
    for strategy, value in agg.items():
        pnl = value["ask_krw"] - value["fee_amount"] - value["bid_krw"]
        trade_count = value["trade_count"]
        rows.append({
            "strategy": strategy,
            "bid_krw": _round_money(value["bid_krw"]),
            "ask_krw": _round_money(value["ask_krw"]),
            "fee_amount": _round_money(value["fee_amount"]),
            "pnl": _round_money(pnl),
            "roi_pct": round(pnl / value["bid_krw"] * 100, 2) if value["bid_krw"] > _EPSILON else 0.0,
            "trade_count": trade_count,
            "win_rate": round(value["win_count"] / trade_count * 100, 1) if trade_count else 0.0,
        })
    return rows


def _build_monthly_rows(realized_events):
    agg: dict[str, dict] = defaultdict(lambda: {"bid_krw": 0.0, "ask_krw": 0.0, "fee_amount": 0.0})
    for event in realized_events:
        month = event["month"]
        agg[month]["bid_krw"] += event["bid_krw"]
        agg[month]["ask_krw"] += event["ask_krw"]
        agg[month]["fee_amount"] += event["fee_amount"]

    rows = []
    for month in sorted(agg.keys()):
        value = agg[month]
        pnl = value["ask_krw"] - value["fee_amount"] - value["bid_krw"]
        rows.append({
            "month": month,
            "bid_krw": _round_money(value["bid_krw"]),
            "ask_krw": _round_money(value["ask_krw"]),
            "fee_amount": _round_money(value["fee_amount"]),
            "pnl": _round_money(pnl),
            "bar_pct": 0,
        })

    if rows:
        max_abs = max(abs(row["pnl"]) for row in rows) or 1
        for row in rows:
            row["bar_pct"] = round(abs(row["pnl"]) / max_abs * 100)

    return rows


def _build_pair_rows(realized_events):
    pairs = []
    for event in realized_events:
        pairs.append({
            "ticker": event["ticker"],
            "exchange": event["exchange"],
            "strategy": event["strategy"],
            "buy_price": round(event["buy_price"], 8),
            "sell_price": round(event["sell_price"], 8),
            "volume": round(event["volume"], 8),
            "bid_krw": _round_money(event["bid_krw"]),
            "ask_krw": _round_money(event["ask_krw"]),
            "fee_amount": _round_money(event["fee_amount"]),
            "pnl": _round_money(event["pnl"]),
            "roi_pct": event["roi_pct"],
            "hold_time_s": event["hold_time_s"],
            "hold_time_fmt": event["hold_time_fmt"],
            "buy_at_fmt": event["buy_at_fmt"],
            "sell_at_fmt": event["sell_at_fmt"],
        })
    return sorted(pairs, key=lambda pair: pair["hold_time_s"], reverse=True)


def _build_holdings_rows(positions, current_prices):
    grouped: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "quantity": 0.0,
        "cost_krw": 0.0,
        "current_price": 0.0,
        "value_krw": 0.0,
        "pnl": 0.0,
        "oversold": False,
    })
    oversold_count = 0
    for (_user_id, exchange, ticker), position in positions.items():
        quantity = position["quantity"]
        if quantity <= _EPSILON:
            oversold_count += int(position["oversold_count"] > 0)
            continue

        cost_krw = position["cost_krw"]
        current_price = _safe_float(current_prices.get((_user_id, exchange, ticker)))
        value_krw = current_price * quantity if current_price > 0 else 0.0
        pnl = value_krw - cost_krw if current_price > 0 else 0.0

        row = grouped[(exchange, ticker)]
        row["quantity"] += quantity
        row["cost_krw"] += cost_krw
        row["value_krw"] += value_krw
        row["pnl"] += pnl
        row["oversold"] = row["oversold"] or position["oversold_count"] > 0
        if current_price > 0:
            row["current_price"] = current_price
        if position["oversold_count"] > 0:
            oversold_count += 1

    rows = []
    for (exchange, ticker), value in grouped.items():
        quantity = value["quantity"]
        cost_krw = value["cost_krw"]
        current_price = value["current_price"]
        avg_price = cost_krw / quantity if quantity > _EPSILON else 0.0
        roi_pct = round(value["pnl"] / cost_krw * 100, 2) if cost_krw > _EPSILON and current_price > 0 else 0.0
        rows.append({
            "exchange": exchange,
            "ticker": ticker,
            "quantity": round(quantity, 8),
            "avg_price": round(avg_price, 8),
            "cost_krw": _round_money(cost_krw),
            "current_price": current_price,
            "value_krw": _round_money(value["value_krw"]),
            "pnl": _round_money(value["pnl"]),
            "roi_pct": roi_pct,
            "oversold": value["oversold"],
        })

    rows.sort(key=lambda row: row["value_krw"], reverse=True)
    return rows, oversold_count


async def _fetch_current_prices(position_rows, bot_user_id):
    if not position_rows:
        return {}

    # exchange별 ticker set 및 (user_id, exchange, ticker) 목록 구성
    upbit_tickers: set[str] = set()
    bithumb_tickers: set[str] = set()
    keys_by_ticker: dict[tuple[str, str], list[tuple]] = defaultdict(list)

    for row in position_rows:
        exchange = row["exchange"]
        ticker = row["ticker"]
        user_id = str(row.get("user_id") or bot_user_id or "")
        key = (user_id, exchange, ticker)
        keys_by_ticker[(exchange, ticker)].append(key)
        if exchange == "upbit":
            upbit_tickers.add(ticker)
        elif exchange == "bithumb":
            bithumb_tickers.add(ticker)
        # KIS: 공개 현재가 API 없으므로 skip

    prices: dict[tuple, float] = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if upbit_tickers:
                resp = await client.get(
                    "https://api.upbit.com/v1/ticker",
                    params={"markets": ",".join(upbit_tickers)},
                )
                if resp.status_code == 200:
                    for item in resp.json():
                        market = item.get("market", "")
                        price = _safe_float(item.get("trade_price"))
                        if price > 0:
                            for key in keys_by_ticker[("upbit", market)]:
                                prices[key] = price

            if bithumb_tickers:
                resp = await client.get(
                    "https://api.bithumb.com/v1/ticker",
                    params={"markets": ",".join(bithumb_tickers)},
                )
                if resp.status_code == 200:
                    for item in resp.json():
                        market = item.get("market", "")
                        price = _safe_float(item.get("trade_price"))
                        if price > 0:
                            for key in keys_by_ticker[("bithumb", market)]:
                                prices[key] = price
    except Exception:
        pass

    return prices


def _auth_guard(request: Request):
    if not _require_login(request):
        return None, JSONResponse({"error": "Unauthorized"}, status_code=401)
    session_user = get_session_user(request)
    is_admin = session_user["is_admin"]
    bot_user_id = session_user["bot_user_id"]
    if not is_admin and not bot_user_id:
        return None, JSONResponse({"error": "No linked trading account."}, status_code=403)
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
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        window_start = time.time() - _PERIODS[period] if _PERIODS[period] else None
        _, realized_events = _build_report_state(trades, window_start=window_start)
        rows = _build_pnl_rows(realized_events)
        rows.sort(key=lambda row: row["pnl"], reverse=True)
        total_bid = sum(row["bid_krw"] for row in rows)
        total_ask = sum(row["ask_krw"] for row in rows)
        total_fee = sum(row["fee_amount"] for row in rows)
        total_pnl = sum(row["pnl"] for row in rows)
        return JSONResponse({
            "rows": rows,
            "summary": {
                "total_bid": round(total_bid),
                "total_ask": round(total_ask),
                "total_fee": round(total_fee),
                "total_pnl": round(total_pnl),
            },
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


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
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        window_start = time.time() - _PERIODS[period] if _PERIODS[period] else None
        _, realized_events = _build_report_state(trades, window_start=window_start)
        rows = _build_strategy_rows(realized_events)
        rows.sort(key=lambda row: row["pnl"], reverse=True)
        return JSONResponse({"rows": rows})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


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
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        window_start = time.time() - _PERIODS[period] if _PERIODS[period] else None
        _, realized_events = _build_report_state(trades, window_start=window_start)
        rows = _build_pnl_rows(realized_events)
        rows.sort(key=lambda row: row["roi_pct"], reverse=True)
        for index, row in enumerate(rows):
            row["rank"] = index + 1
        return JSONResponse({"rows": rows})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/reports/monthly")
async def api_reports_monthly(request: Request):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        _, realized_events = _build_report_state(trades)
        return JSONResponse({"rows": _build_monthly_rows(realized_events)})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/reports/holdings")
async def api_reports_holdings(request: Request):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        positions, _ = _build_report_state(trades)
        current_prices = await _fetch_current_prices(
            [
                {"user_id": user_id, "exchange": exchange, "ticker": ticker}
                for user_id, exchange, ticker in positions.keys()
            ],
            bot_user_id,
        )
        rows, oversold_count = _build_holdings_rows(positions, current_prices)
        total_cost = sum(row["cost_krw"] for row in rows)
        total_value = sum(row["value_krw"] for row in rows)
        total_pnl = sum(row["pnl"] for row in rows)
        total_roi_pct = round(total_pnl / total_cost * 100, 2) if total_cost else 0.0
        return JSONResponse({
            "rows": rows,
            "summary": {
                "total_cost": round(total_cost),
                "total_value": round(total_value),
                "total_pnl": round(total_pnl),
                "total_roi_pct": total_roi_pct,
                "asset_count": len(rows),
                "oversold_count": oversold_count,
            },
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


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
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        window_start = time.time() - _PERIODS[period] if _PERIODS[period] else None
        _, realized_events = _build_report_state(trades, window_start=window_start)
        return JSONResponse({"pairs": _build_pair_rows(realized_events)})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


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
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        window_start = time.time() - _PERIODS[period] if _PERIODS[period] else None
        _, realized_events = _build_report_state(trades, window_start=window_start)
        pairs = _build_pair_rows(realized_events)

        if not pairs:
            return JSONResponse({"stats": {
                "total_pairs": 0,
                "win_count": 0,
                "loss_count": 0,
                "win_rate": 0.0,
                "avg_win_pct": 0.0,
                "avg_loss_pct": 0.0,
                "rr_ratio": 0.0,
            }})

        wins = [pair for pair in pairs if pair["pnl"] > 0]
        losses = [pair for pair in pairs if pair["pnl"] <= 0]
        avg_win_pct = round(sum(pair["roi_pct"] for pair in wins) / len(wins), 2) if wins else 0.0
        avg_loss_pct = round(sum(pair["roi_pct"] for pair in losses) / len(losses), 2) if losses else 0.0
        return JSONResponse({"stats": {
            "total_pairs": len(pairs),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(len(wins) / len(pairs) * 100, 1),
            "avg_win_pct": avg_win_pct,
            "avg_loss_pct": avg_loss_pct,
            "rr_ratio": round(avg_win_pct / abs(avg_loss_pct), 2) if avg_loss_pct else 0.0,
        }})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
