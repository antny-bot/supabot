"""/buy, /sell — 단일 지정가/시장가 수동 주문 확인 및 실행.

`_pending_manual_orders`/`MANUAL_ORDER_TTL_SECONDS`/`create_manual_order_token`/
`pop_valid_manual_order`는 main.py 소유 상태로 남는다 (main.<name>으로 접근).
"""
import uuid as _uuid

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import main
from main import check_auth, check_details_help, resolve_ticker_for_command
from core.parsers import parse_exchange_and_ticker, parse_number, is_exchange_token, validate_max_order, exchange_display_name, is_us_stock_ticker
from core.formatters import build_manual_order_confirm_message
from core.operational_events import append_operational_event
from core import trading_gate


@check_auth
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "buy"): return
    ok, halt_msg = trading_gate.assert_can_trade()
    if not ok:
        await update.message.reply_text(halt_msg)
        return
    user_id = str(update.effective_chat.id)
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("⚠️ 사용법: /buy [거래소] [종목] [가격|market] [수량] (거래소 생략 시 업비트)")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = await resolve_ticker_for_command(
        update, user_id, args, default_exchange, "/buy kis 000250 50000 1"
    )
    if ticker is None:
        return
    offset = 2 if is_exchange_token(args[0], exchange) else 1

    auto_reorder = args[-1].lower() in ("유지", "--keep") if len(args) > offset + 2 else False
    if auto_reorder:
        args = args[:-1]

    try:
        is_market = args[offset].lower() == "market"
        if is_market:
            price, volume, ord_type = 0.0, parse_number(args[offset + 1]), "market"
        else:
            price, volume, ord_type = parse_number(args[offset]), parse_number(args[offset + 1]), "limit"
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ 가격과 수량은 숫자여야 합니다.")
        return

    if not is_market:
        ok, error_msg = validate_max_order(user, price * volume)
        if not ok:
            await update.message.reply_text(error_msg)
            return

    token = main.create_manual_order_token(user_id, exchange, "bid", ticker, price, volume, ord_type=ord_type, auto_reorder=auto_reorder)
    confirm_data = f"manualrun|{token}"
    keyboard = [[InlineKeyboardButton("✅ 매수 실행", callback_data=confirm_data),
                 InlineKeyboardButton("❌ 취소", callback_data=f"manualcancel|{token}")]]
    await update.message.reply_text(
        build_manual_order_confirm_message(exchange, ticker, "bid", price, volume, user, ord_type=ord_type, auto_reorder=auto_reorder),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


@check_auth
async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "sell"): return
    ok, halt_msg = trading_gate.assert_can_trade()
    if not ok:
        await update.message.reply_text(halt_msg)
        return
    user_id = str(update.effective_chat.id)
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("⚠️ 사용법: /sell [거래소] [종목] [가격|market] [수량] (거래소 생략 시 업비트)")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = await resolve_ticker_for_command(
        update, user_id, args, default_exchange, "/sell kis 000250 50000 1"
    )
    if ticker is None:
        return
    offset = 2 if is_exchange_token(args[0], exchange) else 1

    auto_reorder = args[-1].lower() in ("유지", "--keep") if len(args) > offset + 2 else False
    if auto_reorder:
        args = args[:-1]

    try:
        is_market = args[offset].lower() == "market"
        if is_market:
            price, volume, ord_type = 0.0, parse_number(args[offset + 1]), "market"
        else:
            price, volume, ord_type = parse_number(args[offset]), parse_number(args[offset + 1]), "limit"
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ 가격과 수량은 숫자여야 합니다.")
        return

    token = main.create_manual_order_token(user_id, exchange, "ask", ticker, price, volume, ord_type=ord_type, auto_reorder=auto_reorder)
    confirm_data = f"manualrun|{token}"
    keyboard = [[InlineKeyboardButton("✅ 매도 실행", callback_data=confirm_data),
                 InlineKeyboardButton("❌ 취소", callback_data=f"manualcancel|{token}")]]
    await update.message.reply_text(
        build_manual_order_confirm_message(exchange, ticker, "ask", price, volume, user, ord_type=ord_type, auto_reorder=auto_reorder),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def manual_order_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, token = query.data.split("|", 1)
    if action == "manualcancel":
        main._pending_manual_orders.pop(token, None)
        await query.edit_message_text("❌ 주문이 취소되었습니다.")
        return

    user_id = str(query.from_user.id)
    user = main.user_manager.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
        return
    if not user.get("is_active"):
        await query.edit_message_text("❌ 사용자 인증을 확인할 수 없습니다.")
        return

    pending, error = main.pop_valid_manual_order(token, user_id)
    if error:
        await query.edit_message_text(f"⚠️ {error}")
        return
    exchange = pending["exchange"]
    side = pending["side"]
    ticker = pending["ticker"]
    price = float(pending["price"])
    volume = float(pending["volume"])
    ord_type = pending.get("ord_type", "limit")
    auto_reorder = pending.get("auto_reorder", False)
    is_market = ord_type == "market"
    can_ok, can_msg = trading_gate.assert_can_trade()
    if not can_ok:
        await query.edit_message_text(can_msg)
        return
    if side == "bid":
        order_krw = price * volume
        if is_market:
            # 시장가 매수는 확정 가격이 없어(price=0) 한도 검증이 그냥 통과되던 우회구멍이었다(L1).
            # 현재가로 노출을 추정해 동일하게 한도를 적용하고, 추정이 불가하면 안전하게 차단한다.
            tkr = await main.exchange_adapter.get_ticker(exchange, ticker, user_id)
            current_price = float(tkr.get("trade_price", 0)) if tkr else 0.0
            if current_price <= 0:
                await query.edit_message_text("⚠️ 현재가 조회에 실패하여 주문 한도를 검증할 수 없습니다. 잠시 후 다시 시도해 주세요.")
                return
            order_krw = current_price * volume
        ok, error_msg = validate_max_order(user, order_krw)
        if not ok:
            await query.edit_message_text(error_msg)
            return
        exp_ok, exp_msg = trading_gate.check_can_place_order(
            user, main.order_manager.get_user_orders(user_id), order_krw,
            is_usd=is_us_stock_ticker(exchange, ticker),
        )
        if not exp_ok:
            await query.edit_message_text(exp_msg)
            return

    ex = main.exchange_adapter.get_exchange(exchange)
    ex_env_label = ex.env_label(user.get("exchanges", {}).get(exchange, {}))
    env_notice = f" ({ex_env_label})" if ex_env_label else ""
    action = "매수" if side == "bid" else "매도"
    order_type_label = "시장가 " if is_market else ""
    is_reserved = getattr(ex, "supports_reserved_orders", False) and not ex.is_market_open(ticker)

    if is_reserved:
        res = {"uuid": f"reserved:{_uuid.uuid4().hex}"}
    else:
        await query.edit_message_text(f"🚀 {exchange_display_name(exchange)} {ticker} {order_type_label}{action} 주문 전송 중{env_notice}...")
        res = await main.exchange_adapter.create_order(user_id, exchange, ticker, side, price, volume, ord_type=ord_type)

    if res and "uuid" in res:
        main.order_manager.add_order(
            user_id, exchange, ticker, res["uuid"], price, volume, side=side, strategy="manual",
            status="reserved" if is_reserved else "wait", auto_reorder=auto_reorder,
        )
        if is_reserved:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⏳ {exchange_display_name(exchange)} {ticker} {action} 주문 예약 등록 완료{env_notice}!\n장 개장 시 자동으로 실제 주문이 제출됩니다.",
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ {exchange_display_name(exchange)} {ticker} {action} 주문 완료{env_notice}!\n주문ID: {res['uuid']}",
            )
    else:
        append_operational_event("error", "manual_order", "manual order failed", f"{exchange} {ticker} {side}")
        await context.bot.send_message(chat_id=user_id, text=f"❌ 주문 실패: {res}")
