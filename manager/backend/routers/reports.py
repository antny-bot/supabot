import asyncio
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta

import httpx

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import bot_client
from ..db import get_db, get_stock_name_map, is_db_available
from ._auth import _require_login, get_session_user
from ..services import backtest_engine, budget_manager, progression_manager, universe_resolver

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


def _build_exchange_rows(realized_events):
    agg: dict[str, dict] = defaultdict(lambda: {
        "bid_krw": 0.0,
        "ask_krw": 0.0,
        "fee_amount": 0.0,
        "trade_count": 0,
        "win_count": 0,
    })
    for event in realized_events:
        exchange = event["exchange"] or "?"
        agg[exchange]["bid_krw"] += event["bid_krw"]
        agg[exchange]["ask_krw"] += event["ask_krw"]
        agg[exchange]["fee_amount"] += event["fee_amount"]
        agg[exchange]["trade_count"] += 1
        if event["pnl"] > 0:
            agg[exchange]["win_count"] += 1

    rows = []
    for exchange, value in agg.items():
        pnl = value["ask_krw"] - value["fee_amount"] - value["bid_krw"]
        trade_count = value["trade_count"]
        rows.append({
            "exchange": exchange,
            "bid_krw": _round_money(value["bid_krw"]),
            "ask_krw": _round_money(value["ask_krw"]),
            "fee_amount": _round_money(value["fee_amount"]),
            "pnl": _round_money(pnl),
            "roi_pct": round(pnl / value["bid_krw"] * 100, 2) if value["bid_krw"] > _EPSILON else 0.0,
            "trade_count": trade_count,
            "win_rate": round(value["win_count"] / trade_count * 100, 1) if trade_count else 0.0,
        })
    return rows


def _build_daily_rows(realized_events):
    agg: dict[str, dict] = defaultdict(lambda: {"bid_krw": 0.0, "ask_krw": 0.0, "fee_amount": 0.0})
    for event in realized_events:
        day = datetime.fromtimestamp(event["executed_at"]).strftime("%Y-%m-%d")
        agg[day]["bid_krw"] += event["bid_krw"]
        agg[day]["ask_krw"] += event["ask_krw"]
        agg[day]["fee_amount"] += event["fee_amount"]

    rows = []
    cumulative = 0.0
    for day in sorted(agg.keys()):
        value = agg[day]
        pnl = value["ask_krw"] - value["fee_amount"] - value["bid_krw"]
        cumulative += pnl
        rows.append({
            "date": day,
            "bid_krw": _round_money(value["bid_krw"]),
            "ask_krw": _round_money(value["ask_krw"]),
            "fee_amount": _round_money(value["fee_amount"]),
            "pnl": _round_money(pnl),
            "cumulative_pnl": _round_money(cumulative),
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
        stock_map = await get_stock_name_map()
        for row in rows:
            ticker = row.get("ticker", "")
            row["ticker"] = stock_map.get(ticker, ticker)
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


@router.get("/api/reports/exchange")
async def api_reports_exchange(request: Request, period: str = "30d",
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
        rows = _build_exchange_rows(realized_events)
        rows.sort(key=lambda row: row["pnl"], reverse=True)
        return JSONResponse({"rows": rows})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/reports/daily")
async def api_reports_daily(request: Request, period: str = "30d",
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
        return JSONResponse({"rows": _build_daily_rows(realized_events)})
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
        stock_map = await get_stock_name_map()
        for index, row in enumerate(rows):
            row["rank"] = index + 1
            ticker = row.get("ticker", "")
            row["ticker"] = stock_map.get(ticker, ticker)
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
        stock_map = await get_stock_name_map()
        for row in rows:
            ticker = row.get("ticker", "")
            row["ticker"] = stock_map.get(ticker, ticker)
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
        pairs = _build_pair_rows(realized_events)
        stock_map = await get_stock_name_map()
        for p in pairs:
            ticker = p.get("ticker", "")
            p["ticker"] = stock_map.get(ticker, ticker)
        return JSONResponse({"pairs": pairs})
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


def _read_local_nl_logs(limit: int = 200) -> list[dict]:
    """Supabase DB가 비어있거나 연결 불가 시 data/nl_unmatched.jsonl에서 최근 로그를 폴백으로 읽어온다."""
    path = os.getenv("NL_UNMATCHED_LOG_PATH", "data/nl_unmatched.jsonl")
    if not os.path.exists(path):
        return []
    try:
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    rows.append(item)
                except Exception:
                    continue
        rows.reverse()
        return rows[:limit]
    except Exception:
        return []


def _parse_tool_chain(llm_action: str | None) -> list[str]:
    if not llm_action:
        return []
    cleaned = llm_action.replace("->", ",").replace("→", ",")
    tools = [t.strip() for t in cleaned.split(",") if t.strip()]
    return tools


@router.get("/api/reports/nl-logs")
async def api_reports_nl_logs(request: Request, limit: int = 100, offset: int = 0):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    session_user = get_session_user(request)
    if not session_user.get("is_admin"):
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    try:
        rows = []
        total = 0

        if is_db_available():
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
                res = await q.execute()
                rows = res.data or []
                total_res = await db.table("nl_logs").select("id", count="exact").execute()
                total = total_res.count if hasattr(total_res, "count") and total_res.count is not None else len(rows)
            except Exception:
                rows = []

        if not rows:
            local_all = _read_local_nl_logs(limit=max(limit * 2, 200))
            total = len(local_all)
            rows = local_all[offset:offset + limit]

        result = []
        tool_counts: dict[str, int] = {}
        final_counts: dict[str, int] = {}
        tool_call_queries = 0
        multi_turn_queries = 0
        confirmed_cnt = 0
        rejected_cnt = 0
        pending_cnt = 0

        for row in rows:
            ts = row.get("logged_at") or row.get("ts")
            raw_text = row.get("raw_text") or row.get("text_norm") or ""
            llm_action = row.get("llm_action") or ""
            final_action = row.get("final_action") or ""
            confirm_status = row.get("confirm_status") or ""

            fmt = "??"
            if ts:
                try:
                    if isinstance(ts, (int, float)):
                        fmt = datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
                    elif isinstance(ts, str) and "T" in ts:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        fmt = dt.strftime("%m-%d %H:%M")
                    else:
                        fmt = str(ts)[:16]
                except Exception:
                    fmt = str(ts)[:16]

            tools = _parse_tool_chain(llm_action)
            tool_count = len(tools)
            is_multi = tool_count > 1

            if tool_count > 0 and llm_action not in ("chat", "unmatched"):
                tool_call_queries += 1
                for t in tools:
                    tool_counts[t] = tool_counts.get(t, 0) + 1
            if is_multi:
                multi_turn_queries += 1

            if final_action:
                final_counts[final_action] = final_counts.get(final_action, 0) + 1

            if confirm_status == "confirmed":
                confirmed_cnt += 1
            elif confirm_status == "rejected":
                rejected_cnt += 1
            elif confirm_status == "pending":
                pending_cnt += 1

            result.append({
                "id": row.get("id"),
                "user_id": row.get("user_id"),
                "raw_text": raw_text,
                "preprocessed": row.get("preprocessed"),
                "llm_action": llm_action,
                "final_action": final_action,
                "confirm_status": confirm_status,
                "tool_chain": tools,
                "tool_count": tool_count,
                "is_multi_turn": is_multi,
                "tool_trace": row.get("tool_trace") or [],
                "proposed_actions": row.get("proposed_actions") or [],
                "logged_at": ts,
                "logged_at_fmt": fmt,
            })

        total_valid = len(rows)
        tool_call_rate = round((tool_call_queries / total_valid * 100), 1) if total_valid > 0 else 0.0
        decided_actions = confirmed_cnt + rejected_cnt
        approval_rate = round((confirmed_cnt / decided_actions * 100), 1) if decided_actions > 0 else 0.0

        top_tools = [
            {"tool": k, "count": v}
            for k, v in sorted(tool_counts.items(), key=lambda x: -x[1])[:5]
        ]
        action_breakdown = [
            {"action": k, "count": v}
            for k, v in sorted(final_counts.items(), key=lambda x: -x[1])
        ]

        stats = {
            "total_queries": total,
            "tool_call_count": tool_call_queries,
            "tool_call_rate": tool_call_rate,
            "multi_turn_count": multi_turn_queries,
            "confirmed_count": confirmed_cnt,
            "rejected_count": rejected_cnt,
            "pending_count": pending_cnt,
            "approval_rate": approval_rate,
            "top_tools": top_tools,
            "final_actions": action_breakdown,
        }

        return JSONResponse({"rows": result, "total": total, "stats": stats})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


def _build_drawdown_stats(realized_events):
    sorted_events = sorted(realized_events, key=lambda e: e.get("executed_at", 0))

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    max_drawdown_pct = 0.0

    time_series = []
    wins = []
    losses = []

    for event in sorted_events:
        pnl = event["pnl"]
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative

        dd = peak - cumulative
        dd_pct = round(dd / peak * 100, 2) if peak > 0 else 0.0

        if dd > max_drawdown:
            max_drawdown = dd
        if dd_pct > max_drawdown_pct:
            max_drawdown_pct = dd_pct

        day_str = datetime.fromtimestamp(event["executed_at"]).strftime("%Y-%m-%d %H:%M")
        time_series.append({
            "timestamp": event["executed_at"],
            "date": day_str,
            "cumulative_pnl": _round_money(cumulative),
            "peak": _round_money(peak),
            "drawdown": _round_money(dd),
            "drawdown_pct": dd_pct,
        })

        if pnl > 0:
            wins.append(pnl)
        else:
            losses.append(pnl)

    total_win_amount = sum(wins)
    total_loss_amount = abs(sum(losses))
    profit_factor = round(total_win_amount / total_loss_amount, 2) if total_loss_amount > 0 else (99.0 if total_win_amount > 0 else 0.0)
    current_dd = round(peak - cumulative) if peak > cumulative else 0
    current_dd_pct = round(current_dd / peak * 100, 2) if peak > 0 else 0.0

    return {
        "series": time_series,
        "metrics": {
            "mdd": _round_money(max_drawdown),
            "mdd_pct": max_drawdown_pct,
            "current_drawdown": current_dd,
            "current_drawdown_pct": current_dd_pct,
            "peak_pnl": _round_money(peak),
            "cumulative_pnl": _round_money(cumulative),
            "profit_factor": profit_factor,
            "max_win": _round_money(max(wins)) if wins else 0,
            "max_loss": _round_money(min(losses)) if losses else 0,
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(len(wins) / (len(wins) + len(losses)) * 100, 1) if (wins or losses) else 0.0,
        },
    }


@router.get("/api/reports/drawdown")
async def api_reports_drawdown(
    request: Request,
    period: str = "30d",
    date_from: str | None = None,
    date_to: str | None = None,
):
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
        res = _build_drawdown_stats(realized_events)
        return JSONResponse(res)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/reports/allocation")
async def api_reports_allocation(request: Request):
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
        rows, _ = _build_holdings_rows(positions, current_prices)
        total_value = sum(r["value_krw"] for r in rows)

        by_exchange = defaultdict(float)
        by_category = {
            "crypto": 0.0,
            "kr_stock": 0.0,
            "us_stock": 0.0,
        }

        for r in rows:
            val = r["value_krw"]
            exch = (r["exchange"] or "").lower()
            ticker = str(r.get("ticker", "")).strip()
            by_exchange[exch] += val
            if exch in ("upbit", "bithumb"):
                by_category["crypto"] += val
            elif exch == "kis":
                by_category["kr_stock"] += val
            elif exch == "toss":
                clean_tk = ticker.replace("KRW-", "").strip()
                # 토스증권: 미국 티커(AAPL, TSLA 등 영문)는 해외주식, KRX 숫자/비상장/한글 종목명은 국내주식
                is_us = clean_tk.isascii() and clean_tk.isalpha()
                if is_us:
                    by_category["us_stock"] += val
                else:
                    by_category["kr_stock"] += val
            else:
                by_category["crypto"] += val

        exchange_list = []
        for exch, val in by_exchange.items():
            pct = round(val / total_value * 100, 1) if total_value else 0.0
            exchange_list.append({"name": exch.upper(), "value": round(val), "pct": pct})

        cat_names = {
            "crypto": "가상자산",
            "kr_stock": "국내주식",
            "us_stock": "해외주식",
        }
        category_list = []
        for cat_key, cat_val in by_category.items():
            pct = round(cat_val / total_value * 100, 1) if total_value else 0.0
            category_list.append({
                "name": cat_names.get(cat_key, cat_key),
                "key": cat_key,
                "value": round(cat_val),
                "pct": pct,
            })

        return JSONResponse({
            "total_value": round(total_value),
            "by_exchange": exchange_list,
            "by_category": category_list,
            "asset_count": len(rows),
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)



def _build_batches_and_timeline(trades, stock_map, window_start=None, window_end=None, filter_group_no=None, filter_ticker=None):
    """체결 로그에서 배치(#N)별 요약과 시계열(Time-Series) 체결 이벤트를 생성한다."""
    pos_by_key: dict[tuple[str, str, int | None], dict] = defaultdict(lambda: {
        "holding_vol": 0.0,
        "avg_buy_price": 0.0,
        "cum_realized_pnl": 0.0,
    })
    batch_agg: dict[int, dict] = {}
    all_tickers: set[str] = set()
    timeline: list[dict] = []

    for trade in _iter_trades_asc(trades):
        ex = str(trade.get("exchange") or "")
        raw_tk = str(trade.get("ticker") or "")
        disp_tk = stock_map.get(raw_tk, raw_tk)
        side = str(trade.get("side") or "bid")
        price = _safe_float(trade.get("price"))
        vol = _safe_float(trade.get("volume"))
        fee = _safe_float(trade.get("fee_amount"))
        executed_at = _safe_float(trade.get("executed_at"))
        strategy = str(trade.get("strategy") or "manual")
        raw_gno = trade.get("group_no")
        gno = int(raw_gno) if raw_gno is not None and str(raw_gno).lstrip("-").isdigit() else None

        if price <= 0 or volume_is_zero(vol):
            continue

        if raw_tk:
            all_tickers.add(raw_tk)

        # 배치별 집계 (전체 이력 기준으로 평단/보유 계산 후 기간 필터 적용)
        pos_key = (ex, raw_tk, gno if filter_group_no is not None else None)
        pos = pos_by_key[pos_key]
        amt = price * vol
        trade_pnl = None

        if side == "bid":
            prev_cost = pos["holding_vol"] * pos["avg_buy_price"]
            new_vol = pos["holding_vol"] + vol
            pos["avg_buy_price"] = (prev_cost + amt + fee) / new_vol if new_vol > _EPSILON else price
            pos["holding_vol"] = new_vol
        elif side == "ask":
            avg_c = pos["avg_buy_price"]
            trade_pnl = (price - avg_c) * vol - fee if avg_c > _EPSILON else 0.0
            pos["cum_realized_pnl"] += trade_pnl
            pos["holding_vol"] = max(0.0, pos["holding_vol"] - vol)
            if pos["holding_vol"] <= _EPSILON:
                pos["holding_vol"] = 0.0

        if gno is not None:
            b = batch_agg.setdefault(gno, {
                "group_no": gno,
                "exchange": ex,
                "ticker": disp_tk,
                "raw_ticker": raw_tk,
                "strategy": strategy,
                "bid_count": 0,
                "ask_count": 0,
                "bid_krw": 0.0,
                "ask_krw": 0.0,
                "realized_pnl": 0.0,
                "holding_vol": 0.0,
                "avg_buy_price": 0.0,
                "first_ts": executed_at,
                "last_ts": executed_at,
            })
            if side == "bid":
                b["bid_count"] += 1
                b["bid_krw"] += amt
            else:
                b["ask_count"] += 1
                b["ask_krw"] += amt
                b["realized_pnl"] += (trade_pnl or 0.0)
            b["holding_vol"] = pos["holding_vol"]
            b["avg_buy_price"] = pos["avg_buy_price"]
            if executed_at < b["first_ts"] or b["first_ts"] == 0:
                b["first_ts"] = executed_at
            if executed_at > b["last_ts"]:
                b["last_ts"] = executed_at

        # 기간 및 배치/종목 필터링
        if window_start is not None and executed_at < window_start:
            continue
        if window_end is not None and executed_at >= window_end:
            continue
        if filter_group_no is not None and gno != filter_group_no:
            continue
        if filter_ticker:
            ft = filter_ticker.upper()
            tk_u = raw_tk.upper()
            tk_base = tk_u.split("-", 1)[1] if "-" in tk_u else tk_u
            disp_u = disp_tk.upper()
            if ft not in (tk_u, tk_base, disp_u) and ft not in disp_u:
                continue

        timeline.append({
            "seq": len(timeline) + 1,
            "executed_at": executed_at,
            "date_fmt": datetime.fromtimestamp(executed_at).strftime("%Y-%m-%d %H:%M") if executed_at else "-",
            "exchange": ex,
            "ticker": disp_tk,
            "raw_ticker": raw_tk,
            "side": side,
            "price": round(price, 4),
            "volume": round(vol, 8),
            "amount": _round_money(amt),
            "strategy": strategy,
            "group_no": gno,
            "holding_vol": round(pos["holding_vol"], 8),
            "avg_buy_price": round(pos["avg_buy_price"], 4),
            "trade_pnl": _round_money(trade_pnl) if trade_pnl is not None else None,
            "cum_realized_pnl": _round_money(pos["cum_realized_pnl"]),
        })

    batches = []
    for gno, b in sorted(batch_agg.items(), key=lambda x: x[0], reverse=True):
        batches.append({
            "group_no": gno,
            "exchange": b["exchange"],
            "ticker": b["ticker"],
            "raw_ticker": b["raw_ticker"],
            "strategy": b["strategy"],
            "bid_count": b["bid_count"],
            "ask_count": b["ask_count"],
            "bid_krw": _round_money(b["bid_krw"]),
            "ask_krw": _round_money(b["ask_krw"]),
            "realized_pnl": _round_money(b["realized_pnl"]),
            "holding_vol": round(b["holding_vol"], 8),
            "avg_buy_price": round(b["avg_buy_price"], 4),
            "first_at_fmt": _fmt_ts(b["first_ts"]),
            "last_at_fmt": _fmt_ts(b["last_ts"]),
        })

    return batches, timeline, sorted(all_tickers)


def volume_is_zero(v: float) -> bool:
    return v <= _EPSILON


@router.get("/api/reports/batches")
async def api_reports_batches(
    request: Request,
    period: str = "30d",
    date_from: str | None = None,
    date_to: str | None = None,
    group_no: int | None = None,
    ticker: str | None = None,
    template_id: int | None = None,
):
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx
    if period not in _PERIODS:
        period = "30d"

    try:
        db = get_db()
        trades = await _fetch_trades(db, is_admin, bot_user_id, None)
        target_tpl = None
        if template_id is not None:
            try:
                tpl_res = await db.table("strategy_templates").select("*").eq("id", template_id).execute()
                if tpl_res.data:
                    target_tpl = tpl_res.data[0]
            except Exception:
                pass

            def _match_trade_for_tpl(tr: dict) -> bool:
                if tr.get("template_id") is not None:
                    return int(tr["template_id"]) == int(template_id)
                if not target_tpl:
                    return False
                t_stype = (target_tpl.get("strategy_type") or "").lower()
                if t_stype == "kospi_top_dca":
                    return False
                t_ex = (target_tpl.get("exchange") or "").lower()
                t_tk = (target_tpl.get("ticker") or "").upper()
                tr_ex = (tr.get("exchange") or "").lower()
                tr_tk = (tr.get("ticker") or "").upper()
                tr_st = (tr.get("strategy") or "").lower()
                if t_stype in ("rsitrade", "rsi"):
                    allowed = ("rsitrade", "rsitrade_sell", "rsi", "sgridrsi")
                elif t_stype in ("dca", "sdca"):
                    allowed = ("dca", "sdca")
                else:
                    allowed = (t_stype,)
                return tr_ex == t_ex and tr_tk == t_tk and tr_st in allowed

            trades = [tr for tr in trades if _match_trade_for_tpl(tr)]

        window_start, window_end = _resolve_window(period, date_from, date_to)
        stock_map = await get_stock_name_map()

        batches, timeline, tickers = _build_batches_and_timeline(
            trades,
            stock_map,
            window_start=window_start,
            window_end=window_end,
            filter_group_no=group_no,
            filter_ticker=ticker,
        )

        # 최근 예수금 점검 알림(cash_monitor) 및 활성 DCA 스케줄 조회
        cash_alerts = []
        try:
            ev_q = (
                db.table("operational_events")
                .select("level,source,message,details,created_at")
                .order("id", desc=True)
                .limit(20)
            )
            ev_q._params["source"] = "eq.cash_monitor"
            ev_rows = (await ev_q.execute()).data or []
            for r in ev_rows[:5]:
                cash_alerts.append({
                    "level": r.get("level", "warning"),
                    "message": r.get("message", ""),
                    "details": r.get("details", ""),
                    "created_at": r.get("created_at", ""),
                })
        except Exception:
            pass

        dca_schedules = []
        try:
            dca_q = db.table("dca_schedules").select("*").order("created_at", desc=True).limit(100)
            if not is_admin and bot_user_id:
                dca_q._params["user_id"] = f"eq.{bot_user_id}"
            dca_rows = (await dca_q.execute()).data or []
            for s in dca_rows:
                if s.get("status") == "active":
                    if target_tpl is not None:
                        t_stype = (target_tpl.get("strategy_type") or "").lower()
                        if t_stype not in ("dca", "sdca"):
                            continue
                        if (s.get("exchange") or "").lower() != (target_tpl.get("exchange") or "").lower():
                            continue
                        if (s.get("ticker") or "").upper() != (target_tpl.get("ticker") or "").upper():
                            continue
                    tk = str(s.get("ticker") or "")
                    dca_schedules.append({
                        "id": s.get("id"),
                        "group_no": s.get("group_no"),
                        "exchange": s.get("exchange"),
                        "ticker": stock_map.get(tk, tk),
                        "raw_ticker": tk,
                        "side": s.get("side", "bid"),
                        "frequency": s.get("frequency"),
                        "exec_time": s.get("exec_time"),
                        "amount_type": s.get("amount_type"),
                        "amount": s.get("amount"),
                        "run_count": s.get("run_count", 0),
                        "max_runs": s.get("max_runs"),
                        "next_run_fmt": _fmt_ts(s.get("next_run_at")),
                    })
        except Exception:
            pass

        return JSONResponse({
            "batches": batches,
            "timeline": timeline,
            "tickers": tickers,
            "dca_schedules": dca_schedules,
            "cash_alerts": cash_alerts,
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ── TOP N 회전 전략 전용 리포트 & 다중 시나리오 백테스트 비교 ─────────────────

@router.get("/api/reports/top-rotation")
async def api_reports_top_rotation(
    request: Request,
    template_id: int,
    group_no: int | None = None,
):
    """TOP N 회전/추적 전략 상세 리포트: 예산 현황, 보유/이탈 현황, 순위 히트맵, 주문/체결 목록."""
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx

    try:
        db = get_db()
        t_q = db.table("strategy_templates").select("*").eq("id", template_id)
        if not is_admin and bot_user_id:
            t_q._params["user_id"] = f"eq.{bot_user_id}"
        t_rows = (await t_q.execute()).data
        if not t_rows:
            return JSONResponse({"error": "전략 템플릿을 찾을 수 없습니다."}, status_code=404)

        template = t_rows[0]
        params = template.get("params") or {}
        stock_map = await get_stock_name_map()

        # 1. 보유 종목 및 이탈 진행 상태 구성
        holdings = await progression_manager.get_template_holdings(template["user_id"], template_id)
        exit_prog = params.get("exit_progress", {})
        
        market = params.get("market", "KOSPI")
        master_top = await universe_resolver.freeze_or_get_master_top(market, max_n=50)
        master_rank_map = {it["code"]: it["rank"] for it in master_top}
        price_map = {it["code"]: float(it["price"]) for it in master_top}

        rank_start = int(params.get("rank_start", 1))
        rank_end = int(params.get("rank_end", params.get("top_n", 10)))

        holdings_status = []
        for ticker, h in holdings.items():
            cur_rank = master_rank_map.get(ticker, 9999)
            cur_price = price_map.get(ticker, h.get("avg_price", 0.0))
            val = h["qty"] * cur_price
            pnl = val - h["total_cost"]
            pnl_pct = (pnl / h["total_cost"] * 100.0) if h["total_cost"] > 0 else 0.0

            if ticker in exit_prog:
                prog = exit_prog[ticker]
                st_badge = f"🟠 이탈 분할매도 (D-{prog.get('remaining_days', 0)})"
                st_code = "exiting"
            elif rank_start <= cur_rank <= rank_end:
                st_badge = f"🟢 TOP {cur_rank}위 유지"
                st_code = "holding_top"
            else:
                st_badge = f"🟡 유예 보유 ({cur_rank}위)"
                st_code = "buffered"

            holdings_status.append({
                "ticker": ticker,
                "name": stock_map.get(ticker, ticker),
                "rank": cur_rank if cur_rank < 9999 else "—",
                "qty": h["qty"],
                "avg_price": round(h["avg_price"]),
                "current_price": round(cur_price),
                "eval_value": round(val),
                "pnl": round(pnl),
                "pnl_pct": round(pnl_pct, 2),
                "status_badge": st_badge,
                "status_code": st_code,
            })

        holdings_status.sort(key=lambda x: (x["status_code"] != "holding_top", x["rank"] if isinstance(x["rank"], int) else 9999))

        # 2. 주문 및 체결 내역
        ord_q = db.table("orders").select("*").eq("template_id", template_id).order("created_at", desc=True)
        tr_q = db.table("trade_logs").select("*").eq("template_id", template_id).order("executed_at", desc=True)
        if group_no is not None:
            ord_q._params["group_no"] = f"eq.{group_no}"
            tr_q._params["group_no"] = f"eq.{group_no}"

        orders_data = (await ord_q.execute()).data or []
        try:
            trades_data = (await tr_q.execute()).data or []
        except Exception as e:
            # trade_logs 테이블에 group_no 컬럼이 아직 없는 환경 fallback
            logger.warning(f"Failed to fetch trade_logs with group_no filter: {e}")
            try:
                fallback_tr_q = db.table("trade_logs").select("*").eq("template_id", template_id).order("executed_at", desc=True)
                raw_trades = (await fallback_tr_q.execute()).data or []
                if group_no is not None:
                    order_uuids = {o.get("uuid") for o in orders_data if o.get("uuid")}
                    trades_data = [
                        t for t in raw_trades
                        if (t.get("group_no") == group_no) or (t.get("uuid") in order_uuids)
                    ]
                else:
                    trades_data = raw_trades
            except Exception as e2:
                logger.error(f"Fallback query for trade_logs also failed: {e2}")
                trades_data = []

        for o in orders_data:
            tk = o.get("ticker", "")
            o["name"] = stock_map.get(tk, tk)
            o["order_kind"] = "모으기 매수" if o.get("side") == "bid" else "이탈 분할매도"
            o["created_fmt"] = _fmt_ts(o.get("created_at"))

        for tr in trades_data:
            tk = tr.get("ticker", "")
            tr["name"] = stock_map.get(tk, tk)
            tr["order_kind"] = "모으기 매수" if tr.get("side") == "bid" else "이탈 분할매도"
            tr["executed_fmt"] = _fmt_ts(tr.get("executed_at"))

        # 3. 사이클 파이프라인 및 다음 영업일 매수 타겟(Next Target) 산출
        cycle_no = int(params.get("cycle_no", 1))
        current_cycle_bought = list(params.get("current_cycle_bought", []))
        carryover_budget = float(params.get("carryover_budget", 0.0))
        cycle_alloc_mode = params.get("cycle_alloc_mode", "one_share")
        cycle_target_krw = float(params.get("cycle_target_krw", 300000))

        target_items = [it for it in master_top if rank_start <= it["rank"] <= rank_end]
        target_pipeline = []
        next_target = None

        for item in target_items:
            code = item["code"]
            p = float(item["price"])
            rank = item["rank"]
            name = stock_map.get(code, item.get("name", code))

            if cycle_alloc_mode == "target_amount":
                t_qty = max(1.0, round(cycle_target_krw / max(1.0, p)))
            else:
                t_qty = 1.0
            cost = t_qty * p

            is_bought = code in current_cycle_bought
            is_next = False
            if not is_bought and next_target is None:
                is_next = True
                shortfall = max(0.0, cost - carryover_budget)
                next_target = {
                    "rank": rank,
                    "code": code,
                    "name": name,
                    "price": p,
                    "target_qty": t_qty,
                    "required_krw": cost,
                    "carryover_budget": carryover_budget,
                    "shortfall": shortfall,
                    "budget_sufficient": carryover_budget >= cost,
                    "cycle_no": cycle_no,
                }

            status = "bought" if is_bought else ("next" if is_next else "waiting")
            target_pipeline.append({
                "rank": rank,
                "code": code,
                "name": name,
                "price": p,
                "target_qty": t_qty,
                "cost": cost,
                "status": status,
            })

        if not next_target and target_items:
            first_it = target_items[0]
            f_code = first_it["code"]
            f_p = float(first_it["price"])
            f_qty = max(1.0, round(cycle_target_krw / max(1.0, f_p))) if cycle_alloc_mode == "target_amount" else 1.0
            f_cost = f_qty * f_p
            next_target = {
                "rank": first_it["rank"],
                "code": f_code,
                "name": stock_map.get(f_code, first_it.get("name", f_code)),
                "price": f_p,
                "target_qty": f_qty,
                "required_krw": f_cost,
                "carryover_budget": carryover_budget,
                "shortfall": max(0.0, f_cost - carryover_budget),
                "budget_sufficient": carryover_budget >= f_cost,
                "cycle_no": cycle_no + 1,
                "note": "1사이클 완주 후 다음 사이클 1위 종목",
            }

        # 4. 일단위 실행 흐름 (일별 스냅샷 순위, 매수 성공 여부, 익일 타겟)
        # 실제 체결(trades_data) 및 현재 진행중 주문(orders_data)과 대조하여 미체결 취소분을 걸러내고 실제 상태를 반영한다.
        executed_buy_by_group_code: dict[tuple, dict] = {}
        for tr in trades_data:
            if tr.get("side") == "bid":
                key = (tr.get("group_no"), str(tr.get("ticker") or ""))
                prev = executed_buy_by_group_code.get(key)
                vol = float(tr.get("volume") or 0)
                price = float(tr.get("price") or 0)
                if prev is None:
                    executed_buy_by_group_code[key] = {"volume": vol, "price": price, "cost": price * vol}
                else:
                    tot_vol = prev["volume"] + vol
                    tot_cost = prev["cost"] + (price * vol)
                    executed_buy_by_group_code[key] = {
                        "volume": tot_vol,
                        "price": round(tot_cost / tot_vol) if tot_vol > 0 else price,
                        "cost": tot_cost,
                    }

        open_order_by_group_code: dict[tuple, str] = {}
        cancelled_order_by_group_code: set[tuple] = set()
        for o in orders_data:
            if o.get("side") == "bid":
                key = (o.get("group_no"), str(o.get("ticker") or ""))
                st = str(o.get("status") or "")
                if st in ("wait", "reserved", "partial", "pending_reorder"):
                    open_order_by_group_code[key] = st
                elif st in ("cancel", "failed", "rejected", "market_closed", "expired"):
                    cancelled_order_by_group_code.add(key)

        history = params.get("history", [])
        latest_group_no = max((int(h.get("group_no") or 0) for h in history), default=0)
        daily_execution_flow = []
        for h_item in reversed(history):
            dt = h_item.get("date", "")
            g_no = h_item.get("group_no")
            c_no = h_item.get("cycle_no", cycle_no)
            buys = h_item.get("buy_orders") or h_item.get("buys", [])
            sells = h_item.get("sell_orders") or h_item.get("sells", [])
            snap = h_item.get("snapshot") or h_item.get("top_list", [])
            w_next = h_item.get("waiting_next")
            cob = h_item.get("new_carryover")
            if cob is None:
                cob = h_item.get("end_carryover")
            if cob is None:
                cob = h_item.get("carryover_budget", 0.0)

            formatted_buys = []
            for b in buys:
                b_code = str(b.get("code") or b.get("ticker") or "")
                key = (g_no, b_code)
                exec_info = executed_buy_by_group_code.get(key)
                open_st = open_order_by_group_code.get(key)
                if exec_info:
                    b_price = exec_info["price"]
                    b_vol = exec_info["volume"]
                    b_cost = exec_info["cost"]
                    b_status = "done"
                elif open_st:
                    b_price = b.get("price", 0)
                    b_vol = b.get("volume", b.get("qty", 1))
                    b_cost = b.get("cost", b_price * b_vol)
                    b_status = open_st
                elif key in cancelled_order_by_group_code or (g_no is not None and int(g_no) < latest_group_no and trades_data):
                    # 과거 배치인데 체결 로그에도 없고 오픈 주문에도 없으면 미체결 취소된 주문이므로 체결 목록에서 제외
                    continue
                else:
                    b_price = b.get("price", 0)
                    b_vol = b.get("volume", b.get("qty", 1))
                    b_cost = b.get("cost", b_price * b_vol)
                    b_status = b.get("status", "done")

                formatted_buys.append({
                    "code": b_code,
                    "name": stock_map.get(b_code, b.get("name", b_code)),
                    "rank": b.get("rank"),
                    "price": b_price,
                    "volume": b_vol,
                    "cost": b_cost,
                    "status": b_status,
                })

            formatted_sells = []
            for s in sells:
                s_code = s.get("code") or s.get("ticker", "")
                formatted_sells.append({
                    "code": s_code,
                    "name": stock_map.get(s_code, s.get("name", s_code)),
                    "volume": s.get("volume", s.get("qty", 1)),
                    "price": s.get("price", 0),
                    "remaining_days": s.get("remaining_days"),
                })

            snap_preview = []
            for sp in snap[:rank_end]:
                sp_code = sp.get("code", "")
                snap_preview.append({
                    "rank": sp.get("rank"),
                    "code": sp_code,
                    "name": stock_map.get(sp_code, sp.get("name", sp_code)),
                    "price": sp.get("price", 0),
                })

            daily_execution_flow.append({
                "date": dt,
                "group_no": g_no,
                "cycle_no": c_no,
                "carryover_budget": cob,
                "buys": formatted_buys,
                "sells": formatted_sells,
                "snapshot_top": snap_preview,
                "waiting_next": w_next,
            })

        return JSONResponse({
            "template": template,
            "holdings_status": holdings_status,
            "batch_budget_logs": history,
            "orders": orders_data,
            "trades": trades_data,
            "master_top": master_top[:15],
            "cycle_pipeline": {
                "cycle_no": cycle_no,
                "rank_start": rank_start,
                "rank_end": rank_end,
                "total_targets": len(target_pipeline),
                "bought_count": len(current_cycle_bought),
                "progress_pct": round(len(current_cycle_bought) / max(1, len(target_pipeline)) * 100),
                "pipeline": target_pipeline,
                "next_target": next_target,
            },
            "daily_execution_flow": daily_execution_flow,
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/reports/strategy-detail")
async def api_reports_strategy_detail(
    request: Request,
    template_id: int,
):
    """단일 종목 / 일반 전략(GRID, RSI, DCA 등) 상세 운용 현황 리포트."""
    ctx, err = _auth_guard(request)
    if err:
        return err
    is_admin, bot_user_id = ctx

    try:
        db = get_db()
        t_q = db.table("strategy_templates").select("*").eq("id", template_id)
        if not is_admin and bot_user_id:
            t_q._params["user_id"] = f"eq.{bot_user_id}"
        t_rows = (await t_q.execute()).data
        if not t_rows:
            return JSONResponse({"error": "전략 템플릿을 찾을 수 없습니다."}, status_code=404)

        template = t_rows[0]
        await budget_manager.sync_single_strategy_budget_events(template, persist=True)
        ticker = (template.get("ticker") or "").upper()
        exchange = (template.get("exchange") or "upbit").lower()
        params = template.get("params") or {}
        stock_map = await get_stock_name_map()

        # 1. 템플릿 기준 보유 포지션
        holdings = await progression_manager.get_template_holdings(template["user_id"], template_id)
        holding_item = holdings.get(ticker, {"qty": 0.0, "total_cost": 0.0, "avg_price": 0.0})
        qty = float(holding_item.get("qty", 0.0))
        total_cost = float(holding_item.get("total_cost", 0.0))
        avg_price = float(holding_item.get("avg_price", 0.0))

        # 2. 현재가 조회 및 평가 손익 계산
        current_price = avg_price
        try:
            price_res = await _fetch_current_prices([{"exchange": exchange, "ticker": ticker, "user_id": template["user_id"]}], bot_user_id)
            fetched_price = price_res.get((str(template["user_id"]), exchange, ticker))
            if fetched_price and float(fetched_price) > 0:
                current_price = float(fetched_price)
        except Exception:
            pass

        eval_value = qty * current_price
        pnl = (eval_value - total_cost) if total_cost > 0 else 0.0
        pnl_pct = (pnl / total_cost * 100.0) if total_cost > 0 else 0.0

        # 3. 최근 주문 내역
        ord_q = db.table("orders").select("*").eq("template_id", template_id).order("created_at", desc=True).limit(50)
        orders_data = list((await ord_q.execute()).data or [])

        # 4. 최근 체결 내역
        tr_q = db.table("trade_logs").select("*").eq("template_id", template_id).order("executed_at", desc=True).limit(50)
        try:
            trades_data = list((await tr_q.execute()).data or [])
        except Exception:
            trades_data = []

        # 단일 종목 전략 레거시 주문/체결(template_id is null) 폴백 병합
        t_stype = (template.get("strategy_type") or "").lower()
        if t_stype != "kospi_top_dca" and exchange and ticker:
            if t_stype in ("rsitrade", "rsi"):
                allowed_strats = ("rsitrade", "rsitrade_sell", "rsi", "sgridrsi")
            elif t_stype in ("dca", "sdca"):
                allowed_strats = ("dca", "sdca")
            else:
                allowed_strats = (t_stype,)

            if not orders_data:
                try:
                    l_ord_q = db.table("orders").select("*").eq("exchange", exchange).eq("ticker", ticker).order("created_at", desc=True).limit(50)
                    l_ord_q._params["template_id"] = "is.null"
                    if template.get("user_id"):
                        l_ord_q._params["user_id"] = f"eq.{template['user_id']}"
                    for lo in ((await l_ord_q.execute()).data or []):
                        if (lo.get("strategy") or "").lower() in allowed_strats:
                            orders_data.append(lo)
                except Exception:
                    pass

            if not trades_data:
                try:
                    l_tr_q = db.table("trade_logs").select("*").eq("exchange", exchange).eq("ticker", ticker).order("executed_at", desc=True).limit(50)
                    l_tr_q._params["template_id"] = "is.null"
                    if template.get("user_id"):
                        l_tr_q._params["user_id"] = f"eq.{template['user_id']}"
                    for ltr in ((await l_tr_q.execute()).data or []):
                        if (ltr.get("strategy") or "").lower() in allowed_strats:
                            trades_data.append(ltr)
                except Exception:
                    pass

        for o in orders_data:
            tk = o.get("ticker", "")
            o["name"] = stock_map.get(tk, tk)
            o["created_fmt"] = _fmt_ts(o.get("created_at"))

        for tr in trades_data:
            tk = tr.get("ticker", "")
            tr["name"] = stock_map.get(tk, tk)
            tr["executed_fmt"] = _fmt_ts(tr.get("executed_at"))

        return JSONResponse({
            "template": template,
            "ticker": ticker,
            "name": stock_map.get(ticker, ticker),
            "exchange": exchange,
            "holding": {
                "qty": qty,
                "avg_price": round(avg_price, 2),
                "total_cost": round(total_cost),
                "current_price": round(current_price, 2),
                "eval_value": round(eval_value),
                "pnl": round(pnl),
                "pnl_pct": round(pnl_pct, 2),
            },
            "orders": orders_data,
            "trades": trades_data,
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/api/reports/top-rotation/backtest-compare")
async def api_reports_backtest_compare(request: Request):
    """다중 시나리오 역테스트 & 수익률 비교 아레나."""
    ctx, err = _auth_guard(request)
    if err:
        return err

    try:
        body = await request.json()
        start_date = body.get("start_date")
        end_date = body.get("end_date")
        scenarios = body.get("scenarios", [])
        include_benchmark = body.get("include_benchmark", True)

        if not start_date or not end_date or not scenarios:
            return JSONResponse({"error": "start_date, end_date, scenarios 필드는 필수입니다."}, status_code=400)

        result = await backtest_engine.run_multi_scenario_backtest(
            start_date=start_date,
            end_date=end_date,
            scenarios=scenarios,
            include_benchmark=include_benchmark,
        )
        return JSONResponse({"ok": True, "data": result})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

