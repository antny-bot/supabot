import asyncio
import time
from collections import defaultdict
from datetime import datetime, timedelta

import httpx

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import bot_client
from ..db import get_db
from ._auth import _require_login, get_session_user

router = APIRouter()

_PERIODS = {"1d": 86400, "7d": 604800, "30d": 2592000, "all": None}
_EPSILON = 1e-12


def _parse_date_range(date_from: str | None, date_to: str | None) -> tuple[float | None, float | None]:
    ts_from = ts_to = None
    if date_from:
        ts_from = datetime.strptime(date_from, "%Y-%m-%d").timestamp()
    if date_to:
        ts_to = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).timestamp()
    return ts_from, ts_to


def _resolve_window(period: str, date_from: str | None, date_to: str | None):
    """Return (window_start, window_end) as Unix timestamps or None."""
    if date_from or date_to:
        return _parse_date_range(date_from, date_to)
    window = _PERIODS.get(period)
    return (time.time() - window if window else None), None


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


def _build_report_state(trades, window_start=None, window_end=None):
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
        if window_end is not None and executed_at >= window_end:
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


def _fetch_kr_stock_prices_sync(codes: set[str]) -> dict[str, float]:
    """KRX 국내 종목 최근 종가를 FinanceDataReader로 조회 (KIS/Toss 국내주식 공용).

    실시간 시세가 아니라 최근 일봉 종가이며, 공개 현재가 API가 없는 KIS/Toss
    국내주식 보유분에 대한 근사 평가용이다. 실패한 종목은 조용히 건너뛴다(0 표시 유지).
    """
    import FinanceDataReader as fdr

    out: dict[str, float] = {}
    start = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
    for code in codes:
        try:
            df = fdr.DataReader(code, start=start)
            if df is not None and not df.empty:
                out[code] = float(df["Close"].iloc[-1])
        except Exception:
            continue
    return out


async def _fetch_current_prices(position_rows, bot_user_id):
    if not position_rows:
        return {}

    # exchange별 ticker set 및 (user_id, exchange, ticker) 목록 구성
    upbit_tickers: set[str] = set()
    bithumb_tickers: set[str] = set()
    kr_stock_codes: set[str] = set()
    stock_requests: list[dict] = []
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
        elif exchange in ("kis", "toss"):
            # KIS/Toss는 매니저 프로세스에 거래소 자격증명이 없어 직접 조회할 수 없으므로
            # 봇 프로세스의 /internal/get_prices webhook을 통해 실시간 현재가를 가져온다.
            stock_requests.append({"user_id": user_id, "exchange": exchange, "ticker": ticker})
            if ticker.isdigit():
                kr_stock_codes.add(ticker)

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

    stock_keys_with_price: set[tuple[str, str]] = set()
    if stock_requests:
        try:
            results = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, bot_client.get_prices, stock_requests),
                timeout=15,
            )
            for item in results:
                price = _safe_float(item.get("price"))
                if price > 0:
                    key = (str(item.get("user_id")), item.get("exchange"), item.get("ticker"))
                    prices[key] = price
                    stock_keys_with_price.add((item.get("exchange"), item.get("ticker")))
        except Exception:
            pass

    # 봇 webhook으로 실시간가를 못 가져온 국내(숫자코드) 종목·거래소 조합만 일봉 종가로 보완
    missing_exchanges_by_code: dict[str, set[str]] = defaultdict(set)
    for exchange in ("kis", "toss"):
        for code in kr_stock_codes:
            if keys_by_ticker[(exchange, code)] and (exchange, code) not in stock_keys_with_price:
                missing_exchanges_by_code[code].add(exchange)

    if missing_exchanges_by_code:
        try:
            kr_prices = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _fetch_kr_stock_prices_sync, set(missing_exchanges_by_code)),
                timeout=15,
            )
            for code, price in kr_prices.items():
                if price > 0:
                    for exchange in missing_exchanges_by_code.get(code, ()):
                        for key in keys_by_ticker[(exchange, code)]:
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
async def api_reports_pnl(request: Request, period: str = "30d",
                          date_from: str | None = None, date_to: str | None = None):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    if period not in _PERIODS:
        period = "30d"
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        window_start, window_end = _resolve_window(period, date_from, date_to)
        _, realized_events = _build_report_state(trades, window_start=window_start, window_end=window_end)
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
async def api_reports_strategy(request: Request, period: str = "30d",
                               date_from: str | None = None, date_to: str | None = None):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    if period not in _PERIODS:
        period = "30d"
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        window_start, window_end = _resolve_window(period, date_from, date_to)
        _, realized_events = _build_report_state(trades, window_start=window_start, window_end=window_end)
        rows = _build_strategy_rows(realized_events)
        rows.sort(key=lambda row: row["pnl"], reverse=True)
        return JSONResponse({"rows": rows})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/reports/roi-ranking")
async def api_reports_roi_ranking(request: Request, period: str = "30d",
                                  date_from: str | None = None, date_to: str | None = None):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    if period not in _PERIODS:
        period = "30d"
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        window_start, window_end = _resolve_window(period, date_from, date_to)
        _, realized_events = _build_report_state(trades, window_start=window_start, window_end=window_end)
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
async def api_reports_pairs(request: Request, period: str = "30d",
                            date_from: str | None = None, date_to: str | None = None):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    if period not in _PERIODS:
        period = "30d"
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        window_start, window_end = _resolve_window(period, date_from, date_to)
        _, realized_events = _build_report_state(trades, window_start=window_start, window_end=window_end)
        return JSONResponse({"pairs": _build_pair_rows(realized_events)})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/nl-logs")
async def api_nl_logs(request: Request, period: str = "7d", limit: int = 200):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    session_user = get_session_user(request)
    if not session_user["is_admin"]:
        return JSONResponse({"error": "Admin only"}, status_code=403)
    if period not in _PERIODS:
        period = "7d"
    limit = max(1, min(limit, 500))
    try:
        db = get_db()
        q = db.table("nl_logs").select("id,user_id,raw_text,llm_action,final_action,confirm_status,logged_at")
        q = q.order("logged_at", desc=True).limit(limit)
        window_start, _ = _resolve_window(period, None, None)
        if window_start:
            q._params["logged_at"] = f"gte.{window_start}"
        rows = (await q.execute()).data or []

        final_counts: dict[str, int] = {}
        llm_counts: dict[str, int] = {}
        for r in rows:
            fa = r.get("final_action") or "unmatched"
            la = r.get("llm_action") or "unmatched"
            final_counts[fa] = final_counts.get(fa, 0) + 1
            llm_counts[la] = llm_counts.get(la, 0) + 1

        formatted = [
            {
                "id": r.get("id"),
                "user_id": r.get("user_id") or "",
                "raw_text": r.get("raw_text") or "",
                "llm_action": r.get("llm_action") or "",
                "final_action": r.get("final_action") or "",
                "confirm_status": r.get("confirm_status") or "",
                "logged_at_fmt": _fmt_ts(r.get("logged_at")),
            }
            for r in rows
        ]
        return JSONResponse({
            "rows": formatted,
            "stats": {
                "total": len(rows),
                "final_actions": sorted(final_counts.items(), key=lambda x: -x[1]),
                "llm_actions": sorted(llm_counts.items(), key=lambda x: -x[1]),
            },
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/reports/win-stats")
async def api_reports_win_stats(request: Request, period: str = "30d",
                                date_from: str | None = None, date_to: str | None = None):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    if period not in _PERIODS:
        period = "30d"
    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        window_start, window_end = _resolve_window(period, date_from, date_to)
        _, realized_events = _build_report_state(trades, window_start=window_start, window_end=window_end)
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


@router.get("/api/reports/nl-logs")
async def api_reports_nl_logs(request: Request, limit: int = 100, offset: int = 0):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    session_user = get_session_user(request)
    if not session_user.get("is_admin"):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    try:
        db = get_db()
        q = (
            db.table("nl_logs")
            .select("*")
            .order("logged_at", desc=True)
            .limit(limit)
        )
        if offset:
            q._params["offset"] = offset
        rows = (await q.execute()).data or []
        result = []
        for row in rows:
            ts = row.get("logged_at")
            try:
                fmt = datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M") if ts else "??"
            except Exception:
                fmt = "??"
            result.append({
                "id": row.get("id"),
                "user_id": row.get("user_id"),
                "raw_text": row.get("raw_text", ""),
                "preprocessed": row.get("preprocessed"),
                "llm_action": row.get("llm_action"),
                "final_action": row.get("final_action"),
                "confirm_status": row.get("confirm_status"),
                "logged_at": ts,
                "logged_at_fmt": fmt,
            })
        total_res = await db.table("nl_logs").select("id", count="exact").execute()
        total = total_res.count if hasattr(total_res, "count") and total_res.count is not None else len(result)
        return JSONResponse({"rows": result, "total": total})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
