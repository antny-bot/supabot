"""자연어(Gemini NL) 라우팅 — 의도 파싱·도구 호출·확인·실행.

단순 조회는 룰 기반 1차 패스트트랙(`preprocess_natural_language_intent`)으로 0초대 즉시 응답하고,
복합 요청 및 매매/제어 작업은 Gemini Function Calling 멀티턴 에이전트 루프(`run_nl_agent_loop`)로 처리한다.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import main
from main import check_auth
from core.command_log import log_command
from core.operational_events import append_operational_event
from core.natural_language import (
    append_natural_language_log,
    append_preprocess_hit,
    normalize_natural_language_intent,
    preprocess_natural_language_intent,
    update_natural_language_log_outcome,
    _looks_like_rsi_split_request,
)
from core.parsers import (
    POLL_INTERVAL_KEYS, parse_config_value, validate_config_update,
    parse_exchange_and_ticker, exchange_display_name, validate_max_order,
    get_user_rsi_interval, has_gemini_key, get_dca_weights,
)
from core.formatters import build_config_view, format_config_value
from core.nl_schema import TradeIntentModel
from core.nl_agent import run_nl_agent_loop, AgentRunResult
from core.manager_api_client import request_manager_api
from core.order_execution import execute_rsitrade_orders, execute_sgridrsi_orders
from core.stock_resolver import find_kr_stock_candidates
from core.ticker_disambiguation import (
    create_nl_disambiguation_token,
    pop_valid_nl_disambiguation,
)


def _build_llm_prompt(user_text, user, recent_context=None):
    prefs = user.get("preferences", {})
    context_lines = []
    if recent_context and isinstance(recent_context, list):
        for item in recent_context:
            role = item.get("role", "user")
            if role == "user":
                context_lines.append(f"User: {item.get('text', '')}")
            elif role == "bot":
                act = item.get("action")
                tk = item.get("ticker")
                context_lines.append(f"Bot resolved: action={act}, ticker={tk}")
    context_block = ""
    if context_lines:
        context_block = "Recent conversation context:\n" + "\n".join(context_lines) + "\n(If the user text refers back to the ticker/subject from recent conversation, carry it over.)\n\n"

    return (
        "Parse Korean trading bot text. Return JSON matching the schema.\n"
        "Never execute. Use null for unknown fields.\n"
        "Use help only for usage/capability questions.\n"
        "Missing required fields => clarify.\n"
        "Orders/cancel/config/watch need user confirm.\n"
        "Pending/reserved/tracked strategy orders => status. Real open/unfilled exchange orders => orders.\n"
        "매도/팔아 + RSI + 분할 => sgridrsi (sell_rsi_range only, buy_rsi_range=null).\n"
        "매수/사줘 + RSI + 분할, or RSI + 분할 (no direction) => rsitrade (buy_rsi_range).\n"
        "grid/gridrsi is price-range; RSI range goes to gridrsi/sgridrsi not grid.\n"
        "Missing sell_rsi_range for rsitrade/gridrsi => null; server uses default.\n"
        "dca_mode=true only if user explicitly mentions DCA/물타기/가중치 분할 (rsitrade only); else null.\n"
        "Exchange: upbit|bithumb|kis|toss|null. Korean stock => kis or toss (default kis if unspecified, "
        "toss if user explicitly says 토스/tossinvest). Samsung => 005930. Crypto ticker: BTC/ETH/XRP.\n"
        f"Default exchange: {prefs.get('default_exchange', 'upbit')}.\n"
        f"{context_block}"
        f"Commands:\n{main.LLM_COMMAND_CATALOG}\n"
        f"User text: {user_text}"
    )


async def parse_natural_language_intent(text, user, recent_context=None):
    """단발성 TradeIntentModel 스키마 파서 (단위 테스트 및 하위 호환성 유지)."""
    api_key = user.get("llm", {}).get("gemini_api_key", "")
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TradeIntentModel,
            temperature=0.1,
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=user.get("preferences", {}).get("llm_model", "gemini-2.5-flash-lite"),
            contents=_build_llm_prompt(text, user, recent_context=recent_context),
            config=config,
        )
        data = json.loads(response.text)
        if isinstance(data, dict):
            return data
        return None
    except Exception as e:
        main._log.warning("Gemini intent parse error", exc_info=e, extra={"event": "gemini_parse_error"})
        return None


def _intent_args(intent, user):
    action = intent.get("action")
    exchange = intent.get("exchange") or user.get("preferences", {}).get("default_exchange", "upbit")
    ticker = intent.get("ticker")
    args = []
    if exchange:
        args.append(exchange)
    if ticker:
        args.append(str(ticker))
    if action in ["buy", "sell"]:
        if intent.get("price") is not None:
            args.append(str(intent["price"]))
        if intent.get("volume") is not None:
            args.append(str(intent["volume"]))
    elif action in ["grid"]:
        for key in ["start_price", "end_price", "count", "amount_krw"]:
            if intent.get(key) is not None:
                args.append(str(intent[key]))
    elif action in ["sgrid"]:
        for key in ["start_price", "end_price", "count", "volume"]:
            if intent.get(key) is not None:
                args.append(str(intent[key]))
    elif action in ("rsitrade", "gridrsi"):
        if intent.get("buy_rsi_range"):
            args.append(str(intent["buy_rsi_range"]))
        if intent.get("sell_rsi_range"):
            args.append(str(intent["sell_rsi_range"]))
        if intent.get("count") is not None:
            args.append(str(intent["count"]))
        if intent.get("amount_krw") is not None:
            args.append(str(intent["amount_krw"]))
    elif action == "sgridrsi":
        if intent.get("sell_rsi_range"):
            args.append(str(intent["sell_rsi_range"]))
        if intent.get("count") is not None:
            args.append(str(intent["count"]))
        if intent.get("amount_krw") is not None:
            args.append(str(intent["amount_krw"]))
    elif action == "config_set":
        args = ["set", str(intent.get("config_key") or ""), str(intent.get("config_value") or "")]
    return args


def _is_immediate_intent(action):
    return action in {"asset", "price", "orders", "status", "config_view", "history", "help", "rsi", "indicators"}


def _intent_summary(intent):
    action = intent.get("action")
    if action == "config_set":
        return f"설정 변경: {intent.get('config_key')} = {intent.get('config_value')}"
    if action in ("rsitrade", "gridrsi"):
        exchange = intent.get("exchange") or "upbit"
        _, ticker = parse_exchange_and_ticker([exchange, intent.get("ticker")] if intent.get("ticker") else [exchange], exchange)
        buy_range = intent.get("buy_rsi_range") or "기본값"
        sell_range = intent.get("sell_rsi_range") or "기본값"
        count = intent.get("count") or "기본"
        amount = intent.get("amount_krw")
        amount_text = f"{float(amount):,.0f}원" if amount is not None else "기본 예산"
        dca_text = " / DCA 가중 배분" if intent.get("dca_mode") else ""
        return (
            f"{exchange_display_name(exchange)} {ticker} / "
            f"매수 RSI {buy_range} / 매도 RSI {sell_range} / "
            f"{count}분할 / 총 {amount_text}{dca_text}"
        )
    if action == "sgridrsi":
        exchange = intent.get("exchange") or "upbit"
        _, ticker = parse_exchange_and_ticker([exchange, intent.get("ticker")] if intent.get("ticker") else [exchange], exchange)
        sell_range = intent.get("sell_rsi_range") or "기본값"
        count = intent.get("count") or "기본"
        amount = intent.get("amount_krw")
        amount_text = f"{float(amount):,.0f}원" if amount is not None else "기본 예산"
        return (
            f"{exchange_display_name(exchange)} {ticker} / "
            f"매도 RSI {sell_range} / "
            f"{count}분할 / 총 {amount_text}"
        )
    pieces = [str(action or "unknown")]
    for key in ["exchange", "ticker", "price", "volume", "amount_krw", "start_price", "end_price", "count", "buy_rsi_range", "sell_rsi_range"]:
        if intent.get(key) is not None:
            pieces.append(f"{key}={intent[key]}")
    return " / ".join(pieces)


def _clarify_message(text, intent):
    action = intent.get("action") if isinstance(intent, dict) else None
    if action in ("rsitrade", "gridrsi") or _looks_like_rsi_split_request(text):
        return "⚠️ RSI 전략은 종목, 매수 RSI, 예산을 확인할 수 있어야 합니다."
    if action == "sgridrsi":
        return "⚠️ RSI 매도 전략은 종목, 매도 RSI, 예산을 확인할 수 있어야 합니다."
    return "⚠️ 요청을 명령으로 해석하지 못했습니다. 종목, 거래소, 가격/수량을 더 구체적으로 입력해 주세요."


async def execute_query_intent(update, context, user, intent):
    from handlers import status_handlers, query_handlers, system_handlers
    action = intent.get("action")
    context.args = _intent_args(intent, user)
    if action == "asset":
        return await query_handlers.asset_command(update, context)
    if action == "price":
        return await query_handlers.price_command(update, context)
    if action == "orders":
        return await query_handlers.orders_command(update, context)
    if action == "status":
        return await status_handlers.status_command(update, context)
    if action == "history":
        return await query_handlers.history_command(update, context)
    if action == "config_view":
        return await update.message.reply_text(
            build_config_view(user, active_order_count=len(main.order_manager.orders)),
            parse_mode="HTML",
        )
    if action == "help":
        return await system_handlers.help_command(update, context)
    if action in ["rsi", "indicators"]:
        return await query_handlers.indicators_command(update, context)
    await update.message.reply_text("⚠️ 자연어 요청을 조회 명령으로 해석하지 못했습니다.")


async def _send_nl_ticker_disambiguation(query, intent, raw_name, candidates):
    token = create_nl_disambiguation_token(str(query.from_user.id), intent, candidates)
    buttons = [
        [InlineKeyboardButton(f"{name} ({code})", callback_data=f"nltickerpick|{token}|{idx}")]
        for idx, (name, code) in enumerate(candidates)
    ]
    await query.edit_message_text(
        f"🔍 '{raw_name}'과 정확히 일치하는 종목을 찾지 못했습니다. 후보 중 선택해 주세요:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def nl_ticker_disambiguation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_chat.id)
    try:
        _, token, idx_s = query.data.split("|")
        idx = int(idx_s)
    except (ValueError, AttributeError):
        await query.edit_message_text("⚠️ 잘못된 요청입니다.")
        return

    intent, err = pop_valid_nl_disambiguation(token, user_id, idx)
    if intent is None:
        await query.edit_message_text(f"⚠️ {err}")
        return

    user = main.user_manager.get_user(user_id)
    if not user or not user.get("is_active"):
        await query.edit_message_text("❌ 사용자 인증을 확인할 수 없습니다.")
        return

    try:
        await execute_confirmed_intent(query, context, user, intent)
    except Exception as e:
        await query.edit_message_text(f"❌ 자연어 요청 실행 실패: {e}")


def _format_action_summary(act: dict) -> str:
    """단일 ProposedAction에 대한 한 줄 요약 텍스트를 반환한다."""
    act_type = act.get("action_type")
    ex = exchange_display_name(act.get("exchange", ""))
    tk = act.get("ticker", "")

    if act_type == "manual_order":
        side_kr = "매수" if act.get("side") == "bid" else "매도"
        price = act.get("price", 0.0)
        vol = act.get("volume", 0.0)
        total = act.get("amount_krw") or (price * vol)
        return f"• [{ex}] {tk} {side_kr} {vol:g}개 @ {price:,.0f}원 (총 {total:,.0f}원)"

    if act_type == "cancel_orders":
        uuids = act.get("order_uuids", [])
        uuid_preview = ", ".join(uuids[:2]) + ("..." if len(uuids) > 2 else "")
        return f"• [{ex}] 미체결 주문 {len(uuids)}건 취소 ({uuid_preview})"

    if act_type == "strategy_rsi":
        strat = "RSI 분할 매수" if act.get("side") == "buy" else "RSI 분할 매도"
        count = act.get("count", 5)
        amount = act.get("amount_krw")
        amt_str = f", 총 {amount:,.0f}원" if amount else ""
        return f"• [{ex}] {tk} {strat} {count}분할{amt_str}"

    if act_type == "strategy_grid":
        sp = act.get("start_price", 0.0)
        ep = act.get("end_price", 0.0)
        count = act.get("count", 5)
        return f"• [{ex}] {tk} 거미줄 매매 ({sp:,.0f}~{ep:,.0f}원, {count}분할)"

    if act_type == "template_control":
        t_id = act.get("template_id")
        action = act.get("action")
        act_kr = {"run": "즉시 실행", "pause": "일시중지", "stop_and_cancel": "중지 및 주문취소", "topup": "예산 추가"}.get(action, action)
        return f"• 전략 템플릿 #{t_id} {act_kr}"

    if act_type == "update_config":
        return f"• 설정 변경: {act.get('config_key')} = {act.get('config_value')}"

    if act_type == "watchlist_change":
        act_kr = "관심종목 등록" if act.get("action") == "watch" else "관심종목 해제"
        return f"• [{ex}] {tk} {act_kr}"

    return f"• 작업: {act}"


async def execute_confirmed_actions(query, context, user, actions: list[dict]):
    """Gemini Function Calling 에이전트가 제안한 복수/단일 작업을 일괄 순차 실행한다."""
    user_id = str(query.from_user.id)
    results = []

    for idx, act in enumerate(actions, 1):
        act_type = act.get("action_type")
        ex = act.get("exchange") or user.get("preferences", {}).get("default_exchange", "upbit")
        tk = act.get("ticker", "")

        try:
            if act_type == "manual_order":
                side = act.get("side", "bid")
                price = float(act.get("price", 0.0))
                volume = float(act.get("volume", 0.0))
                if main.exchange_adapter:
                    volume = main.exchange_adapter.get_exchange(ex).round_volume(volume)
                ok, err = validate_max_order(user, price * volume)
                if not ok:
                    results.append(f"❌ {idx}. 주문 실패: {err}")
                    continue
                res = await main.exchange_adapter.create_order(user_id, ex, tk, side, price, volume)
                if res and "uuid" in res:
                    main.order_manager.add_order(user_id, ex, tk, res["uuid"], price, volume, side=side, strategy="manual")
                    side_kr = "매수" if side == "bid" else "매도"
                    results.append(f"✅ {idx}. [{exchange_display_name(ex)}] {tk} {side_kr} 성공 (ID: {res['uuid']})")
                else:
                    results.append(f"❌ {idx}. [{exchange_display_name(ex)}] {tk} 주문 실패: {res}")

            elif act_type == "cancel_orders":
                uuids = act.get("order_uuids", [])
                cancelled_cnt = 0
                for u in uuids:
                    order = main.order_manager.get_order(u)
                    if not order:
                        # user_orders에서 재탐색
                        for o in main.order_manager.get_user_orders(user_id, ex):
                            if o.get("uuid") == u:
                                order = o
                                break
                    if order and await main.cancel_and_remove_order(user_id, order):
                        cancelled_cnt += 1
                    await asyncio.sleep(0.05)
                results.append(f"✅ {idx}. [{exchange_display_name(ex)}] 주문 {cancelled_cnt}/{len(uuids)}건 취소 완료")

            elif act_type == "strategy_rsi":
                strat = act.get("strategy", "rsitrade")
                buy_range = act.get("buy_rsi_range") or user.get("preferences", {}).get("rsi_buy_range", "25-30")
                sell_range = act.get("sell_rsi_range") or user.get("preferences", {}).get("rsi_sell_range", "65-75")
                count = int(act.get("count") or user.get("preferences", {}).get("rsi_order_count", 5))
                budget = float(act.get("amount_krw") or user.get("preferences", {}).get("rsi_budget_krw") or 0)
                group_no = main.order_manager.get_next_group_no(user_id)

                if strat == "rsitrade":
                    if act.get("dca_mode"):
                        budgets = [budget * w for w in get_dca_weights(count)]
                    else:
                        budgets = [budget / count] * count
                    await execute_rsitrade_orders(
                        exchange_adapter=main.exchange_adapter, order_manager=main.order_manager,
                        signal_engine=main.signal_engine,
                        user_id=user_id, exchange=ex, ticker=tk,
                        buy_rsi_range=buy_range, sell_rsi_range=sell_range,
                        count=count, per_order_budgets=budgets,
                        user=user, group_no=group_no, bot=context.bot, notify_chat_id=user_id,
                        trigger_sync_fn=main.trigger_realtime_sync,
                    )
                    results.append(f"✅ {idx}. [{exchange_display_name(ex)}] {tk} RSI 분할 매수 실행 완료")
                else:
                    await execute_sgridrsi_orders(
                        exchange_adapter=main.exchange_adapter, order_manager=main.order_manager,
                        signal_engine=main.signal_engine,
                        user_id=user_id, exchange=ex, ticker=tk,
                        sell_rsi_range=sell_range, count=count, budget=budget,
                        user=user, group_no=group_no, bot=context.bot, notify_chat_id=user_id,
                        trigger_sync_fn=main.trigger_realtime_sync,
                    )
                    results.append(f"✅ {idx}. [{exchange_display_name(ex)}] {tk} RSI 분할 매도 실행 완료")

            elif act_type == "template_control":
                t_id = act.get("template_id")
                action = act.get("action")
                path_map = {
                    "run": f"/api/templates/{t_id}/run",
                    "pause": f"/api/templates/{t_id}/pause",
                    "stop_and_cancel": f"/api/templates/{t_id}/stop-cancel",
                    "topup": f"/api/templates/{t_id}/topup",
                }
                api_path = path_map.get(action)
                if api_path:
                    body = {"amount_krw": act.get("amount_krw")} if action == "topup" else None
                    is_adm = bool(user.get("is_admin", False))
                    resp = await request_manager_api("POST", api_path, user_id, is_admin=is_adm, json_body=body)
                    if resp.get("ok"):
                        results.append(f"✅ {idx}. 전략 템플릿 #{t_id} {action} 완료")
                    else:
                        results.append(f"❌ {idx}. 전략 템플릿 #{t_id} 실패: {resp.get('error')}")
                else:
                    results.append(f"⚠️ {idx}. 지원되지 않는 템플릿 명령: {action}")

            elif act_type == "update_config":
                ckey = act.get("config_key")
                cval = act.get("config_value")
                main.user_manager.update_preference(user_id, ckey, cval)
                results.append(f"✅ {idx}. 설정 변경 완료: {ckey} = {format_config_value(ckey, cval)}")

            elif act_type == "watchlist_change":
                act_str = act.get("action")
                if act_str == "watch":
                    changed = main.user_manager.add_watchlist(user_id, ex, tk)
                    results.append(f"✅ {idx}. [{exchange_display_name(ex)}] {tk} 관심종목 등록 완료")
                else:
                    changed = main.user_manager.remove_watchlist(user_id, ex, tk)
                    results.append(f"✅ {idx}. [{exchange_display_name(ex)}] {tk} 관심종목 해제 완료")

            else:
                results.append(f"⚠️ {idx}. 알 수 없는 작업 유형: {act_type}")

        except Exception as e:
            main._log.error("execute_confirmed_actions failed for act=%s: %s", act, e, exc_info=True)
            results.append(f"❌ {idx}. 실행 오류 ({act_type}): {str(e)}")

    summary_text = "🎉 **실행 결과 보고**\n\n" + "\n".join(results)
    await query.edit_message_text(summary_text)


async def execute_confirmed_intent(query, context, user, intent):
    """기존 단일 intent 실행 함수 (하위 호환성 유지)."""
    user_id = str(query.from_user.id)
    action = intent.get("action")
    exchange = intent.get("exchange") or user.get("preferences", {}).get("default_exchange", "upbit")
    raw_ticker = intent.get("ticker")
    _, ticker = parse_exchange_and_ticker([exchange, raw_ticker] if raw_ticker else [exchange], exchange)
    if ticker:
        resolved = await main.exchange_adapter.resolve_ticker(user_id, exchange, ticker)
        if (
            main.exchange_adapter.get_exchange(exchange).requires_numeric_ticker()
            and resolved
            and any('가' <= c <= '힣' for c in resolved)
        ):
            candidates = await find_kr_stock_candidates(ticker, main.exchange_adapter, user_id, exchange)
            if candidates:
                await _send_nl_ticker_disambiguation(query, intent, ticker, candidates)
                return
            await query.edit_message_text(
                f"⚠️ {exchange_display_name(exchange)}에서 '{ticker}' 종목을 찾을 수 없습니다. 종목코드로 다시 시도해 주세요."
            )
            return
        ticker = resolved

    if action == "config_set":
        key = str(intent.get("config_key") or "").strip().lower()
        raw_value = str(intent.get("config_value") or "").strip()
        if key in POLL_INTERVAL_KEYS:
            await query.edit_message_text("❌ 폴링 설정은 config/.env에서 직접 변경 후 재시작해주세요.")
            return
        value = parse_config_value(key, raw_value)
        validate_config_update(user, key, value)
        main.user_manager.update_preference(user_id, key, value)
        await query.edit_message_text(f"✅ {key} 설정을 {format_config_value(key, value)}(으)로 저장했습니다.")
        return

    if action in ["watch", "unwatch"]:
        if not main.exchange_adapter.get_exchange(exchange).supports_minute_candles() and get_user_rsi_interval(user) != "day":
            await query.edit_message_text(main._KIS_RSI_MINUTE_ERROR)
            return
        changed = main.user_manager.add_watchlist(user_id, exchange, ticker) if action == "watch" else main.user_manager.remove_watchlist(user_id, exchange, ticker)
        label = "등록" if action == "watch" else "삭제"
        await query.edit_message_text(f"{'✅' if changed else 'ℹ️'} {exchange_display_name(exchange)} {ticker} 관심 종목 {label} 처리했습니다.")
        return

    if action == "cancel":
        orders = [o for o in main.order_manager.get_user_orders(user_id, exchange) if o["ticker"] == ticker]
        success = 0
        for order in orders:
            if await main.cancel_and_remove_order(user_id, order):
                success += 1
            await asyncio.sleep(0.1)
        await query.edit_message_text(f"✅ {ticker} 취소 완료 ({success}/{len(orders)}건 성공)")
        return

    if action in ["buy", "sell"]:
        price = float(intent.get("price") or 0)
        volume = main.exchange_adapter.get_exchange(exchange).round_volume(float(intent.get("volume") or 0))
        if price <= 0 or volume <= 0:
            await query.edit_message_text("❌ 가격과 수량을 확인할 수 없어 주문을 중단합니다.")
            return
        ok, error_msg = validate_max_order(user, price * volume)
        if not ok:
            await query.edit_message_text(error_msg)
            return
        side = "bid" if action == "buy" else "ask"
        res = await main.exchange_adapter.create_order(user_id, exchange, ticker, side, price, volume)
        if res and "uuid" in res:
            main.order_manager.add_order(user_id, exchange, ticker, res["uuid"], price, volume, side=side, strategy="manual")
            await query.edit_message_text(f"✅ {exchange_display_name(exchange)} {ticker} {'매수' if side == 'bid' else '매도'} 주문 완료\n주문ID: {res['uuid']}")
        else:
            append_operational_event("error", "natural_language_order", "order failed", f"{exchange} {ticker} {side}")
            await query.edit_message_text(f"❌ 주문 실패: {res}")
        return

    if action == "rsitrade":
        if not main.exchange_adapter.get_exchange(exchange).supports_minute_candles() and get_user_rsi_interval(user) != "day":
            await query.edit_message_text(main._KIS_RSI_MINUTE_ERROR)
            return
        buy_range = intent.get("buy_rsi_range") or user["preferences"].get("rsi_buy_range", "25-30")
        sell_range = intent.get("sell_rsi_range") or user["preferences"].get("rsi_sell_range", "65-75")
        count = int(intent.get("count") or user["preferences"].get("rsi_order_count", 5))
        budget = float(intent.get("amount_krw") or user["preferences"].get("rsi_budget_krw") or 0)
        if budget <= 0:
            await query.edit_message_text("❌ RSI 전략 예산을 확인할 수 없어 주문을 중단합니다.")
            return
        await query.edit_message_text("🚀 자연어 RSI 전략 주문을 전송 중입니다...")
        if intent.get("dca_mode"):
            per_order_budgets = [budget * w for w in get_dca_weights(count)]
        else:
            per_order_budgets = [budget / count] * count
        group_no = main.order_manager.get_next_group_no(user_id)
        await execute_rsitrade_orders(
            exchange_adapter=main.exchange_adapter, order_manager=main.order_manager,
            signal_engine=main.signal_engine,
            user_id=user_id, exchange=exchange, ticker=ticker,
            buy_rsi_range=buy_range, sell_rsi_range=sell_range,
            count=count, per_order_budgets=per_order_budgets,
            user=user, group_no=group_no, bot=context.bot, notify_chat_id=user_id,
            trigger_sync_fn=main.trigger_realtime_sync,
        )
        return

    if action == "sgridrsi":
        if not main.exchange_adapter.get_exchange(exchange).supports_minute_candles() and get_user_rsi_interval(user) != "day":
            await query.edit_message_text(main._KIS_RSI_MINUTE_ERROR)
            return
        sell_range = intent.get("sell_rsi_range") or user["preferences"].get("rsi_sell_range", "65-75")
        count = int(intent.get("count") or user["preferences"].get("rsi_order_count", 5))
        budget = float(intent.get("amount_krw") or user["preferences"].get("rsi_budget_krw") or 0)
        if budget <= 0:
            await query.edit_message_text("❌ RSI 매도 전략 예산을 확인할 수 없어 주문을 중단합니다.")
            return
        await query.edit_message_text("🚀 자연어 RSI 매도 전략 주문을 전송 중입니다...")
        group_no = main.order_manager.get_next_group_no(user_id)
        await execute_sgridrsi_orders(
            exchange_adapter=main.exchange_adapter, order_manager=main.order_manager,
            signal_engine=main.signal_engine,
            user_id=user_id, exchange=exchange, ticker=ticker,
            sell_rsi_range=sell_range, count=count, budget=budget,
            user=user, group_no=group_no, bot=context.bot, notify_chat_id=user_id,
            trigger_sync_fn=main.trigger_realtime_sync,
        )
        return

    await query.edit_message_text("⚠️ 이 자연어 요청은 아직 실행할 수 없습니다. /help에서 지원 명령을 확인해 주세요.")


def _update_user_nl_context(context, user_text, outcome):
    """대화 맥락 보관 (최대 4턴 슬라이딩 윈도우)."""
    if not context or not hasattr(context, "user_data") or context.user_data is None:
        return
    history = context.user_data.get("_nl_recent_context")
    if not isinstance(history, list):
        history = []

    history.append({"role": "user", "text": user_text})

    if isinstance(outcome, AgentRunResult):
        # 에이전트 결과
        summary = outcome.reply_text[:100] if outcome.reply_text else ""
        if outcome.proposed_actions:
            summary = f"{len(outcome.proposed_actions)} actions proposed: {summary}"
        history.append({"role": "bot", "action": "agent_loop", "summary": summary})
    elif isinstance(outcome, dict):
        action = outcome.get("action")
        ticker = outcome.get("ticker")
        history.append({"role": "bot", "action": action, "ticker": ticker})

    context.user_data["_nl_recent_context"] = history[-4:]


@check_auth
async def natural_language_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    text = (update.message.text or "").strip()
    if not text or text.startswith("/"):
        return
    user_id = str(update.effective_user.id)
    log_command(user_id, "nl", source="nl")
    prefs = user.get("preferences", {})

    recent_context = context.user_data.get("_nl_recent_context", []) if context and hasattr(context, "user_data") and context.user_data else []

    # 1. 패스트트랙: 단순 조회/룰 기반 전처리 적중 시 Gemini 호출 없이 0초대 즉시 응답
    preprocessed = preprocess_natural_language_intent(text, user)
    if preprocessed:
        append_preprocess_hit(preprocessed)
        _update_user_nl_context(context, text, preprocessed)
        if preprocessed.get("action") == "clarify":
            await update.message.reply_text(preprocessed.get("question") or _clarify_message(text, preprocessed))
            return
        if _is_immediate_intent(preprocessed.get("action")):
            append_natural_language_log(text, None, preprocessed, user_id=user_id, confirm_status="auto")
            await execute_query_intent(update, context, user, preprocessed)
            return

        # 단순 룰 매칭으로 확인이 필요한 주문/취소인 경우
        intent = normalize_natural_language_intent(text, preprocessed, user)
        log_id = append_natural_language_log(text, None, intent, user_id=user_id, confirm_status="pending")
        confirm_text = f"🧠 자연어 요청 확인\n\n{_intent_summary(intent)}\n\n위 내용으로 실행할까요?"
        token = str(len(main._pending_nl_intents) + 1)
        main._pending_nl_intents[token] = {"user_id": str(update.effective_chat.id), "intent": intent, "log_id": log_id}
        keyboard = [[InlineKeyboardButton("✅ 실행", callback_data=f"nlrun|{token}"),
                     InlineKeyboardButton("❌ 취소", callback_data=f"nlcancel|{token}")]]
        await update.message.reply_text(confirm_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # 2. Gemini 에이전트 활성화 여부 확인
    if not prefs.get("llm_enabled") or not has_gemini_key(user):
        await update.message.reply_text("💬 자연어 명령을 사용하려면 /config에서 Gemini API 키를 저장한 뒤 /config set llm_enabled on을 실행해 주세요.")
        return

    # 3. Gemini Function Calling 멀티턴 에이전트 루프 진입
    status_msg = await update.message.reply_text("🤖 AI가 요청을 분석하고 있습니다...")

    agent_result = await run_nl_agent_loop(
        text=text,
        user=user,
        user_id=user_id,
        recent_context=recent_context,
        exchange_adapter=main.exchange_adapter,
        order_manager=main.order_manager,
        signal_engine=main.signal_engine,
        user_manager=main.user_manager,
    )

    _update_user_nl_context(context, text, agent_result)

    # 호출된 도구 목록 요약 로깅
    called_tools = [t.get("tool") for t in agent_result.tool_trace if t.get("tool")]
    llm_action_summary = ", ".join(called_tools) if called_tools else "chat"

    # 케이스 A: 쓰기 변경 제안이 없는 경우 (순수 복합 조회 / 분석 / 일반 대화)
    if not agent_result.proposed_actions:
        append_natural_language_log(
            text,
            {"action": llm_action_summary},
            {"action": "answer"},
            user_id=user_id,
            confirm_status="auto",
            tool_trace=agent_result.tool_trace,
            proposed_actions=[],
        )
        await status_msg.edit_text(agent_result.reply_text or "요청을 처리했습니다.")
        return

    # 케이스 B: 쓰기 변경 제안이 존재하는 경우 (주문 / 취소 / 전략 실행 / 설정 변경 등)
    log_id = append_natural_language_log(
        text,
        {"action": llm_action_summary},
        {"action": "multi_action"},
        user_id=user_id,
        confirm_status="pending",
        tool_trace=agent_result.tool_trace,
        proposed_actions=agent_result.proposed_actions,
    )

    action_summaries = [_format_action_summary(a) for a in agent_result.proposed_actions]
    confirm_text = (
        f"{agent_result.reply_text}\n\n"
        f"📋 **실행 계획 ({len(agent_result.proposed_actions)}건)**\n"
        f"{'\n'.join(action_summaries)}\n\n"
        f"위 작업을 실행할까요?"
    )

    token = str(len(main._pending_nl_intents) + 1)
    main._pending_nl_intents[token] = {
        "user_id": str(update.effective_chat.id),
        "actions": agent_result.proposed_actions,
        "log_id": log_id,
        "reply_text": agent_result.reply_text,
    }

    keyboard = [[
        InlineKeyboardButton("✅ 실행", callback_data=f"nlrun|{token}"),
        InlineKeyboardButton("❌ 취소", callback_data=f"nlcancel|{token}"),
    ]]
    await status_msg.edit_text(confirm_text, reply_markup=InlineKeyboardMarkup(keyboard))


async def natural_language_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, token = query.data.split("|", 1)
    pending = main._pending_nl_intents.pop(token, None)
    if not pending:
        await query.edit_message_text("⚠️ 만료된 자연어 요청입니다. 다시 입력해 주세요.")
        return
    if action == "nlcancel":
        update_natural_language_log_outcome(pending.get("log_id"), "rejected")
        await query.edit_message_text("❌ 자연어 요청을 취소했습니다.")
        return
    user_id = str(query.from_user.id)
    if pending.get("user_id") != user_id:
        update_natural_language_log_outcome(pending.get("log_id"), "expired")
        await query.edit_message_text("❌ 다른 사용자의 요청은 실행할 수 없습니다.")
        return
    user = main.user_manager.get_user(user_id)
    if not user or not user.get("is_active"):
        await query.edit_message_text("❌ 사용자 인증을 확인할 수 없습니다.")
        return
    update_natural_language_log_outcome(pending.get("log_id"), "confirmed")

    try:
        if "actions" in pending:
            # 멀티 액션 일괄 실행
            await execute_confirmed_actions(query, context, user, pending["actions"])
        elif "intent" in pending:
            # 단일 intent 실행 (하위 호환)
            await execute_confirmed_intent(query, context, user, pending["intent"])
        else:
            await query.edit_message_text("⚠️ 실행할 작업 데이터가 없습니다.")
    except Exception as e:
        main._log.error("Execution failed: %s", e, exc_info=True)
        await query.edit_message_text(f"❌ 자연어 요청 실행 실패: {e}")
