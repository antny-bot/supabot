"""/grid, /sgrid, /rsitrade, /sgridrsi — 전략 주문 커맨드 및 확인 콜백.

`_KIS_RSI_MINUTE_ERROR`/`trigger_realtime_sync`/ConversationHandler 상태 상수 등은
main.py 소유 상태로 남는다 (main.<name>으로 접근).
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import main
from main import check_auth, check_details_help, ensure_rsi_supported, resolve_ticker_for_command
from core.parsers import (
    parse_exchange_and_ticker, is_exchange_token, parse_number, validate_max_order,
    parse_rsi_range, interpolate_range, get_user_rsi_interval, get_dca_weights,
    exchange_display_name, is_us_stock_ticker,
)
from core.formatters import build_grid_preview_lines, build_rsi_preview_lines
from core.order_execution import execute_grid_orders, execute_rsitrade_orders, execute_sgridrsi_orders
from core.strategy_tokens import create_strategy_token, pop_valid_strategy_token, discard_strategy_token
from core import trading_gate


async def build_rsi_price_points(user_id, user, exchange, ticker, buy_rsi_range, count):
    b_start, b_end = parse_rsi_range(buy_rsi_range)
    points = []
    for i in range(int(count)):
        target_rsi = interpolate_range(b_start, b_end, i, int(count))
        price = await main.signal_engine.get_price_by_rsi(
            exchange,
            ticker,
            target_rsi,
            side="bid",
            interval=get_user_rsi_interval(user),
            user_id=user_id,
        )
        if price:
            points.append((target_rsi, price))
    return points


async def build_rsi_sell_price_points(user_id, user, exchange, ticker, sell_rsi_range, count):
    s_start, s_end = parse_rsi_range(sell_rsi_range)
    points = []
    for i in range(int(count)):
        target_rsi = interpolate_range(s_start, s_end, i, int(count))
        price = await main.signal_engine.get_price_by_rsi(
            exchange,
            ticker,
            target_rsi,
            side="ask",
            interval=get_user_rsi_interval(user),
            user_id=user_id,
        )
        if price:
            points.append((target_rsi, price))
    return points


async def build_rsigrid_confirm_summary(user_id, user, intent):
    action = intent.get("action")
    exchange = intent.get("exchange") or user.get("preferences", {}).get("default_exchange", "upbit")
    _, ticker = parse_exchange_and_ticker([exchange, intent.get("ticker")] if intent.get("ticker") else [exchange], exchange)
    count = int(intent.get("count") or user["preferences"].get("rsi_order_count", 5))
    budget = float(intent.get("amount_krw") or user["preferences"].get("rsi_budget_krw") or 0)
    if not ticker or budget <= 0 or count <= 0:
        return None

    is_usd = is_us_stock_ticker(exchange, ticker)
    budget_text = f"${budget:,.2f}" if is_usd else f"{budget:,.0f}원"

    if action == "sgridrsi":
        sell_range = intent.get("sell_rsi_range") or user["preferences"].get("rsi_sell_range", "65-75")
        rsi_prices = await build_rsi_sell_price_points(user_id, user, exchange, ticker, sell_range, count)
        if not rsi_prices:
            return None
        preview_text = "\n".join(build_rsi_preview_lines(ticker, rsi_prices, budget, count, is_usd=is_usd))
        return (
            f"💰 RSI 매도 전략 확인\n\n"
            f"전략 설정\n"
            f"- 거래소: {exchange_display_name(exchange)}\n"
            f"- 종목: {ticker}\n"
            f"- 매도 RSI: {sell_range}\n"
            f"- 총예산: {budget_text}\n"
            f"- 분할: {count}개\n\n"
            f"예상 주문\n{preview_text}\n\n"
            f"실행 시점에 가격은 다시 계산될 수 있습니다.\n"
            f"위 내용으로 실행할까요?"
        )

    buy_range = intent.get("buy_rsi_range") or user["preferences"].get("rsi_buy_range", "25-30")
    sell_range = intent.get("sell_rsi_range") or user["preferences"].get("rsi_sell_range", "65-75")
    rsi_prices = await build_rsi_price_points(user_id, user, exchange, ticker, buy_range, count)
    if not rsi_prices:
        return None
    dca_mode = bool(intent.get("dca_mode"))
    per_order_budgets = [budget * w for w in get_dca_weights(count)][:len(rsi_prices)] if dca_mode else None
    preview_text = "\n".join(build_rsi_preview_lines(ticker, rsi_prices, budget, count, per_order_budgets=per_order_budgets, is_usd=is_usd))
    dca_line = "- 배분: DCA 가중 (낮은 RSI 집중)\n" if dca_mode else ""
    return (
        f"🤖 RSI 거미줄 전략 확인\n\n"
        f"전략 설정\n"
        f"- 거래소: {exchange_display_name(exchange)}\n"
        f"- 종목: {ticker}\n"
        f"- 매수 RSI: {buy_range}\n"
        f"- 매도 RSI: {sell_range}\n"
        f"- 총예산: {budget_text}\n"
        f"- 분할: {count}개\n"
        f"{dca_line}\n"
        f"예상 주문\n{preview_text}\n\n"
        f"실행 시점에 가격은 다시 계산될 수 있습니다.\n"
        f"위 내용으로 실행할까요?"
    )


# --- /grid: 거미줄 매수 핸들러 (Confirm 로직 포함) ---
@check_auth
async def grid_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "grid"): return
    ok, halt_msg = trading_gate.assert_can_trade()
    if not ok:
        await update.message.reply_text(halt_msg)
        return
    args = context.args
    if len(args) < 5:
        await update.message.reply_text(
            "⚠️ 사용법 부족\n구문: /grid [거래소] [종목] [시작가] [종료가] [개수] [총예산]"
        )
        return

    user_id = str(update.effective_chat.id)
    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = await resolve_ticker_for_command(
        update, user_id, args, default_exchange, "/grid kis 000250 50000 60000 5 100만"
    )
    if ticker is None:
        return

    # args 인덱스 보정 (거래소 명시 여부에 따라 파라미터 위치가 다름)
    offset = 2 if is_exchange_token(args[0], exchange) else 1

    try:
        start_p, end_p = parse_number(args[offset]), parse_number(args[offset+1])
        count, budget = int(args[offset+2]), parse_number(args[offset+3])
        if count <= 0:
            raise ValueError
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ 숫자 형식의 파라미터가 잘못되었습니다.")
        return

    is_usd = is_us_stock_ticker(exchange, ticker)
    ok, error_msg = validate_max_order(user, budget / count, is_usd=is_usd)
    if not ok:
        await update.message.reply_text(error_msg)
        return

    # KIS: 최소 수량 사전 안내
    kis_notice = ""
    if exchange == "kis":
        mid_price = (start_p + end_p) / 2
        if mid_price > 0 and int((budget / count) / mid_price) < 1:
            await update.message.reply_text("⚠️ 예산 대비 가격이 높아 주문당 수량이 0주가 됩니다. 예산을 늘리거나 주문 개수를 줄여주세요.")
            return
        kis_notice = "\n⚠️ 한국투자증권: 주문 수량은 정수(주)로 처리됩니다."

    token = create_strategy_token(user_id, "gridrun", {
        "exchange": exchange, "ticker": ticker,
        "start_p": start_p, "end_p": end_p, "count": count, "budget": budget,
    })
    keyboard = [
        [InlineKeyboardButton("✅ 주문 실행", callback_data=f"gridrun|{token}"),
         InlineKeyboardButton("❌ 취소", callback_data=f"grid_cancel|{token}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    preview_text = "\n".join(build_grid_preview_lines(ticker, start_p, end_p, count, budget, is_usd=is_usd))
    price_range_text = f"${start_p:,.2f} ~ ${end_p:,.2f}" if is_usd else f"{start_p:,.0f} ~ {end_p:,.0f}"
    budget_text = f"${budget:,.2f}" if is_usd else f"{budget:,.0f}원"
    summary = (
        f"🕸️ 거미줄 매수 주문 확인\n\n"
        f"주문 설정\n"
        f"- 거래소: {exchange.upper()}\n"
        f"- 종목: {ticker}\n"
        f"- 가격 범위: {price_range_text}\n"
        f"- 주문 개수: {count}회\n"
        f"- 총 예산: {budget_text}\n\n"
        "위 내용으로 주문을 진행할까요?"
        f"{kis_notice}"
    )
    summary += f"\n\n예상 주문\n{preview_text}"
    await update.message.reply_text(summary, reply_markup=reply_markup)


@check_auth
async def sgrid_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "sgrid"): return
    ok, halt_msg = trading_gate.assert_can_trade()
    if not ok:
        await update.message.reply_text(halt_msg)
        return
    args = context.args
    if len(args) < 5:
        await update.message.reply_text(
            "⚠️ 사용법 부족\n구문: /sgrid [거래소] [종목] [시작가] [종료가] [개수] [총수량]"
        )
        return

    user_id = str(update.effective_chat.id)
    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = await resolve_ticker_for_command(
        update, user_id, args, default_exchange, "/sgrid kis 000250 50000 60000 5 10"
    )
    if ticker is None:
        return
    offset = 2 if is_exchange_token(args[0], exchange) else 1

    try:
        start_p, end_p = parse_number(args[offset]), parse_number(args[offset+1])
        count, total_vol = int(args[offset+2]), parse_number(args[offset+3])
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ 숫자 형식의 파라미터가 잘못되었습니다.")
        return

    # KIS: 최소 수량 확인
    kis_notice = ""
    if exchange == "kis":
        if int(total_vol) < count:
            await update.message.reply_text(f"⚠️ 총 수량({int(total_vol)}주)이 주문 개수({count})보다 작아 주문당 수량이 0주가 됩니다.")
            return
        kis_notice = "\n⚠️ 한국투자증권: 주문 수량은 정수(주)로 처리됩니다."

    is_usd = is_us_stock_ticker(exchange, ticker)
    vol_text = f"{int(total_vol):,}주" if exchange in ("kis", "toss") else f"{total_vol:.4f}개"
    token = create_strategy_token(user_id, "sgridrun", {
        "exchange": exchange, "ticker": ticker,
        "start_p": start_p, "end_p": end_p, "count": count, "total_vol": total_vol,
    })
    keyboard = [
        [InlineKeyboardButton("✅ 매도 실행", callback_data=f"sgridrun|{token}"),
         InlineKeyboardButton("❌ 취소", callback_data=f"grid_cancel|{token}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    price_range_text = f"${start_p:,.2f} ~ ${end_p:,.2f}" if is_usd else f"{start_p:,.0f} ~ {end_p:,.0f}"
    summary = (
        f"🕸️ 거미줄 매도 주문 확인\n\n"
        f"주문 설정\n"
        f"- 거래소: {exchange.upper()}\n"
        f"- 종목: {ticker}\n"
        f"- 가격 범위: {price_range_text}\n"
        f"- 주문 개수: {count}회\n"
        f"- 총 수량: {vol_text}\n\n"
        "위 내용으로 분할 매도를 진행할까요?"
        f"{kis_notice}"
    )
    await update.message.reply_text(summary, reply_markup=reply_markup)


async def grid_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data.split("|", 1)[0]
    token = query.data.split("|", 1)[1] if "|" in query.data else None

    if action == "grid_cancel":
        discard_strategy_token(token)
        await query.edit_message_text("❌ 주문이 취소되었습니다.")
        return

    if action in ("gridrun", "sgridrun"):
        is_sell = action == "sgridrun"
        user_id = str(query.from_user.id)
        payload, error = pop_valid_strategy_token(token, user_id)
        if error:
            await query.edit_message_text(f"⚠️ {error}")
            return
        ex, tk = payload["exchange"], payload["ticker"]
        s_p, e_p, ct = float(payload["start_p"]), float(payload["end_p"]), int(payload["count"])
        val = float(payload["total_vol"]) if is_sell else float(payload["budget"])
        user = main.user_manager.get_user(user_id)
        if not user:
            await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
            return
        if not is_sell:
            ok, error_msg = validate_max_order(user, val / ct, is_usd=is_us_stock_ticker(ex, tk))
            if not ok:
                await query.edit_message_text(error_msg)
                return
            gate_ok, gate_msg = trading_gate.check_can_place_order(
                user, main.order_manager.get_user_orders(user_id), val,
                is_usd=is_us_stock_ticker(ex, tk),
            )
            if not gate_ok:
                await query.edit_message_text(gate_msg)
                return
        else:
            gate_ok, gate_msg = trading_gate.assert_can_trade()
            if not gate_ok:
                await query.edit_message_text(gate_msg)
                return

        action_name = "매도" if is_sell else "매수"
        await query.edit_message_text(f"🚀 {ex.upper()}에 거미줄 {action_name} 주문 전송을 시작합니다...")

        group_no = main.order_manager.get_next_group_no(user_id)
        await execute_grid_orders(
            exchange_adapter=main.exchange_adapter, order_manager=main.order_manager,
            user_id=user_id, exchange=ex, ticker=tk,
            start_price=s_p, end_price=e_p, count=ct, budget_or_volume=val,
            is_sell=is_sell, group_no=group_no,
            bot=context.bot, notify_chat_id=user_id,
            trigger_sync_fn=main.trigger_realtime_sync,
        )


async def grid_quick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, exchange, ticker = query.data.split("_", 3)
    await query.edit_message_text(
        f"🕸️ 거미줄 설정 안내\n\n"
        f"- 거래소: {exchange_display_name(exchange)}\n"
        f"- 종목: {ticker}\n\n"
        f"예: /grid {exchange} {ticker} [시작가] [종료가] [횟수] [예산]\n"
        f"또는 RSI 전략은 /rsitrade {exchange} {ticker} [매수RSI] [매도RSI] [횟수] [예산]"
    )


@check_auth
async def rsitrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """RSI 기반 자동 순환 매매 설정"""
    if await check_details_help(update, "rsitrade"): return
    ok, halt_msg = trading_gate.assert_can_trade()
    if not ok:
        await update.message.reply_text(halt_msg)
        return
    raw_args = context.args
    if not raw_args:
        await update.message.reply_text("⚠️ 사용법: /rsitrade [거래소] [종목] [매수RSI구간] [매도RSI구간] [횟수] [예산]\n예: /rsitrade BTC 25-30 65-75 5 100만")
        return

    dca_mode = any(a in ("-dca", "-max") for a in raw_args)
    args = [a for a in raw_args if a not in ("-dca", "-max")]
    if not args:
        await update.message.reply_text("⚠️ 사용법: /rsitrade [거래소] [종목] [매수RSI구간] [매도RSI구간] [횟수] [예산]\n예: /rsitrade BTC 25-30 65-75 5 100만")
        return

    user_id = str(update.effective_chat.id)
    default_exchange = user["preferences"].get("default_exchange", "upbit")
    _, raw_ticker = parse_exchange_and_ticker(args, default_exchange)
    if not raw_ticker:
        await update.message.reply_text("⚠️ 종목은 반드시 입력해야 합니다. 예: /rsitrade BTC")
        return
    exchange, ticker = await resolve_ticker_for_command(
        update, user_id, args, default_exchange, "/rsitrade kis 000250"
    )
    if ticker is None:
        return
    if not await ensure_rsi_supported(update, user, exchange):
        return

    offset = 2 if is_exchange_token(args[0], exchange) else 1

    try:
        preferences = user["preferences"]
        buy_rsi_range = args[offset] if len(args) > offset else preferences.get("rsi_buy_range", "25-30")
        _sell_arg = args[offset+1] if len(args) > offset + 1 else None
        sell_rsi_range = None if _sell_arg in ("-", "없음", "none") else (_sell_arg or preferences.get("rsi_sell_range", "65-75"))
        count = int(args[offset+2]) if len(args) > offset + 2 else int(preferences.get("rsi_order_count", 5))
        budget = parse_number(args[offset+3]) if len(args) > offset + 3 else preferences.get("rsi_budget_krw")
        if budget is None:
            await update.message.reply_text(
                "⚠️ RSI 전략 예산이 필요합니다. 명령어에 예산을 입력하거나 /config set rsi_budget_krw 100만으로 기본 예산을 저장하세요."
            )
            return
        budget = float(budget)

        b_start, b_end = parse_rsi_range(buy_rsi_range)
        if sell_rsi_range:
            parse_rsi_range(sell_rsi_range)
        if count <= 0:
            raise ValueError
    except (ValueError, TypeError, IndexError):
        await update.message.reply_text("⚠️ 파라미터 형식이 잘못되었습니다. (예: 25-30)")
        return

    is_usd = is_us_stock_ticker(exchange, ticker)
    dca_weights = get_dca_weights(count) if dca_mode else None
    per_order_budgets = [budget * w for w in dca_weights] if dca_weights else None
    max_per_order = max(per_order_budgets) if per_order_budgets else budget / count
    min_per_order = min(per_order_budgets) if per_order_budgets else budget / count

    ok, error_msg = validate_max_order(user, max_per_order, is_usd=is_usd)
    if not ok:
        await update.message.reply_text(error_msg)
        return

    # 1. 거래소 최소 주문 금액 검증
    min_amt = main.exchange_adapter.get_min_order_amount(exchange)
    if min_per_order < min_amt:
        unit = "달러" if is_usd else "원"
        await update.message.reply_text(f"❌ 예산이 너무 적습니다. 건당 최소 {min_amt:,.0f}{unit} 이상이어야 합니다.")
        return

    status_msg = await update.message.reply_text(f"🔍 {ticker} RSI 가격 분석 중...")

    # 2. RSI 구간별 가격 역산
    buy_prices = []
    rsi_step = (b_end - b_start) / (count - 1) if count > 1 else 0
    for i in range(count):
        target_rsi = b_start + (rsi_step * i)
        p = await main.signal_engine.get_price_by_rsi(
            exchange,
            ticker,
            target_rsi,
            side="bid",
            interval=get_user_rsi_interval(user),
            user_id=user_id,
        )
        if p: buy_prices.append((target_rsi, p))

    if not buy_prices:
        await status_msg.edit_text("❌ RSI 가격 역산에 실패했습니다. 데이터를 불러올 수 없습니다.")
        return

    # 3. 요약 및 확인 버튼
    token = create_strategy_token(user_id, "rsitrun", {
        "exchange": exchange, "ticker": ticker,
        "buy_rsi_range": buy_rsi_range, "sell_rsi_range": sell_rsi_range or "-",
        "count": count, "budget": budget, "dca_mode": dca_mode,
    })
    keyboard = [[InlineKeyboardButton("✅ 전략 가동 시작", callback_data=f"rsitrun|{token}"),
                 InlineKeyboardButton("❌ 취소", callback_data=f"grid_cancel|{token}")]]

    preview_budgets = per_order_budgets[:len(buy_prices)] if per_order_budgets else None
    preview_text = "\n".join(build_rsi_preview_lines(ticker, buy_prices, budget, count, per_order_budgets=preview_budgets, is_usd=is_usd))
    sell_line = f"- 익절(RSI): {sell_rsi_range} 목표\n" if sell_rsi_range else "- 익절 예약: 없음 (매수만)\n"
    dca_line = "- 배분: DCA 가중 (낮은 RSI 집중)\n" if dca_mode else ""
    auto_sell_note = "체결 시 자동으로 익절 주문이 예약됩니다. 시작할까요?" if sell_rsi_range else "매수만 진행합니다. 시작할까요?"
    price_range_text = f"${buy_prices[0][1]:,.2f} ~ ${buy_prices[-1][1]:,.2f}" if is_usd else f"{buy_prices[0][1]:,.0f} ~ {buy_prices[-1][1]:,.0f}원"
    budget_text = f"${budget:,.2f}" if is_usd else f"{budget:,.0f}원"
    summary = (
        f"🤖 RSI 순환 매매 전략 확인\n\n"
        f"전략 설정\n"
        f"- 거래소: {exchange.upper()}\n"
        f"- 종목: {ticker}\n"
        f"- 매집(RSI): {buy_rsi_range} ({price_range_text})\n"
        f"{sell_line}"
        f"{dca_line}"
        f"- 분할: {count}회 | 총예산: {budget_text}\n\n"
        f"{auto_sell_note}"
    )
    summary += f"\n\n예상 주문\n{preview_text}\n\n실행 시점에 가격은 다시 계산될 수 있습니다."
    await status_msg.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))


async def rsitrade_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    token = query.data.split("|", 1)[1] if "|" in query.data else None
    payload, error = pop_valid_strategy_token(token, user_id)
    if error:
        await query.edit_message_text(f"⚠️ {error}")
        return
    ex, tk = payload["exchange"], payload["ticker"]
    b_rsi, s_rsi = payload["buy_rsi_range"], payload["sell_rsi_range"]
    dca_mode = bool(payload.get("dca_mode"))
    ct, bg = int(payload["count"]), float(payload["budget"])
    user = main.user_manager.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
        return
    if not main.exchange_adapter.get_exchange(ex).supports_minute_candles() and get_user_rsi_interval(user) != "day":
        await query.edit_message_text(main._KIS_RSI_MINUTE_ERROR)
        return

    dca_weights = get_dca_weights(ct) if dca_mode else None
    per_order_budgets = [bg * w for w in dca_weights] if dca_weights else [bg / ct] * ct
    ok, error_msg = validate_max_order(user, max(per_order_budgets), is_usd=is_us_stock_ticker(ex, tk))
    if not ok:
        await query.edit_message_text(error_msg)
        return
    gate_ok, gate_msg = trading_gate.check_can_place_order(
        user, main.order_manager.get_user_orders(user_id), bg, is_usd=is_us_stock_ticker(ex, tk),
    )
    if not gate_ok:
        await query.edit_message_text(gate_msg)
        return

    await query.edit_message_text(f"🚀 {tk} RSI 순환 매매를 시작합니다. 매수 주문 전송 중...")

    group_no = main.order_manager.get_next_group_no(user_id)
    await execute_rsitrade_orders(
        exchange_adapter=main.exchange_adapter, order_manager=main.order_manager, signal_engine=main.signal_engine,
        user_id=user_id, exchange=ex, ticker=tk,
        buy_rsi_range=b_rsi, sell_rsi_range=s_rsi,
        count=ct, per_order_budgets=per_order_budgets,
        user=user, group_no=group_no, bot=context.bot, notify_chat_id=user_id,
        trigger_sync_fn=main.trigger_realtime_sync,
    )


@check_auth
async def sgridrsi_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """RSI 목표 구간 분할 매도 — 보유 코인을 RSI 가격에서 직접 매도"""
    if await check_details_help(update, "sgridrsi"): return
    ok, halt_msg = trading_gate.assert_can_trade()
    if not ok:
        await update.message.reply_text(halt_msg)
        return
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 사용법: /sgridrsi [거래소] [종목] [RSI구간] [횟수] [예산]\n예: /sgridrsi 빗썸 ETH 80-90 10 100만")
        return

    user_id = str(update.effective_chat.id)
    default_exchange = user["preferences"].get("default_exchange", "upbit")
    _, raw_ticker = parse_exchange_and_ticker(args, default_exchange)
    if not raw_ticker:
        await update.message.reply_text("⚠️ 종목은 반드시 입력해야 합니다. 예: /sgridrsi ETH")
        return
    exchange, ticker = await resolve_ticker_for_command(
        update, user_id, args, default_exchange, "/sgridrsi kis 000250"
    )
    if ticker is None:
        return
    if not await ensure_rsi_supported(update, user, exchange):
        return

    offset = 2 if is_exchange_token(args[0], exchange) else 1

    try:
        preferences = user["preferences"]
        sell_rsi_range = args[offset] if len(args) > offset else preferences.get("rsi_sell_range", "65-75")
        count = int(args[offset+1]) if len(args) > offset + 1 else int(preferences.get("rsi_order_count", 5))
        budget = parse_number(args[offset+2]) if len(args) > offset + 2 else preferences.get("rsi_budget_krw")
        if budget is None:
            await update.message.reply_text(
                "⚠️ RSI 매도 전략 예산이 필요합니다. 명령어에 예산을 입력하거나 /config set rsi_budget_krw 100만으로 기본 예산을 저장하세요."
            )
            return
        budget = float(budget)
        s_start, s_end = parse_rsi_range(sell_rsi_range)
        if count <= 0:
            raise ValueError
    except (ValueError, TypeError, IndexError):
        await update.message.reply_text("⚠️ 파라미터 형식이 잘못되었습니다. (예: 80-90)")
        return

    is_usd = is_us_stock_ticker(exchange, ticker)
    ok, error_msg = validate_max_order(user, budget / count, is_usd=is_usd)
    if not ok:
        await update.message.reply_text(error_msg)
        return

    min_amt = main.exchange_adapter.get_min_order_amount(exchange)
    if (budget / count) < min_amt:
        unit = "달러" if is_usd else "원"
        await update.message.reply_text(f"❌ 예산이 너무 적습니다. 건당 최소 {min_amt:,.0f}{unit} 이상이어야 합니다.")
        return

    status_msg = await update.message.reply_text(f"🔍 {ticker} RSI 매도 가격 분석 중...")

    sell_prices = []
    rsi_step = (s_end - s_start) / (count - 1) if count > 1 else 0
    for i in range(count):
        target_rsi = s_start + (rsi_step * i)
        p = await main.signal_engine.get_price_by_rsi(
            exchange, ticker, target_rsi, side="ask",
            interval=get_user_rsi_interval(user), user_id=user_id,
        )
        if p: sell_prices.append((target_rsi, p))

    if not sell_prices:
        await status_msg.edit_text("❌ RSI 가격 역산에 실패했습니다. 데이터를 불러올 수 없습니다.")
        return

    token = create_strategy_token(user_id, "sgridrsirun", {
        "exchange": exchange, "ticker": ticker,
        "sell_rsi_range": sell_rsi_range, "count": count, "budget": budget,
    })
    keyboard = [[InlineKeyboardButton("✅ 매도 전략 가동", callback_data=f"sgridrsirun|{token}"),
                 InlineKeyboardButton("❌ 취소", callback_data=f"grid_cancel|{token}")]]

    preview_text = "\n".join(build_rsi_preview_lines(ticker, sell_prices, budget, count, is_usd=is_usd))
    price_range_text = f"${sell_prices[0][1]:,.2f} ~ ${sell_prices[-1][1]:,.2f}" if is_usd else f"{sell_prices[0][1]:,.0f} ~ {sell_prices[-1][1]:,.0f}원"
    budget_text = f"${budget:,.2f}" if is_usd else f"{budget:,.0f}원"
    summary = (
        f"💰 RSI 매도 전략 확인\n\n"
        f"전략 설정\n"
        f"- 거래소: {exchange.upper()}\n"
        f"- 종목: {ticker}\n"
        f"- 매도(RSI): {sell_rsi_range} ({price_range_text})\n"
        f"- 분할: {count}회 | 총예산: {budget_text}\n\n"
        "보유 코인을 RSI 목표가에서 분할 매도합니다. 시작할까요?"
    )
    summary += f"\n\n예상 주문\n{preview_text}\n\n실행 시점에 가격은 다시 계산될 수 있습니다."
    await status_msg.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))


async def sgridrsi_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    token = query.data.split("|", 1)[1] if "|" in query.data else None
    payload, error = pop_valid_strategy_token(token, user_id)
    if error:
        await query.edit_message_text(f"⚠️ {error}")
        return
    ex, tk = payload["exchange"], payload["ticker"]
    s_rsi = payload["sell_rsi_range"]
    ct, bg = int(payload["count"]), float(payload["budget"])
    user = main.user_manager.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
        return
    if not main.exchange_adapter.get_exchange(ex).supports_minute_candles() and get_user_rsi_interval(user) != "day":
        await query.edit_message_text(main._KIS_RSI_MINUTE_ERROR)
        return
    ok, error_msg = validate_max_order(user, bg / ct, is_usd=is_us_stock_ticker(ex, tk))
    if not ok:
        await query.edit_message_text(error_msg)
        return
    gate_ok, gate_msg = trading_gate.assert_can_trade()
    if not gate_ok:
        await query.edit_message_text(gate_msg)
        return

    await query.edit_message_text(f"🚀 {tk} RSI 매도 전략을 시작합니다. 매도 주문 전송 중...")

    group_no = main.order_manager.get_next_group_no(user_id)
    await execute_sgridrsi_orders(
        exchange_adapter=main.exchange_adapter, order_manager=main.order_manager, signal_engine=main.signal_engine,
        user_id=user_id, exchange=ex, ticker=tk,
        sell_rsi_range=s_rsi, count=ct, budget=bg,
        user=user, group_no=group_no, bot=context.bot, notify_chat_id=user_id,
        trigger_sync_fn=main.trigger_realtime_sync,
    )


async def signal_snooze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime, timedelta, timezone
    query = update.callback_query
    await query.answer()
    # data: "signal_snooze_{mode}_{exchange}_{ticker}"
    parts = query.data.split("_", 4)
    mode, exchange, ticker = parts[2], parts[3], parts[4]
    user_id = str(query.from_user.id)
    expires = main.signal_engine.set_snooze(user_id, exchange, ticker, mode)
    label = {"1h": "1시간", "2h": "2시간", "day": "오늘 하루"}.get(mode, mode)
    kst = timezone(timedelta(hours=9))
    exp_str = datetime.fromtimestamp(expires, tz=kst).strftime("%H:%M")
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"🔕 {exchange.upper()} {ticker} 알람을 {label}({exp_str}까지) 스누즈했습니다.",
    )


# --- /dca, /sdca: 정기 매수/매도(DCA) 전략 핸들러 ---

_SIDE_ALIASES = {
    "매수": "bid", "buy": "bid", "bid": "bid",
    "매도": "ask", "sell": "ask", "ask": "ask",
}


def _format_dca_amount_text(exchange: str, ticker: str, amount_type: str, amount: float) -> str:
    is_usd = is_us_stock_ticker(exchange, ticker)
    if amount_type == "volume":
        if exchange in ("kis", "toss"):
            return f"{int(amount):,}주"
        return f"{amount:g}개"
    if is_usd:
        return f"${amount:,.2f}"
    return f"{amount:,.0f}원"


def build_dca_list_message(user_id: str, cash_reports: list[dict] | None = None) -> tuple[str, InlineKeyboardMarkup | None]:
    from datetime import datetime
    from core.parsers import KST
    from core.dca_manager import format_dca_schedule, format_cash_health_section

    dca_mgr = getattr(main, "dca_manager", None)
    schedules = dca_mgr.get_user_schedules(user_id, active_only=True) if dca_mgr else []
    if not schedules:
        msg = (
            "📅 <b>등록된 정기 매수/매도 전략이 없습니다.</b>\n\n"
            "<b>사용 예시:</b>\n"
            "• <code>/dca BTC 매일 5만</code> (매일 09:05 5만원 매수)\n"
            "• <code>/dca 한투 005930 매주월 1주 09:10</code> (매주 월요일 1주 매수)\n"
            "• <code>/dca ETH 월수금 3만 10:00 20회</code> (월·수·금 3만원 매수, 총 20회)\n"
            "• <code>/dca 매도 BTC 매월15일 0.01개</code> (매월 15일 0.01개 매도)"
        )
        return msg, None

    lines = [f"📅 <b>가동 중인 정기 매수/매도 전략 ({len(schedules)}건)</b>\n"]
    buttons = []
    for idx, s in enumerate(schedules, start=1):
        side_str = "매수" if s.get("side") == "bid" else "매도"
        ex_str = exchange_display_name(s["exchange"])
        tk = s["ticker"]
        sched_str = format_dca_schedule(s)
        amt_str = _format_dca_amount_text(s["exchange"], tk, s.get("amount_type", "budget"), float(s["amount"]))
        run_cnt = int(s.get("run_count") or 0)
        max_runs = s.get("max_runs")
        run_str = f"{run_cnt}/{max_runs}회" if max_runs else f"누적 {run_cnt}회 (무기한)"
        next_ts = float(s.get("next_run_at") or 0)
        next_str = datetime.fromtimestamp(next_ts, tz=KST).strftime("%Y-%m-%d %H:%M") if next_ts > 0 else "-"
        gno = s.get("group_no")
        group_tag = f" [<b>#{gno}</b>]" if gno else ""

        lines.append(
            f"<b>{idx}. [{ex_str}] {tk} ({side_str})</b>{group_tag}  <code>{s['id']}</code>\n"
            f"  ├ 주기: {sched_str}\n"
            f"  ├ 1회 규모: {amt_str} | 진행: {run_str}\n"
            f"  └ 다음 실행: {next_str} (KST)"
        )
        btn_tag = f"#{gno}" if gno else f"{idx}번"
        buttons.append([
            InlineKeyboardButton(
                f"🛑 {btn_tag} 중지 ({tk} {side_str})",
                callback_data=f"dcadel|{s['id']}",
            )
        ])

    if cash_reports:
        lines.append("\n" + format_cash_health_section(cash_reports, html=True))

    lines.append("\n💡 중지 명령어: <code>/dca stop [#배치번호 또는 ID]</code> | 배치 리포트: <code>/report #[번호]</code>")
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def build_dca_confirm_summary(payload: dict) -> str:
    from datetime import datetime
    from core.parsers import KST
    from core.dca_manager import format_dca_schedule, compute_next_run_at

    exchange = payload["exchange"]
    ticker = payload["ticker"]
    side = payload["side"]
    action_label = "매수" if side == "bid" else "매도"
    sched_text = format_dca_schedule(payload)
    amt_type = payload["amount_type"]
    amt_label = "1회 수량" if amt_type == "volume" else "1회 예산"
    amt_text = _format_dca_amount_text(exchange, ticker, amt_type, float(payload["amount"]))
    max_runs = payload.get("max_runs")
    runs_text = f"총 {max_runs}회 실행 후 자동 종료" if max_runs else "무기한 반복 (수동 중지 전까지)"
    next_ts = compute_next_run_at(
        frequency=payload["frequency"],
        exec_time=payload["exec_time"],
        days_of_week=payload.get("days_of_week"),
        day_of_month=payload.get("day_of_month"),
    )
    next_dt_str = datetime.fromtimestamp(next_ts, tz=KST).strftime("%Y-%m-%d %H:%M")

    market_note = ""
    if exchange in ("kis", "toss"):
        market_note = "\nℹ️ 주식 휴장일·장외 시간 도래 시 다음 정규장 개장 시각에 자동 실행됩니다."

    return (
        f"📅 정기 {action_label} 전략 확인\n\n"
        f"전략 설정\n"
        f"- 거래소: {exchange_display_name(exchange)}\n"
        f"- 종목: {ticker}\n"
        f"- 구분: 정기 {action_label}\n"
        f"- 주기: {sched_text}\n"
        f"- {amt_label}: {amt_text}\n"
        f"- 주문 방식: 실행 시점 현재가 기준 지정가 (슬리피지 버퍼 적용)\n"
        f"- 반복 조건: {runs_text}\n"
        f"- 첫 실행 예정: {next_dt_str} (KST)"
        f"{market_note}\n\n"
        f"위 내용으로 정기 {action_label} 전략을 등록할까요?"
    )


async def _handle_dca_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user, default_side: str = "bid"):
    from core.dca_manager import (
        DEFAULT_DCA_EXEC_TIME,
        parse_dca_schedule,
        parse_dca_amount,
        parse_dca_time,
        parse_dca_max_runs,
        is_dca_time_token,
        is_dca_max_runs_token,
    )

    user_id = str(update.effective_chat.id)
    args = list(context.args or [])

    # 1. 인자가 없거나 list 조회인 경우
    if not args or args[0].lower() in ("list", "목록", "조회", "status"):
        from core.dca_manager import analyze_user_cash_sufficiency
        dca_mgr = getattr(main, "dca_manager", None)
        cash_reports = await analyze_user_cash_sufficiency(
            user_id, dca_mgr, getattr(main, "order_manager", None), getattr(main, "exchange_adapter", None)
        )
        msg, markup = build_dca_list_message(user_id, cash_reports=cash_reports)
        await update.message.reply_text(msg, reply_markup=markup, parse_mode="HTML")
        return

    # 2. 중지/삭제 명령 처리 (/dca stop [id|번호], /dca clear)
    sub = args[0].lower()
    if sub in ("stop", "del", "delete", "cancel", "remove", "중지", "삭제", "취소"):
        if len(args) < 2:
            await update.message.reply_text("⚠️ 중지할 정기 전략 ID 또는 번호를 입력해 주세요. 예: `/dca stop 1`")
            return
        target_token = args[1].strip()
        dca_mgr = getattr(main, "dca_manager", None)
        if not dca_mgr:
            await update.message.reply_text("⚠️ 정기 전략 관리자가 초기화되지 않았습니다.")
            return
        schedules = dca_mgr.get_user_schedules(user_id, active_only=True)
        target_id = target_token
        if target_token.startswith("#") and target_token[1:].isdigit():
            by_gno = dca_mgr.get_schedule_by_group_no(user_id, int(target_token[1:]))
            if by_gno:
                target_id = by_gno["id"]
        elif target_token.isdigit():
            by_gno = dca_mgr.get_schedule_by_group_no(user_id, int(target_token))
            idx = int(target_token) - 1
            if 0 <= idx < len(schedules):
                target_id = schedules[idx]["id"]
            elif by_gno:
                target_id = by_gno["id"]
        removed = dca_mgr.remove_schedule(target_id, user_id=user_id)
        if removed:
            await update.message.reply_text(f"🛑 정기 전략(`{target_id}`)이 중지 및 삭제되었습니다.")
        else:
            await update.message.reply_text(f"⚠️ `{target_token}`에 해당하는 정기 전략을 찾을 수 없습니다. `/dca`로 목록을 확인하세요.")
        return

    if sub in ("clear", "모두중지", "전체삭제"):
        dca_mgr = getattr(main, "dca_manager", None)
        count = dca_mgr.clear_user_schedules(user_id) if dca_mgr else 0
        await update.message.reply_text(f"🛑 총 {count}건의 정기 매수/매도 전략을 모두 중지했습니다.")
        return

    # 3. 신규 정기 전략 등록
    ok, halt_msg = trading_gate.assert_can_trade()
    if not ok:
        await update.message.reply_text(halt_msg)
        return

    # 첫 토큰이 매수/매도 방향인지 확인
    side = default_side
    if args[0].lower() in _SIDE_ALIASES:
        side = _SIDE_ALIASES[args[0].lower()]
        args = args[1:]

    if len(args) < 3:
        await update.message.reply_text(
            "⚠️ 사용법: /dca [매수|매도] [거래소] [종목] [주기] [금액|수량] [시각(선택)] [횟수(선택)]\n"
            "예시:\n"
            "• /dca BTC 매일 5만\n"
            "• /dca 한투 005930 매주월 1주 09:10\n"
            "• /dca ETH 월수금 3만 10:00 20회\n"
            "• /dca 매도 BTC 매월15일 0.01개"
        )
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = await resolve_ticker_for_command(
        update, user_id, args, default_exchange, "/dca kis 005930 매주월 1주"
    )
    if ticker is None:
        return

    offset = 2 if is_exchange_token(args[0], exchange) else 1
    rem = args[offset:]
    if len(rem) < 2:
        await update.message.reply_text(
            "⚠️ 주기와 주문 금액(또는 수량)을 모두 입력해 주세요.\n"
            "예: /dca BTC 매일 5만"
        )
        return

    raw_schedule = rem[0]
    raw_amount = rem[1]
    optional_tokens = rem[2:]

    try:
        sched_info = parse_dca_schedule(raw_schedule)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return

    try:
        amount_type, amount = parse_dca_amount(raw_amount)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return

    exec_time = DEFAULT_DCA_EXEC_TIME
    max_runs = None
    for tok in optional_tokens:
        if is_dca_time_token(tok):
            exec_time = parse_dca_time(tok)
        elif is_dca_max_runs_token(tok) or tok.isdigit():
            try:
                max_runs = parse_dca_max_runs(tok)
            except ValueError as e:
                await update.message.reply_text(f"⚠️ {e}")
                return
        else:
            await update.message.reply_text(
                f"⚠️ 알 수 없는 옵션입니다: `{tok}`\n"
                "실행 시각은 `09:05` 형식, 총 횟수는 `10회` 형식으로 입력해 주세요."
            )
            return

    ex_obj = main.exchange_adapter.get_exchange(exchange)
    is_usd = is_us_stock_ticker(exchange, ticker)

    if amount_type == "volume":
        if ex_obj.requires_integer_volume() and int(amount) < 1:
            await update.message.reply_text("⚠️ 주식 주문 수량은 최소 1주 이상이어야 합니다.")
            return
    else:
        min_amt = main.exchange_adapter.get_min_order_amount(exchange)
        if not is_usd and amount < min_amt:
            await update.message.reply_text(f"❌ 1회 예산이 너무 적습니다. 최소 {min_amt:,.0f}원 이상이어야 합니다.")
            return
        if side == "bid":
            ok, err_msg = validate_max_order(user, amount, is_usd=is_usd)
            if not ok:
                await update.message.reply_text(err_msg)
                return

    payload = {
        "exchange": exchange,
        "ticker": ticker,
        "side": side,
        "frequency": sched_info["frequency"],
        "days_of_week": sched_info["days_of_week"],
        "day_of_month": sched_info["day_of_month"],
        "exec_time": exec_time,
        "amount_type": amount_type,
        "amount": amount,
        "max_runs": max_runs,
    }
    token = create_strategy_token(user_id, "dcarun", payload)
    action_label = "매수" if side == "bid" else "매도"
    keyboard = [[
        InlineKeyboardButton(f"✅ 정기 {action_label} 시작", callback_data=f"dcarun|{token}"),
        InlineKeyboardButton("❌ 취소", callback_data=f"grid_cancel|{token}"),
    ]]
    summary = build_dca_confirm_summary(payload)
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))


@check_auth
async def dca_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """정기 매수/매도(DCA) 전략 등록 및 목록 관리"""
    if await check_details_help(update, "dca"):
        return
    await _handle_dca_command(update, context, user, default_side="bid")


@check_auth
async def sdca_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """정기 매도(SDCA) 전략 등록 단축 명령어"""
    if await check_details_help(update, "dca"):
        return
    await _handle_dca_command(update, context, user, default_side="ask")


async def dca_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime
    from core.parsers import KST
    from core.dca_manager import format_dca_schedule

    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    token = query.data.split("|", 1)[1] if "|" in query.data else None
    payload, error = pop_valid_strategy_token(token, user_id)
    if error:
        await query.edit_message_text(f"⚠️ {error}")
        return

    user = main.user_manager.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 등록을 중단합니다.")
        return

    gate_ok, gate_msg = trading_gate.assert_can_trade()
    if not gate_ok:
        await query.edit_message_text(gate_msg)
        return

    dca_mgr = getattr(main, "dca_manager", None)
    if not dca_mgr:
        await query.edit_message_text("❌ 정기 전략 관리자가 초기화되지 않았습니다.")
        return

    om = getattr(main, "order_manager", None)
    group_no = dca_mgr.get_next_group_no(user_id, order_manager=om)
    sched = dca_mgr.add_schedule(
        user_id=user_id,
        exchange=payload["exchange"],
        ticker=payload["ticker"],
        side=payload["side"],
        frequency=payload["frequency"],
        days_of_week=payload.get("days_of_week"),
        day_of_month=payload.get("day_of_month"),
        exec_time=payload["exec_time"],
        amount_type=payload["amount_type"],
        amount=float(payload["amount"]),
        max_runs=payload.get("max_runs"),
        group_no=group_no,
    )

    action_label = "매수" if sched["side"] == "bid" else "매도"
    amt_str = _format_dca_amount_text(sched["exchange"], sched["ticker"], sched["amount_type"], sched["amount"])
    next_dt = datetime.fromtimestamp(sched["next_run_at"], tz=KST).strftime("%Y-%m-%d %H:%M")
    runs_str = f"총 {sched['max_runs']}회" if sched.get("max_runs") else "무기한"

    await query.edit_message_text(
        f"✅ [{exchange_display_name(sched['exchange'])}] {sched['ticker']} 정기 {action_label} 등록 완료!\n\n"
        f"• 배치: #{sched['group_no']} (ID: {sched['id']})\n"
        f"• 주기: {format_dca_schedule(sched)}\n"
        f"• 1회 규모: {amt_str} ({runs_str})\n"
        f"• 첫 실행: {next_dt} (KST)\n\n"
        f"📋 조회 및 중지: /dca | 배치 리포트: /report #{sched['group_no']}"
    )


async def dca_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    sched_id = query.data.split("|", 1)[1] if "|" in query.data else ""
    dca_mgr = getattr(main, "dca_manager", None)
    if not dca_mgr:
        await query.edit_message_text("⚠️ 정기 전략 관리자가 초기화되지 않았습니다.")
        return

    removed = dca_mgr.remove_schedule(sched_id, user_id=user_id)
    if not removed:
        await query.edit_message_text("⚠️ 이미 삭제되었거나 존재하지 않는 전략입니다.")
        return

    msg, markup = build_dca_list_message(user_id)
    header = f"🛑 정기 전략(<code>{sched_id}</code>)을 중지했습니다.\n\n"
    await query.edit_message_text(header + msg, reply_markup=markup, parse_mode="HTML")
