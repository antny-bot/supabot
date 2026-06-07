"""자연어(Gemini NL) 라우팅 — 의도 파싱·확인·실행.

`_pending_nl_intents`/`LLM_COMMAND_CATALOG`/`_log`/`help_command`/
`_KIS_RSI_MINUTE_ERROR` 등은 main.py 소유 상태로 남는다 (main.<name>으로 접근).
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
    _looks_like_rsi_split_request,
)
from core.parsers import (
    POLL_INTERVAL_KEYS, parse_config_value, validate_config_update,
    parse_exchange_and_ticker, exchange_display_name, validate_max_order,
    parse_rsi_range, interpolate_range, get_user_rsi_interval, has_gemini_key,
)
from core.formatters import build_config_view, format_config_value


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
        "Schema: {\"action\": string, \"exchange\": string|null, \"ticker\": string|null, "
        "\"price\": number|null, \"volume\": number|null, \"amount_krw\": number|null, "
        "\"start_price\": number|null, \"end_price\": number|null, \"count\": integer|null, "
        "\"buy_rsi_range\": string|null, \"sell_rsi_range\": string|null, "
        "\"config_key\": string|null, \"config_value\": string|null, \"question\": string|null}.\n"
        "Exchange: upbit|bithumb|kis|null. Korean stock => kis. Samsung => 005930. Crypto ticker: BTC/ETH/XRP.\n"
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
        return (
            f"{exchange_display_name(exchange)} {ticker} / "
            f"매수 RSI {buy_range} / 매도 RSI {sell_range} / "
            f"{count}분할 / 총 {amount_text}"
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
    from handlers import status_handlers, query_handlers
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
        return await main.help_command(update, context)
    if action in ["rsi", "indicators"]:
        return await query_handlers.indicators_command(update, context)
    await update.message.reply_text("⚠️ 자연어 요청을 조회 명령으로 해석하지 못했습니다.")


async def execute_confirmed_intent(query, context, user, intent):
    user_id = str(query.from_user.id)
    action = intent.get("action")
    exchange = intent.get("exchange") or user.get("preferences", {}).get("default_exchange", "upbit")
    raw_ticker = intent.get("ticker")
    _, ticker = parse_exchange_and_ticker([exchange, raw_ticker] if raw_ticker else [exchange], exchange)

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
        if exchange == "kis" and get_user_rsi_interval(user) != "day":
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
        volume = float(intent.get("volume") or 0)
        if exchange == "kis":
            volume = int(volume)
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
        if exchange == "kis" and get_user_rsi_interval(user) != "day":
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
        b_start, b_end = parse_rsi_range(buy_range)
        s_start, s_end = parse_rsi_range(sell_range)
        budget_per_order = budget / count
        success = 0
        for i in range(count):
            target_rsi = interpolate_range(b_start, b_end, i, count)
            sell_target_rsi = interpolate_range(s_start, s_end, i, count)
            price = await main.signal_engine.get_price_by_rsi(exchange, ticker, target_rsi, side="bid", interval=get_user_rsi_interval(user), user_id=user_id)
            if not price:
                continue
            volume = round(budget_per_order / price, 4)
            if exchange == "kis":
                volume = int(volume)
            if volume <= 0:
                continue
            res = await main.exchange_adapter.create_order(user_id, exchange, ticker, "bid", price, volume)
            if res and "uuid" in res:
                main.order_manager.add_order(user_id, exchange, ticker, res["uuid"], price, volume, side="bid", strategy="rsitrade", target_rsi=target_rsi, linked_to=sell_target_rsi)
                success += 1
            await asyncio.sleep(0.2)
        await context.bot.send_message(chat_id=user_id, text=f"✅ `{ticker}` 자연어 RSI 전략 가동 완료! ({success}/{count}건 예약됨)")
        return

    if action == "sgridrsi":
        if exchange == "kis" and get_user_rsi_interval(user) != "day":
            await query.edit_message_text(main._KIS_RSI_MINUTE_ERROR)
            return
        sell_range = intent.get("sell_rsi_range") or user["preferences"].get("rsi_sell_range", "65-75")
        count = int(intent.get("count") or user["preferences"].get("rsi_order_count", 5))
        budget = float(intent.get("amount_krw") or user["preferences"].get("rsi_budget_krw") or 0)
        if budget <= 0:
            await query.edit_message_text("❌ RSI 매도 전략 예산을 확인할 수 없어 주문을 중단합니다.")
            return
        await query.edit_message_text("🚀 자연어 RSI 매도 전략 주문을 전송 중입니다...")
        s_start, s_end = parse_rsi_range(sell_range)
        budget_per_order = budget / count
        success = 0
        for i in range(count):
            target_rsi = interpolate_range(s_start, s_end, i, count)
            price = await main.signal_engine.get_price_by_rsi(exchange, ticker, target_rsi, side="ask", interval=get_user_rsi_interval(user), user_id=user_id)
            if not price:
                continue
            volume = round(budget_per_order / price, 4)
            if exchange == "kis":
                volume = int(volume)
            if volume <= 0:
                continue
            res = await main.exchange_adapter.create_order(user_id, exchange, ticker, "ask", price, volume)
            if res and "uuid" in res:
                main.order_manager.add_order(user_id, exchange, ticker, res["uuid"], price, volume, side="ask", strategy="sgridrsi", target_rsi=target_rsi, linked_to=None)
                success += 1
            await asyncio.sleep(0.2)
        await context.bot.send_message(chat_id=user_id, text=f"✅ `{ticker}` 자연어 RSI 매도 전략 가동 완료! ({success}/{count}건 예약됨)")
        return

    await query.edit_message_text("⚠️ 이 자연어 요청은 아직 실행할 수 없습니다. /help에서 지원 명령을 확인해 주세요.")


@check_auth
async def natural_language_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    text = (update.message.text or "").strip()
    if not text or text.startswith("/"):
        return
    log_command(str(update.effective_user.id), "nl", source="nl")
    prefs = user.get("preferences", {})

    preprocessed = preprocess_natural_language_intent(text, user)
    if preprocessed:
        append_preprocess_hit(preprocessed)
        if preprocessed.get("action") == "clarify":
            await update.message.reply_text(preprocessed.get("question") or _clarify_message(text, preprocessed))
            return
        if _is_immediate_intent(preprocessed.get("action")):
            await execute_query_intent(update, context, user, preprocessed)
            return
        intent = normalize_natural_language_intent(text, preprocessed, user)
        confirm_text = f"🧠 자연어 요청 확인\n\n{_intent_summary(intent)}\n\n위 내용으로 실행할까요?"
        token = str(len(main._pending_nl_intents) + 1)
        main._pending_nl_intents[token] = {"user_id": str(update.effective_chat.id), "intent": intent}
        keyboard = [[InlineKeyboardButton("✅ 실행", callback_data=f"nlrun|{token}"),
                     InlineKeyboardButton("❌ 취소", callback_data=f"nlcancel|{token}")]]
        await update.message.reply_text(confirm_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if not prefs.get("llm_enabled") or not has_gemini_key(user):
        await update.message.reply_text("💬 자연어 명령을 사용하려면 /config에서 Gemini API 키를 저장한 뒤 /config set llm_enabled on을 실행해 주세요.")
        return

    llm_intent = await parse_natural_language_intent(text, user)
    intent = normalize_natural_language_intent(text, llm_intent, user)
    append_natural_language_log(text, llm_intent, intent)
    if not intent or intent.get("action") in [None, "clarify"]:
        question = intent.get("question") if isinstance(intent, dict) else None
        await update.message.reply_text(question or _clarify_message(text, intent))
        return

    action = intent.get("action")
    if _is_immediate_intent(action):
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
    main._pending_nl_intents[token] = {"user_id": str(update.effective_chat.id), "intent": intent}
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
        await query.edit_message_text("❌ 자연어 요청을 취소했습니다.")
        return
    user_id = str(query.from_user.id)
    if pending.get("user_id") != user_id:
        await query.edit_message_text("❌ 다른 사용자의 요청은 실행할 수 없습니다.")
        return
    user = main.user_manager.get_user(user_id)
    if not user or not user.get("is_active"):
        await query.edit_message_text("❌ 사용자 인증을 확인할 수 없습니다.")
        return
    try:
        await execute_confirmed_intent(query, context, user, pending["intent"])
    except Exception as e:
        await query.edit_message_text(f"❌ 자연어 요청 실행 실패: {e}")
