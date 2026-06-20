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

    # KIS: 정규장 여부 및 최소 수량 사전 안내
    kis_notice = ""
    if exchange == "kis":
        if not main.exchange_adapter.get_exchange(exchange).is_market_open():
            await update.message.reply_text("⚠️ 현재 한국투자증권 정규장 시간이 아닙니다. 정규장(평일 09:00-15:35)에만 주문이 실행됩니다.")
            return
        mid_price = (start_p + end_p) / 2
        if mid_price > 0 and int((budget / count) / mid_price) < 1:
            await update.message.reply_text("⚠️ 예산 대비 가격이 높아 주문당 수량이 0주가 됩니다. 예산을 늘리거나 주문 개수를 줄여주세요.")
            return
        kis_notice = "\n⚠️ 한국투자증권: 주문 수량은 정수(주)로 처리됩니다."

    confirm_data = f"gridrun|{exchange}|{ticker}|{start_p}|{end_p}|{count}|{budget}"
    keyboard = [
        [InlineKeyboardButton("✅ 주문 실행", callback_data=confirm_data),
         InlineKeyboardButton("❌ 취소", callback_data="grid_cancel")]
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

    # KIS: 정규장 여부 및 최소 수량 확인
    kis_notice = ""
    if exchange == "kis":
        if not main.exchange_adapter.get_exchange(exchange).is_market_open():
            await update.message.reply_text("⚠️ 현재 한국투자증권 정규장 시간이 아닙니다. 정규장(평일 09:00-15:35)에만 주문이 실행됩니다.")
            return
        if int(total_vol) < count:
            await update.message.reply_text(f"⚠️ 총 수량({int(total_vol)}주)이 주문 개수({count})보다 작아 주문당 수량이 0주가 됩니다.")
            return
        kis_notice = "\n⚠️ 한국투자증권: 주문 수량은 정수(주)로 처리됩니다."

    is_usd = is_us_stock_ticker(exchange, ticker)
    vol_text = f"{int(total_vol):,}주" if exchange in ("kis", "toss") else f"{total_vol:.4f}개"
    confirm_data = f"sgridrun|{exchange}|{ticker}|{start_p}|{end_p}|{count}|{total_vol}"
    keyboard = [
        [InlineKeyboardButton("✅ 매도 실행", callback_data=confirm_data),
         InlineKeyboardButton("❌ 취소", callback_data="grid_cancel")]
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

    if query.data == "grid_cancel":
        await query.edit_message_text("❌ 주문이 취소되었습니다.")
        return

    if query.data.startswith("gridrun") or query.data.startswith("sgridrun"):
        is_sell = query.data.startswith("sgridrun")
        _, ex, tk, s_p, e_p, ct, val = query.data.split("|")
        s_p, e_p, ct, val = float(s_p), float(e_p), int(ct), float(val)
        user_id = str(query.from_user.id)
        user = main.user_manager.get_user(user_id)
        if not user:
            await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
            return
        if not is_sell:
            ok, error_msg = validate_max_order(user, val / ct, is_usd=is_us_stock_ticker(ex, tk))
            if not ok:
                await query.edit_message_text(error_msg)
                return

        action_name = "매도" if is_sell else "매수"
        await query.edit_message_text(f"🚀 {ex.upper()}에 거미줄 {action_name} 주문 전송을 시작합니다...")

        # KIS 정규장 재확인 (confirm 시점에 다시 체크)
        if ex == "kis" and not main.exchange_adapter.get_exchange(ex).is_market_open():
            await query.edit_message_text("⚠️ 현재 한국투자증권 정규장 시간이 아닙니다. 주문을 실행할 수 없습니다.")
            return

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
    confirm_data = f"rsitrun|{exchange}|{ticker}|{buy_rsi_range}|{sell_rsi_range or '-'}|{count}|{budget}|{'1' if dca_mode else '0'}"
    keyboard = [[InlineKeyboardButton("✅ 전략 가동 시작", callback_data=confirm_data),
                 InlineKeyboardButton("❌ 취소", callback_data="grid_cancel")]]

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

    parts = query.data.split("|")
    _, ex, tk, b_rsi, s_rsi, ct, bg = parts[:7]
    dca_mode = len(parts) > 7 and parts[7] == "1"
    ct, bg = int(ct), float(bg)
    user_id = str(query.from_user.id)
    user = main.user_manager.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
        return
    if ex == "kis" and get_user_rsi_interval(user) != "day":
        await query.edit_message_text(main._KIS_RSI_MINUTE_ERROR)
        return

    dca_weights = get_dca_weights(ct) if dca_mode else None
    per_order_budgets = [bg * w for w in dca_weights] if dca_weights else [bg / ct] * ct
    ok, error_msg = validate_max_order(user, max(per_order_budgets), is_usd=is_us_stock_ticker(ex, tk))
    if not ok:
        await query.edit_message_text(error_msg)
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

    confirm_data = f"sgridrsirun|{exchange}|{ticker}|{sell_rsi_range}|{count}|{budget}"
    keyboard = [[InlineKeyboardButton("✅ 매도 전략 가동", callback_data=confirm_data),
                 InlineKeyboardButton("❌ 취소", callback_data="grid_cancel")]]

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

    _, ex, tk, s_rsi, ct, bg = query.data.split("|")
    ct, bg = int(ct), float(bg)
    user_id = str(query.from_user.id)
    user = main.user_manager.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
        return
    if ex == "kis" and get_user_rsi_interval(user) != "day":
        await query.edit_message_text(main._KIS_RSI_MINUTE_ERROR)
        return
    ok, error_msg = validate_max_order(user, bg / ct, is_usd=is_us_stock_ticker(ex, tk))
    if not ok:
        await query.edit_message_text(error_msg)
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
