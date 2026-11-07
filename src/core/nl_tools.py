"""Gemini Function Calling(도구 사용) 도구 카탈로그.

읽기 전용 도구(Read Tools, 즉시 실행)와
변경 제안 도구(Write Proposal Tools, 실행 보류 및 확인 요청)를 분리 정의한다.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional

from core.bot_logger import get_logger
from core.formatters import exchange_display_name
from core.manager_api_client import request_manager_api
from core.parsers import (
    normalize_exchange,
    parse_config_value,
    validate_config_update,
    validate_max_order,
)
from core.trade_log import read_trades

_log = get_logger("nl_tools")


@dataclass
class NLToolContext:
    user: dict
    user_id: str
    exchange_adapter: Any = None
    order_manager: Any = None
    signal_engine: Any = None
    user_manager: Any = None
    proposed_actions: list[dict] = field(default_factory=list)
    call_trace: list[dict] = field(default_factory=list)


current_nl_context: ContextVar[Optional[NLToolContext]] = ContextVar("current_nl_context", default=None)


def _get_context() -> NLToolContext:
    ctx = current_nl_context.get()
    if ctx is None:
        raise RuntimeError("NLToolContext is not active in current context")
    return ctx


# ==============================================================================
# 1. 읽기 전용 도구 (Read Tools) - 즉시 실행되어 Gemini에 결과 반환
# ==============================================================================


async def get_ticker_price(exchange: str, ticker: str) -> dict:
    """특정 거래소에서 종목의 현재가, 전일 대비 변동률, 고가/저가 시세를 조회합니다.

    Args:
        exchange: 거래소 이름 (upbit, bithumb, kis, toss)
        ticker: 종목 심볼 또는 한글 종목명 (예: BTC, ETH, 삼성전자, 005930, AAPL)
    """
    ctx = _get_context()
    norm_ex = normalize_exchange(exchange) or exchange.lower()
    try:
        resolved_ticker = ticker
        if ctx.exchange_adapter:
            resolved = await ctx.exchange_adapter.resolve_ticker(ctx.user_id, norm_ex, ticker)
            if resolved:
                resolved_ticker = resolved
            price_info = await ctx.exchange_adapter.get_ticker(ctx.user_id, norm_ex, resolved_ticker)
            if price_info:
                return {
                    "exchange": norm_ex,
                    "ticker": resolved_ticker,
                    "price": price_info.get("price") or price_info.get("trade_price"),
                    "high": price_info.get("high_price"),
                    "low": price_info.get("low_price"),
                    "change_rate": price_info.get("change_rate") or price_info.get("signed_change_rate"),
                }
        return {"exchange": norm_ex, "ticker": resolved_ticker, "error": "시세를 조회할 수 없습니다."}
    except Exception as e:
        _log.warning("get_ticker_price failed: ex=%s, ticker=%s, err=%s", norm_ex, ticker, e)
        return {"exchange": norm_ex, "ticker": ticker, "error": str(e)}


async def get_technical_indicators(exchange: str, ticker: str, interval: str = "day") -> dict:
    """종목의 기술적 지표(RSI 14, MACD, 볼린저 밴드, 스토캐스틱 등)를 계산하여 조회합니다.

    Args:
        exchange: 거래소 이름 (upbit, bithumb, kis, toss)
        ticker: 종목 심볼 (예: BTC, 005930)
        interval: 캔들 주기 ("day", "minute1", "minute5", "minute15", "minute60" 등, 기본값 "day")
    """
    ctx = _get_context()
    norm_ex = normalize_exchange(exchange) or exchange.lower()
    try:
        if ctx.exchange_adapter and ctx.signal_engine:
            resolved_ticker = await ctx.exchange_adapter.resolve_ticker(ctx.user_id, norm_ex, ticker) or ticker
            result = await ctx.signal_engine.analyze_ticker(ctx.user_id, norm_ex, resolved_ticker, interval=interval)
            return {
                "exchange": norm_ex,
                "ticker": resolved_ticker,
                "interval": interval,
                "indicators": result or {},
            }
        return {"exchange": norm_ex, "ticker": ticker, "error": "시그널 엔진을 사용할 수 없습니다."}
    except Exception as e:
        _log.warning("get_technical_indicators failed: %s", e)
        return {"exchange": norm_ex, "ticker": ticker, "error": str(e)}


async def get_account_balances(exchange: str) -> dict:
    """사용자의 거래소 계좌 잔고(원화/달러 예수금 및 보유 코인/주식 수량, 평단가)를 조회합니다.

    Args:
        exchange: 거래소 이름 (upbit, bithumb, kis, toss)
    """
    ctx = _get_context()
    norm_ex = normalize_exchange(exchange) or exchange.lower()
    try:
        if ctx.exchange_adapter:
            balances = await ctx.exchange_adapter.get_balances(ctx.user_id, norm_ex)
            # 깔끔하게 요약 정리
            cash_krw = 0.0
            cash_usd = 0.0
            holdings = []
            for b in balances or []:
                cur = b.get("currency", "")
                bal = float(b.get("balance", 0.0) or 0.0)
                locked = float(b.get("locked", 0.0) or 0.0)
                total = bal + locked
                avg_price = float(b.get("avg_buy_price", 0.0) or 0.0)

                if cur.upper() == "KRW":
                    cash_krw = total
                elif cur.upper() == "USD":
                    cash_usd = total
                elif total > 0:
                    holdings.append({
                        "ticker": cur,
                        "balance": bal,
                        "locked": locked,
                        "total": total,
                        "avg_buy_price": avg_price,
                    })

            return {
                "exchange": norm_ex,
                "cash_krw": cash_krw,
                "cash_usd": cash_usd,
                "holdings": holdings,
            }
        return {"exchange": norm_ex, "error": "거래소 어댑터가 설정되지 않았습니다."}
    except Exception as e:
        _log.warning("get_account_balances failed: %s", e)
        return {"exchange": norm_ex, "error": str(e)}


async def get_open_orders(exchange: Optional[str] = None, ticker: Optional[str] = None) -> dict:
    """현재 미체결, 대기 중이거나 예약된 주문 목록(UUID, 가격, 수량, 상태 등)을 조회합니다.
    사용자가 '주문 취소해줘'라고 했을 때 대상 주문의 UUID를 찾기 위해 반드시 먼저 호출해야 합니다.

    Args:
        exchange: 거래소 이름 필터 (upbit, bithumb, kis, toss 또는 null 시 전체)
        ticker: 종목 심볼 필터 (BTC, 005930 등 또는 null 시 전체)
    """
    ctx = _get_context()
    try:
        orders = []
        if ctx.order_manager:
            raw_orders = getattr(ctx.order_manager, "orders", []) or []
            norm_ex = normalize_exchange(exchange) if exchange else None
            resolved_ticker = ticker.upper() if ticker else None

            for o in raw_orders:
                if o.get("status") not in ("open", "wait", "pending"):
                    continue
                if norm_ex and o.get("exchange") != norm_ex:
                    continue
                if resolved_ticker and o.get("ticker", "").upper() != resolved_ticker:
                    continue

                orders.append({
                    "uuid": o.get("uuid"),
                    "exchange": o.get("exchange"),
                    "ticker": o.get("ticker"),
                    "side": o.get("side"),
                    "price": o.get("price"),
                    "volume": o.get("volume"),
                    "filled_volume": o.get("filled_volume", 0.0),
                    "strategy": o.get("strategy"),
                    "status": o.get("status"),
                    "created_at": o.get("created_at"),
                })
        return {"count": len(orders), "orders": orders}
    except Exception as e:
        _log.warning("get_open_orders failed: %s", e)
        return {"count": 0, "orders": [], "error": str(e)}


async def get_recent_trades(exchange: Optional[str] = None, ticker: Optional[str] = None, limit: int = 10) -> dict:
    """봇을 통해 체결 완료된 최근 거래 내역(체결가, 체결수량, 손익 등)을 조회합니다.

    Args:
        exchange: 거래소 필터
        ticker: 종목 심볼 필터
        limit: 조회할 건수 (기본값 10)
    """
    ctx = _get_context()
    norm_ex = normalize_exchange(exchange) if exchange else None
    resolved_ticker = ticker.upper() if ticker else None
    try:
        trades = read_trades() or []
        filtered = []
        for t in reversed(trades):
            if norm_ex and t.get("exchange") != norm_ex:
                continue
            if resolved_ticker and t.get("ticker", "").upper() != resolved_ticker:
                continue
            filtered.append(t)
            if len(filtered) >= limit:
                break
        return {"count": len(filtered), "trades": filtered}
    except Exception as e:
        _log.warning("get_recent_trades failed: %s", e)
        return {"count": 0, "trades": [], "error": str(e)}


async def get_strategy_templates() -> dict:
    """Manager Backend에 등록된 전략 템플릿 목록(ID, 이름, 거래소, 종목, 활성 상태, 예산 등)을 조회합니다."""
    ctx = _get_context()
    try:
        is_admin = bool(ctx.user.get("is_admin", False))
        res = await request_manager_api("GET", "/api/templates", ctx.user_id, is_admin=is_admin)
        if res.get("ok"):
            return {"templates": res.get("data", [])}
        return {"templates": [], "warning": res.get("error", "템플릿을 불러오지 못했습니다.")}
    except Exception as e:
        _log.warning("get_strategy_templates failed: %s", e)
        return {"templates": [], "error": str(e)}


async def get_budget_health(exchange: str) -> dict:
    """특정 거래소의 등록된 모든 전략 필요 예산 대비 실계좌 예수금 상태 및 부족 여부를 조회합니다.

    Args:
        exchange: 거래소 이름 (upbit, bithumb, kis, toss)
    """
    ctx = _get_context()
    norm_ex = normalize_exchange(exchange) or exchange.lower()
    try:
        is_admin = bool(ctx.user.get("is_admin", False))
        res = await request_manager_api(
            "GET",
            "/api/templates/budget-health",
            ctx.user_id,
            is_admin=is_admin,
            params={"exchange": norm_ex},
        )
        if res.get("ok"):
            return res.get("data", {})
        return {"exchange": norm_ex, "warning": res.get("error")}
    except Exception as e:
        _log.warning("get_budget_health failed: %s", e)
        return {"exchange": norm_ex, "error": str(e)}


async def get_user_settings() -> dict:
    """사용자의 현재 봇 환경설정(기본 거래소, RSI 기본값, 리스크 한도 등)을 조회합니다."""
    ctx = _get_context()
    prefs = ctx.user.get("preferences", {})
    return {
        "default_exchange": prefs.get("default_exchange", "upbit"),
        "rsi_buy_range": prefs.get("rsi_buy_range", "25-30"),
        "rsi_sell_range": prefs.get("rsi_sell_range", "65-75"),
        "rsi_interval": prefs.get("rsi_interval", "day"),
        "max_order_krw": prefs.get("max_order_krw"),
        "daily_max_loss_krw": prefs.get("daily_max_loss_krw"),
        "signal_alerts": prefs.get("signal_alerts", True),
    }


# ==============================================================================
# 2. 변경 제안 도구 (Write Proposal Tools) - 실거래 안전장치: 보류 큐에 적재 후 사용자 승인 요청
# ==============================================================================


async def propose_manual_order(
    exchange: str,
    ticker: str,
    side: str,
    price: float,
    volume: Optional[float] = None,
    amount_krw: Optional[float] = None,
) -> dict:
    """단일 지정가 매수(bid) 또는 매도(ask) 주문을 사용자에게 실행 제안합니다. 즉시 실행되지 않고 확인 버튼이 생성됩니다.

    Args:
        exchange: 거래소 (upbit, bithumb, kis, toss)
        ticker: 종목 심볼 (예: BTC, ETH, 005930)
        side: 매수('bid' 또는 'buy') 또는 매도('ask' 또는 'sell')
        price: 1주/1코인당 주문 희망 가격 (KRW 또는 USD)
        volume: 주문 수량 (수량 직접 지정 시)
        amount_krw: 총 주문 금액 (원화). volume이 없으면 price로 나누어 자동 계산됩니다.
    """
    ctx = _get_context()
    norm_ex = normalize_exchange(exchange) or exchange.lower()
    norm_side = "bid" if side.lower() in ("bid", "buy", "매수") else "ask"

    resolved_ticker = ticker
    if ctx.exchange_adapter:
        resolved = await ctx.exchange_adapter.resolve_ticker(ctx.user_id, norm_ex, ticker)
        if resolved:
            resolved_ticker = resolved

    calc_vol = volume
    if calc_vol is None and amount_krw and price > 0:
        calc_vol = amount_krw / price

    if not calc_vol or calc_vol <= 0:
        return {"status": "error", "message": "주문 수량(volume) 또는 주문 금액(amount_krw)이 올바르지 않습니다."}

    action = {
        "action_type": "manual_order",
        "exchange": norm_ex,
        "ticker": resolved_ticker,
        "side": norm_side,
        "price": float(price),
        "volume": float(calc_vol),
        "amount_krw": float(amount_krw) if amount_krw else float(price * calc_vol),
    }
    ctx.proposed_actions.append(action)

    side_label = "매수" if norm_side == "bid" else "매도"
    summary = f"[{exchange_display_name(norm_ex)}] {resolved_ticker} {side_label} {calc_vol}개 @ {price:,.0f}원 (총 {action['amount_krw']:,.0f}원)"
    return {
        "status": "staged_for_user_confirmation",
        "action": action,
        "summary": summary,
    }


async def propose_cancel_orders(exchange: str, order_uuids: list[str], reason: Optional[str] = None) -> dict:
    """대기 중인 미체결 주문들을 취소하도록 사용자에게 실행 제안합니다.

    Args:
        exchange: 거래소 (upbit, bithumb, kis, toss)
        order_uuids: 취소할 주문의 UUID 목록 (반드시 get_open_orders로 먼저 확인한 UUID)
        reason: 취소 사유
    """
    ctx = _get_context()
    norm_ex = normalize_exchange(exchange) or exchange.lower()
    if not order_uuids:
        return {"status": "error", "message": "취소할 주문 UUID가 지정되지 않았습니다."}

    action = {
        "action_type": "cancel_orders",
        "exchange": norm_ex,
        "order_uuids": order_uuids,
        "reason": reason or "사용자 요청 취소",
    }
    ctx.proposed_actions.append(action)

    summary = f"[{exchange_display_name(norm_ex)}] 미체결 주문 {len(order_uuids)}건 취소 ({', '.join(order_uuids[:3])}{'...' if len(order_uuids) > 3 else ''})"
    return {
        "status": "staged_for_user_confirmation",
        "action": action,
        "summary": summary,
    }


async def propose_rsi_strategy(
    exchange: str,
    ticker: str,
    side: str,
    buy_rsi_range: Optional[str] = None,
    sell_rsi_range: Optional[str] = None,
    count: int = 5,
    amount_krw: Optional[float] = None,
    dca_mode: bool = False,
) -> dict:
    """RSI 순환 매매 전략(rsitrade 분할 매수 또는 sgridrsi 분할 매도) 주문 실행을 사용자에게 제안합니다.

    Args:
        exchange: 거래소 (upbit, bithumb, kis, toss)
        ticker: 종목 심볼
        side: 매수('buy'/'bid') 또는 매도('sell'/'ask')
        buy_rsi_range: 매수 RSI 구간 (예: "25-30")
        sell_rsi_range: 매도 목표 RSI 구간 (예: "65-75")
        count: 분할 분할 수 (기본값 5)
        amount_krw: 총 투입 예산 (원화)
        dca_mode: 물타기 가중치 분할 매수 모드 여부
    """
    ctx = _get_context()
    norm_ex = normalize_exchange(exchange) or exchange.lower()
    norm_side = "buy" if side.lower() in ("buy", "bid", "매수") else "sell"
    strat = "rsitrade" if norm_side == "buy" else "sgridrsi"

    resolved_ticker = ticker
    if ctx.exchange_adapter:
        resolved = await ctx.exchange_adapter.resolve_ticker(ctx.user_id, norm_ex, ticker)
        if resolved:
            resolved_ticker = resolved

    action = {
        "action_type": "strategy_rsi",
        "strategy": strat,
        "exchange": norm_ex,
        "ticker": resolved_ticker,
        "side": norm_side,
        "buy_rsi_range": buy_rsi_range,
        "sell_rsi_range": sell_rsi_range,
        "count": count,
        "amount_krw": amount_krw,
        "dca_mode": dca_mode,
    }
    ctx.proposed_actions.append(action)

    strat_name = "RSI 분할 매수(rsitrade)" if norm_side == "buy" else "RSI 분할 매도(sgridrsi)"
    budget_str = f", 예산 {amount_krw:,.0f}원" if amount_krw else ""
    summary = f"[{exchange_display_name(norm_ex)}] {resolved_ticker} {strat_name} {count}분할{budget_str}"
    return {
        "status": "staged_for_user_confirmation",
        "action": action,
        "summary": summary,
    }


async def propose_grid_strategy(
    exchange: str,
    ticker: str,
    side: str,
    start_price: float,
    end_price: float,
    count: int,
    amount_krw: Optional[float] = None,
    volume: Optional[float] = None,
) -> dict:
    """가격 구간 거미줄(Grid) 분할 매수 또는 매도 전략 실행을 사용자에게 제안합니다.

    Args:
        exchange: 거래소
        ticker: 종목 심볼
        side: 매수('buy') 또는 매도('sell')
        start_price: 시작 가격
        end_price: 끝 가격
        count: 분할 주문 건수
        amount_krw: 총 투입 금액
        volume: 총 주문 수량
    """
    ctx = _get_context()
    norm_ex = normalize_exchange(exchange) or exchange.lower()
    norm_side = "buy" if side.lower() in ("buy", "bid", "매수") else "sell"

    resolved_ticker = ticker
    if ctx.exchange_adapter:
        resolved = await ctx.exchange_adapter.resolve_ticker(ctx.user_id, norm_ex, ticker)
        if resolved:
            resolved_ticker = resolved

    action = {
        "action_type": "strategy_grid",
        "exchange": norm_ex,
        "ticker": resolved_ticker,
        "side": norm_side,
        "start_price": float(start_price),
        "end_price": float(end_price),
        "count": count,
        "amount_krw": amount_krw,
        "volume": volume,
    }
    ctx.proposed_actions.append(action)

    summary = f"[{exchange_display_name(norm_ex)}] {resolved_ticker} 거미줄 {norm_side} {start_price:,.0f}~{end_price:,.0f}원 {count}분할"
    return {
        "status": "staged_for_user_confirmation",
        "action": action,
        "summary": summary,
    }


async def propose_template_action(template_id: int, action: str, amount_krw: Optional[float] = None) -> dict:
    """Manager Backend 전략 템플릿 제어(실행, 일시중지, 중지 및 미체결 취소, 예산 추가)를 사용자에게 제안합니다.

    Args:
        template_id: 전략 템플릿 ID (숫자)
        action: 실행할 작업 ('run', 'pause', 'stop_and_cancel', 'topup')
        amount_krw: topup 시 추가할 금액
    """
    ctx = _get_context()
    action_clean = action.lower()
    proposed = {
        "action_type": "template_control",
        "template_id": template_id,
        "action": action_clean,
        "amount_krw": amount_krw,
    }
    ctx.proposed_actions.append(proposed)

    action_kr = {
        "run": "즉시 실행",
        "pause": "일시중지",
        "stop_and_cancel": "중지 및 미체결 일괄 취소",
        "topup": f"예산 {amount_krw:,.0f}원 추가",
    }.get(action_clean, action_clean)
    summary = f"전략 템플릿 #{template_id} {action_kr}"
    return {
        "status": "staged_for_user_confirmation",
        "action": proposed,
        "summary": summary,
    }


async def propose_update_config(config_key: str, config_value: str) -> dict:
    """사용자의 봇 환경설정 변경을 제안합니다.

    Args:
        config_key: 설정 키 (예: default_exchange, rsi_buy_range, max_order_krw 등)
        config_value: 변경할 값 문자열
    """
    ctx = _get_context()
    parsed_val, err = parse_config_value(config_key, config_value)
    if err:
        return {"status": "error", "message": err}

    valid_err = validate_config_update(ctx.user, config_key, parsed_val)
    if valid_err:
        return {"status": "error", "message": valid_err}

    action = {
        "action_type": "update_config",
        "config_key": config_key,
        "config_value": parsed_val,
        "raw_value": config_value,
    }
    ctx.proposed_actions.append(action)

    summary = f"환경설정 변경: {config_key} = {config_value}"
    return {
        "status": "staged_for_user_confirmation",
        "action": action,
        "summary": summary,
    }


async def propose_watchlist_change(exchange: str, ticker: str, action: str) -> dict:
    """RSI 감시 관심종목 추가(watch) 또는 삭제(unwatch)를 제안합니다.

    Args:
        exchange: 거래소
        ticker: 종목 심볼
        action: 'watch'(추가) 또는 'unwatch'(삭제)
    """
    ctx = _get_context()
    norm_ex = normalize_exchange(exchange) or exchange.lower()
    act = "watch" if action.lower() in ("watch", "add", "추가") else "unwatch"

    resolved_ticker = ticker
    if ctx.exchange_adapter:
        resolved = await ctx.exchange_adapter.resolve_ticker(ctx.user_id, norm_ex, ticker)
        if resolved:
            resolved_ticker = resolved

    proposed = {
        "action_type": "watchlist_change",
        "exchange": norm_ex,
        "ticker": resolved_ticker,
        "action": act,
    }
    ctx.proposed_actions.append(proposed)

    act_str = "관심종목 등록" if act == "watch" else "관심종목 해제"
    summary = f"[{exchange_display_name(norm_ex)}] {resolved_ticker} {act_str}"
    return {
        "status": "staged_for_user_confirmation",
        "action": proposed,
        "summary": summary,
    }


ALL_NL_TOOLS = [
    # 읽기 도구 8종
    get_ticker_price,
    get_technical_indicators,
    get_account_balances,
    get_open_orders,
    get_recent_trades,
    get_strategy_templates,
    get_budget_health,
    get_user_settings,
    # 쓰기 제안 도구 7종
    propose_manual_order,
    propose_cancel_orders,
    propose_rsi_strategy,
    propose_grid_strategy,
    propose_template_action,
    propose_update_config,
    propose_watchlist_change,
]

READ_ONLY_TOOL_NAMES = {
    "get_ticker_price",
    "get_technical_indicators",
    "get_account_balances",
    "get_open_orders",
    "get_recent_trades",
    "get_strategy_templates",
    "get_budget_health",
    "get_user_settings",
}

WRITE_PROPOSAL_TOOL_NAMES = {
    "propose_manual_order",
    "propose_cancel_orders",
    "propose_rsi_strategy",
    "propose_grid_strategy",
    "propose_template_action",
    "propose_update_config",
    "propose_watchlist_change",
}
