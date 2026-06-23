"""자연어(Gemini NL) 라우팅 — 의도 파싱·확인·실행.

`_pending_nl_intents`/`LLM_COMMAND_CATALOG`/`_log`/`_KIS_RSI_MINUTE_ERROR` 등은
main.py 소유 상태로 남는다 (main.<name>으로 접근). `help_command`는
`handlers.system_handlers`로 이동했으므로 지연 임포트로 호출한다.
"""
import asyncio
import json

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
from core.order_execution import execute_rsitrade_orders, execute_sgridrsi_orders
from core.stock_resolver import find_kr_stock_candidates
from core.ticker_disambiguation import (
    create_nl_disambiguation_token,
    pop_valid_nl_disambiguation,
)


def _build_llm_prompt(user_text, user):
    prefs = user.get("preferences", {})
    return (
        "Parse Korean trading bot text. Return JSON only.\n"
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
        "Schema: {\"action\": string, \"exchange\": string|null, \"ticker\": string|null, "
        "\"price\": number|null, \"volume\": number|null, \"amount_krw\": number|null, "
        "\"start_price\": number|null, \"end_price\": number|null, \"count\": integer|null, "
        "\"buy_rsi_range\": string|null, \"sell_rsi_range\": string|null, \"dca_mode\": boolean|null, "
        "\"config_key\": string|null, \"config_value\": string|null, \"question\": string|null}.\n"
        "Exchange: upbit|bithumb|kis|toss|null. Korean stock => kis or toss (default kis if unspecified, "
        "toss if user explicitly says 토스/tossinvest). Samsung => 005930. Crypto ticker: BTC/ETH/XRP.\n"
        f"Default exchange: {prefs.get('default_exchange', 'upbit')}.\n"
        f"Commands:\n{main.LLM_COMMAND_CATALOG}\n"
        f"User text: {user_text}"
    )


async def parse_natural_language_intent(text, user):
    api_key = user.get("llm", {}).get("gemini_api_key", "")
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=user.get("preferences", {}).get("llm_model", "gemini-2.5-flash-lite"),
            contents=_build_llm_prompt(text, user),
            config=config,
        )
        return json.loads(response.text)
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
    """후보 종목을 버튼으로 제시한다. 선택 시 intent['ticker']를 코드로 바꿔 execute_confirmed_intent를 재호출."""
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


async def execute_confirmed_intent(query, context, user, intent):
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
            if await main.exchange_adapter.cancel_order(user_id, exchange, order["uuid"], order["ticker"]):
                main.order_manager.remove_order(order["uuid"])
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


@check_auth
async def natural_language_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    text = (update.message.text or "").strip()
    if not text or text.startswith("/"):
        return
    user_id = str(update.effective_user.id)
    log_command(user_id, "nl", source="nl")
    prefs = user.get("preferences", {})

    preprocessed = preprocess_natural_language_intent(text, user)
    if preprocessed:
        append_preprocess_hit(preprocessed)
        if preprocessed.get("action") == "clarify":
            await update.message.reply_text(preprocessed.get("question") or _clarify_message(text, preprocessed))
            return
        if _is_immediate_intent(preprocessed.get("action")):
            append_natural_language_log(text, None, preprocessed, user_id=user_id, confirm_status="auto")
            await execute_query_intent(update, context, user, preprocessed)
            return
        intent = normalize_natural_language_intent(text, preprocessed, user)
        log_id = append_natural_language_log(text, None, intent, user_id=user_id, confirm_status="pending")
        confirm_text = f"🧠 자연어 요청 확인\n\n{_intent_summary(intent)}\n\n위 내용으로 실행할까요?"
        token = str(len(main._pending_nl_intents) + 1)
        main._pending_nl_intents[token] = {"user_id": str(update.effective_chat.id), "intent": intent, "log_id": log_id}
        keyboard = [[InlineKeyboardButton("✅ 실행", callback_data=f"nlrun|{token}"),
                     InlineKeyboardButton("❌ 취소", callback_data=f"nlcancel|{token}")]]
        await update.message.reply_text(confirm_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if not prefs.get("llm_enabled") or not has_gemini_key(user):
        await update.message.reply_text("💬 자연어 명령을 사용하려면 /config에서 Gemini API 키를 저장한 뒤 /config set llm_enabled on을 실행해 주세요.")
        return

    llm_intent = await parse_natural_language_intent(text, user)
    intent = normalize_natural_language_intent(text, llm_intent, user)
    action = intent.get("action") if isinstance(intent, dict) else None
    is_immediate = _is_immediate_intent(action)
    confirm_status = "auto" if (not intent or action in [None, "clarify"] or is_immediate) else "pending"
    log_id = append_natural_language_log(text, llm_intent, intent, user_id=user_id, confirm_status=confirm_status)
    if not intent or action in [None, "clarify"]:
        question = intent.get("question") if isinstance(intent, dict) else None
        await update.message.reply_text(question or _clarify_message(text, intent))
        return

    if is_immediate:
        await execute_query_intent(update, context, user, intent)
        return

    confirm_text = f"🧠 자연어 요청 확인\n\n{_intent_summary(intent)}\n\n위 내용으로 실행할까요?"
    if action in ("rsitrade", "gridrsi", "sgridrsi"):
        from handlers import strategy_handlers
        status_msg = await update.message.reply_text(f"🔍 RSI 가격 분석 중...")
        confirm_text = await strategy_handlers.build_rsigrid_confirm_summary(str(update.effective_chat.id), user, intent)
        if not confirm_text:
            await status_msg.edit_text("❌ RSI 가격 역산에 실패했습니다. 데이터를 불러올 수 없습니다.")
            return

    token = str(len(main._pending_nl_intents) + 1)
    main._pending_nl_intents[token] = {"user_id": str(update.effective_chat.id), "intent": intent, "log_id": log_id}
    keyboard = [[InlineKeyboardButton("✅ 실행", callback_data=f"nlrun|{token}"),
                 InlineKeyboardButton("❌ 취소", callback_data=f"nlcancel|{token}")]]
    if action in ("rsitrade", "gridrsi", "sgridrsi"):
        await status_msg.edit_text(confirm_text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(
            confirm_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


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
        await execute_confirmed_intent(query, context, user, pending["intent"])
    except Exception as e:
        await query.edit_message_text(f"❌ 자연어 요청 실행 실패: {e}")
