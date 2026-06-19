"""조회성 커맨드 — /asset, /orders, /cancel, /cancelno, /price, /indicators, /report, /history."""
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import main
from main import check_auth, check_details_help, resolve_ticker_for_command
from core.parsers import normalize_exchange, exchange_display_name, parse_exchange_and_ticker
from core.formatters import build_report_view, build_cancel_confirm_message
from core.trade_log import read_trades


@check_auth
async def asset_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "asset"): return
    user_id = str(update.effective_chat.id)
    if context.args:
        exchange = normalize_exchange(context.args[0])
        if not exchange:
            await update.message.reply_text("⚠️ 거래소는 업비트, 빗썸, 한투, 토스증권 중 하나로 입력해 주세요.")
            return
        exchanges = [exchange]
    else:
        exchanges = ["upbit", "bithumb", "kis", "toss"]
    min_display_krw = float(user["preferences"].get("asset_min_display_krw", 10000))

    status_msg = await update.message.reply_text("🔄 자산 정보를 불러오는 중입니다...")

    full_msg = "💰 <b>통합 자산 현황</b>\n\n"
    total_eval_krw = 0

    for ex in exchanges:
        balances = await main.exchange_adapter.get_balances(user_id, ex)
        if balances is None:
            full_msg += f"❌ <b>{exchange_display_name(ex)}</b>: API 키가 설정되지 않았거나 오류 발생\n\n"
            continue

        if ex in ("kis", "toss"):
            env_label = f" ({'실전' if balances.get('env') == 'real' else '모의'})" if ex == "kis" else ""
            full_msg += f"🏛️ <b>{exchange_display_name(ex)}</b>{env_label}\n"
            cash = float(balances.get("cash", 0))
            ex_eval = float(balances.get("total_eval", 0))
            full_msg += f"- 💵 예수금: {cash:,.0f}원\n"

            stocks = sorted(balances.get("stocks", []), key=lambda s: float(s.get("value", 0)), reverse=True)
            top5 = stocks[:5]
            rest = stocks[5:]
            for stock in top5:
                value = float(stock.get("value", 0))
                name = stock.get('name') or stock.get('code')
                currency = stock.get("currency", "KRW")
                qty = stock.get('quantity', 0)
                if currency == "KRW":
                    full_msg += f"- 📈 {name} ({qty:,.0f}주)\n"
                    full_msg += f"   └ {value:,.0f}원\n"
                else:
                    full_msg += f"- 📈 {name} ({qty:,.2f}주, {currency})\n"
                    full_msg += f"   └ {value:,.2f} {currency}\n"
            others_count = len(rest)
            others_value = sum(float(s.get("value", 0)) for s in rest if s.get("currency", "KRW") == "KRW")
            if others_count > 0:
                full_msg += f"- 📦 기타 {others_count}개 종목: {others_value:,.0f}원\n"
            full_msg += f"   └ 계좌 평가액: {ex_eval:,.0f}원\n\n"
            total_eval_krw += ex_eval
            continue

        # 거래소별 현재가 정보 가져오기 (평가액 계산용)
        ticker_prices = await main.exchange_adapter.get_krw_ticker_prices(ex)

        full_msg += f"🏛️ <b>{ex.upper()}</b>\n"
        ex_eval = 0
        cash_krw = 0.0
        coin_items = []

        for b in balances:
            qty = float(b['balance']) + float(b['locked'])
            if qty <= 0: continue

            currency = b['currency']
            if currency == "KRW":
                ex_eval += qty
                cash_krw += qty
            else:
                price = ticker_prices.get(currency, 0)
                value = qty * price
                ex_eval += value
                coin_items.append({"currency": currency, "qty": qty, "value": value})

        full_msg += f"- 💵 KRW: {cash_krw:,.0f}원\n"

        coin_items.sort(key=lambda x: x["value"], reverse=True)
        top5 = coin_items[:5]
        rest = coin_items[5:]
        for item in top5:
            full_msg += f"- 🪙 {item['currency']} ({item['qty']:.4f}개)\n"
            if item['value'] > 0:
                full_msg += f"   └ {item['value']:,.0f}원\n"
        others_count = len(rest)
        others_value = sum(i["value"] for i in rest)
        if others_count > 0:
            full_msg += f"- 📦 기타 {others_count}개 종목: {others_value:,.0f}원\n"

        full_msg += f"   └ 거래소 평가액: {ex_eval:,.0f}원\n\n"
        total_eval_krw += ex_eval

    full_msg += f"💳 <b>총 합계 자산: {total_eval_krw:,.0f}원</b>"
    await status_msg.edit_text(full_msg, parse_mode="HTML")


@check_auth
async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "orders"): return
    user_id = str(update.effective_chat.id)
    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, _ = parse_exchange_and_ticker(context.args, default_exchange)

    orders = main.order_manager.get_user_orders(user_id, exchange)
    if not orders:
        await update.message.reply_text("⏳ 봇이 추적 중인 거래소 미체결 주문은 없습니다.\nRSI/거미줄 전략 대기 상태는 /status에서 확인하세요.")
        return

    msg = "⏳ <b>현재 추적 중인 미체결 주문</b>\n\n"
    _order_status_names = {"wait": "대기", "partial": "부분체결", "pending_reorder": "재주문대기", "market_closed": "장외대기"}
    for ord in orders:
        group_tag = f" [<b>#{ord['group_no']}</b>]" if ord.get("group_no") else ""
        side_str = "매수" if ord["side"] == "bid" else "매도"
        status_str = _order_status_names.get(ord.get("status"), "")
        status_tag = f" — {status_str}" if status_str else ""
        msg += f"📌 <b>[{exchange_display_name(ord['exchange'])}]</b> {ord['ticker']}{group_tag}\n"
        msg += f"   └ {ord['price']:,.0f}원 ({side_str}, {ord['volume']:.4f}개){status_tag}\n"

    msg += "\n배치 번호로 취소: <code>/cancelno [번호]</code>"
    await update.message.reply_text(msg, parse_mode="HTML")


@check_auth
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "cancel"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 취소할 종목을 입력하세요. 예: `/cancel BTC` 또는 `/cancel upbit BTC`")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = await resolve_ticker_for_command(update, user_id, args, default_exchange)
    if ticker is None:
        return

    orders = [o for o in main.order_manager.get_user_orders(user_id, exchange) if o['ticker'] == ticker]
    if not orders:
        await update.message.reply_text(f"ℹ️ {exchange_display_name(exchange)}에서 추적 중인 {ticker} 주문이 없습니다.")
        return

    token = main.create_cancel_token(user_id, orders)
    keyboard = [[InlineKeyboardButton("✅ 취소 확정", callback_data=f"cancelrun|{token}"),
                 InlineKeyboardButton("❌ 그대로 두기", callback_data=f"cancelabort|{token}")]]
    await update.message.reply_text(
        build_cancel_confirm_message(orders, f"{exchange_display_name(exchange)} {ticker}"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


@check_auth
async def cancelno_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "cancelno"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 취소할 배치 번호를 입력하세요. 예: <code>/cancelno 1</code>", parse_mode="HTML")
        return

    try:
        group_no = int(args[-1])
    except ValueError:
        await update.message.reply_text("⚠️ 배치 번호는 숫자여야 합니다. 예: <code>/cancelno 1</code>", parse_mode="HTML")
        return

    orders = main.order_manager.get_orders_by_group_no(user_id, group_no)
    if not orders:
        await update.message.reply_text(f"ℹ️ #{group_no} 배치 주문이 없습니다.")
        return

    token = main.create_cancel_token(user_id, orders)
    keyboard = [[InlineKeyboardButton("✅ 취소 확정", callback_data=f"cancelrun|{token}"),
                 InlineKeyboardButton("❌ 그대로 두기", callback_data=f"cancelabort|{token}")]]
    await update.message.reply_text(
        build_cancel_confirm_message(orders, f"#{group_no} 배치"),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def cancel_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, token = query.data.split("|", 1)
    if action == "cancelabort":
        main._pending_cancel_orders.pop(token, None)
        await query.edit_message_text("ℹ️ 주문을 취소하지 않았습니다.")
        return

    user_id = str(query.from_user.id)
    pending, error = main.pop_valid_cancel_token(token, user_id)
    if error:
        await query.edit_message_text(f"⚠️ {error}")
        return

    orders = pending["orders"]
    await query.edit_message_text(f"🛑 주문 {len(orders)}건 취소 중...")

    success_count = 0
    for ord in orders:
        if await main.exchange_adapter.cancel_order(user_id, ord['exchange'], ord['uuid'], ord['ticker']):
            main.order_manager.remove_order(ord['uuid'])
            success_count += 1
        await asyncio.sleep(0.1)

    await query.edit_message_text(f"✅ 취소 완료 ({success_count}/{len(orders)}건 성공)")


@check_auth
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "price"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 종목을 입력하세요. 예: /price BTC 또는 /p ETH")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, raw_ticker = parse_exchange_and_ticker(args, default_exchange)
    ticker = await main.exchange_adapter.resolve_ticker(user_id, exchange, raw_ticker)
    display_ticker = f"{raw_ticker}({ticker})" if ticker != raw_ticker else ticker

    if exchange in ("kis", "toss") and ticker and any('가' <= c <= '힣' for c in ticker):
        await update.message.reply_text(
            f"⚠️ {exchange_display_name(exchange)}은 종목코드로 입력하세요.\n예: /price {exchange} 000250"
        )
        return

    ticker_data, indicators = await asyncio.gather(
        main.exchange_adapter.get_ticker(exchange, ticker, user_id=user_id),
        main.signal_engine.get_indicators(exchange, ticker, interval="day", user_id=user_id),
        return_exceptions=True,
    )

    if isinstance(ticker_data, Exception) or not ticker_data:
        await update.message.reply_text(f"❌ {exchange_display_name(exchange)}에서 {display_ticker} 정보를 찾을 수 없습니다.")
        return
    if isinstance(indicators, Exception):
        indicators = None

    price = float(ticker_data.get('trade_price', 0))
    change_rate = float(ticker_data.get('change_rate', 0)) * 100
    change_price = float(ticker_data.get('change_price', 0))
    high = float(ticker_data.get('high_price', 0))
    low = float(ticker_data.get('low_price', 0))
    volume = float(ticker_data.get('acc_trade_price_24h', 0))
    stock_name = ticker_data.get('stock_name', '')
    currency = ticker_data.get('currency', 'KRW')
    unit = "원" if currency == "KRW" else f" {currency}"
    price_fmt = "{:,.0f}" if currency == "KRW" else "{:,.2f}"

    change_emoji = "📈" if change_rate > 0 else "📉" if change_rate < 0 else "➖"

    ticker_label = f"{stock_name} ({ticker})" if stock_name else ticker
    msg = (
        f"📊 <b>[{exchange_display_name(exchange)}] {ticker_label}</b> 실시간 시세\n\n"
        f"현재가: <b>{price_fmt.format(price)}{unit}</b> {change_emoji}\n"
        f"전일대비: {change_rate:+.2f}% ({price_fmt.format(change_price)}{unit})"
    )
    if high or low:
        msg += (
            f"\n고가(24H): {price_fmt.format(high)}{unit}\n"
            f"저가(24H): {price_fmt.format(low)}{unit}"
        )
    if volume:
        msg += f"\n거래대금: {volume/100000000:,.1f}억{unit}" if currency == "KRW" else f"\n거래대금: {volume:,.0f}{unit}"

    if indicators:
        technical_parts = []
        rsi = indicators.get("rsi")
        if rsi is not None:
            technical_parts.append(f"RSI(14): {rsi:.1f}")
        for period in [7, 14, 30, 90]:
            ma_val = indicators.get(f"ma{period}")
            if ma_val is not None:
                technical_parts.append(f"MA{period}: {price_fmt.format(ma_val)}{unit}")
        if technical_parts:
            msg += "\n\n📈 <b>기술지표 (일봉)</b>\n" + "\n".join(technical_parts)

    await update.message.reply_text(msg, parse_mode="HTML")


@check_auth
async def indicators_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "indicators"): return
    user_id = str(update.effective_chat.id)
    args = context.args or []
    if not args:
        await update.message.reply_text("⚠️ 종목을 입력하세요. 예: /indicators BTC 또는 /ind upbit KRW-BTC 60")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    # 마지막 인자가 봉기준(숫자 또는 day)이면 분리
    if len(args) >= 2 and args[-1].lower() in ("day", "1", "3", "5", "10", "15", "30", "60", "240"):
        interval = args[-1].lower()
        ticker_args = args[:-1]
    else:
        interval = user["preferences"].get("rsi_interval", "day")
        ticker_args = args

    exchange, ticker = await resolve_ticker_for_command(
        update, user_id, ticker_args, default_exchange, f"/indicators {default_exchange} 000250"
    )
    if ticker is None:
        return

    await update.message.reply_text(f"⏳ {exchange_display_name(exchange)} {ticker} 지표 계산 중...")

    result = await main.signal_engine.get_indicators(exchange, ticker, interval=interval, user_id=user_id)
    if result is None:
        await update.message.reply_text(f"❌ {exchange_display_name(exchange)}에서 {ticker} 캔들 데이터를 가져올 수 없습니다.")
        return

    rsi = result["rsi"]
    macd = result["macd"]
    bb = result["bbands"]
    stoch = result["stoch"]
    price = result["current_price"]
    used_interval = result["interval"]
    interval_label = "일봉" if used_interval == "day" else f"{used_interval}분봉"

    bb_pos = ""
    if price > bb.upper:
        bb_pos = " ▲ 상단 돌파"
    elif price < bb.lower:
        bb_pos = " ▼ 하단 이탈"

    hist_sign = "+" if macd.histogram >= 0 else ""
    msg = (
        f"📈 <b>[{exchange_display_name(exchange)}] {ticker}</b> 멀티지표 ({interval_label})\n\n"
        f"현재가: <b>{price:,.0f}원</b>\n\n"
        f"<b>RSI(14)</b>: {rsi:.2f}\n"
        f"<b>MACD(12,26,9)</b>: {macd.macd:,.0f} / Signal {macd.signal:,.0f} / Hist {hist_sign}{macd.histogram:,.0f}\n"
        f"<b>볼린저(20,2σ)</b>: 상 {bb.upper:,.0f} / 중 {bb.middle:,.0f} / 하 {bb.lower:,.0f}{bb_pos} (밴드폭 {bb.width_pct:.1f}%)\n"
        f"<b>스토캐스틱(14,3)</b>: %K {stoch.k:.1f} / %D {stoch.d:.1f}"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


@check_auth
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "report"): return
    user_id = str(update.effective_chat.id)
    args = context.args or []
    period = args[0].lower() if args else "all"
    if period not in ("today", "week", "month", "all"):
        await update.message.reply_text("⚠️ 사용법: /report [today|week|month|all]")
        return
    trades = read_trades(user_id, period)
    if not trades:
        await update.message.reply_text(
            "📊 해당 기간에 체결 기록이 없습니다.\n"
            "팁: 주문이 전량 체결되면 자동으로 기록됩니다."
        )
        return
    await update.message.reply_text(build_report_view(trades, period), parse_mode="HTML")


@check_auth
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "history"): return
    user_id = str(update.effective_chat.id)
    default_exchange = user["preferences"].get("default_exchange", "upbit")

    exchange, ticker = await resolve_ticker_for_command(update, user_id, context.args or [], default_exchange)
    if context.args and ticker is None:
        return

    history = await main.exchange_adapter.get_order_history(user_id, exchange, ticker)
    if not history:
        await update.message.reply_text(f"ℹ️ {exchange_display_name(exchange)}의 최근 체결 내역이 없습니다.")
        return

    # 상위 5건만 표시
    msg = f"📜 <b>[{exchange_display_name(exchange)}] 최근 체결 내역</b> (최근 5건)\n\n"
    for ord in history[:5]:
        side = "🔴 매수" if ord.get('side', '').lower() in ['bid', 'buy'] else "🔵 매도"
        tk = ord.get('market', ticker)
        price = float(ord.get('price', 0))
        vol = float(ord.get('volume', 0))
        date = ord.get('created_at', '').split('T')[0]

        msg += f"- {date} | {side} | {tk}\n"
        msg += f"  └ {price:,.0f}원 | {vol:.4f}개\n"

    await update.message.reply_text(msg, parse_mode="HTML")
