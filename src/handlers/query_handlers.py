"""조회성 커맨드 — /asset, /orders, /cancel, /cancelno, /price, /indicators, /report, /history."""
import asyncio
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import main
from main import check_auth, check_details_help, resolve_ticker_for_command
from core.parsers import normalize_exchange, exchange_display_name, parse_exchange_and_ticker
from core.formatters import (
    build_cancel_confirm_message,
    build_report_view_page,
    build_timeseries_report_view_page,
)
from core.trade_log import read_trades
from core.dca_manager import analyze_user_cash_sufficiency
from handlers import list_view_handlers


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

    status_msg = await update.message.reply_text("🔄 자산 정보를 불러오는 중입니다...")

    balances_by_ex = {}
    ticker_prices_by_ex = {}
    for ex in exchanges:
        balances = await main.exchange_adapter.get_balances(user_id, ex)
        balances_by_ex[ex] = balances
        # 거래소별 현재가 정보 가져오기 (코인 평가액 계산용, KIS/토스는 불필요)
        if balances is not None and ex not in ("kis", "toss"):
            ticker_prices_by_ex[ex] = await main.exchange_adapter.get_krw_ticker_prices(ex)

    snapshot = {"exchanges": exchanges, "balances": balances_by_ex, "ticker_prices": ticker_prices_by_ex}
    token = main.create_list_view_token(user_id, "asset", {"expanded_exchanges": []}, snapshot=snapshot)
    full_msg, markup = list_view_handlers.build_asset_message(snapshot, set(), token)
    await status_msg.edit_text(full_msg, reply_markup=markup, parse_mode="HTML")


@check_auth
async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "orders"): return
    user_id = str(update.effective_chat.id)
    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange = None
    if context.args:
        exchange, _ = parse_exchange_and_ticker(context.args, default_exchange)

    orders = main.order_manager.get_user_orders(user_id) if exchange is None else main.order_manager.get_user_orders(user_id, exchange)
    if not orders:
        await update.message.reply_text("⏳ 봇이 추적 중인 거래소 미체결 주문은 없습니다.\nRSI/거미줄 전략 대기 상태는 /status에서 확인하세요.")
        return

    token = main.create_list_view_token(user_id, "orders", {"expanded": False, "exchange": exchange})
    msg, markup = list_view_handlers.build_orders_message(user_id, exchange, False, token)
    await update.message.reply_text(msg, reply_markup=markup, parse_mode="HTML")


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

    raw_no = str(args[-1]).strip().lstrip("#")
    try:
        group_no = int(raw_no)
    except ValueError:
        await update.message.reply_text("⚠️ 배치 번호는 숫자여야 합니다. 예: <code>/cancelno 1</code>", parse_mode="HTML")
        return

    orders = main.order_manager.get_orders_by_group_no(user_id, group_no)
    dca_mgr = getattr(main, "dca_manager", None)
    dca_sched = dca_mgr.get_schedule_by_group_no(user_id, group_no) if dca_mgr else None

    if not orders and dca_sched:
        dca_mgr.remove_schedule(dca_sched["id"], user_id=user_id)
        await update.message.reply_text(
            f"🛑 #{group_no} 배치 정기 전략(<code>{dca_sched['id']}</code>, {dca_sched['ticker']})을 중지했습니다.",
            parse_mode="HTML",
        )
        return

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
        if await main.cancel_and_remove_order(user_id, ord):
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
    exchange, ticker = await main.resolve_ticker_for_command(
        update, user_id, args, default_exchange, cmd_hint=f"/price {exchange} 000250"
    )
    if ticker is None:
        return
    display_ticker = f"{raw_ticker}({ticker})" if ticker != raw_ticker else ticker

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
    is_usd = ticker_data.get('currency') == 'USD'
    currency = ticker_data.get('currency', 'KRW')
    unit = "원" if currency == "KRW" else f" {currency}"
    price_fmt = "{:,.0f}" if currency == "KRW" else "{:,.2f}"

    change_emoji = "📈" if change_rate > 0 else "📉" if change_rate < 0 else "➖"

    ticker_label = f"{stock_name} ({ticker})" if stock_name else ticker
    if is_usd:
        msg = (
            f"📊 <b>[{exchange_display_name(exchange)}] {ticker_label}</b> 실시간 시세\n\n"
            f"현재가: <b>${price:,.2f}</b> {change_emoji}\n"
            f"전일대비: {change_rate:+.2f}% (${change_price:,.2f})\n"
            f"고가(24H): ${high:,.2f}\n"
            f"저가(24H): ${low:,.2f}\n"
            f"거래량: {volume:,.0f}"
        )
    else:
        msg = (
            f"📊 <b>[{exchange_display_name(exchange)}] {ticker_label}</b> 실시간 시세\n\n"
            f"현재가: <b>{price:,.0f}원</b> {change_emoji}\n"
            f"전일대비: {change_rate:+.2f}% ({change_price:,.0f}원)\n"
            f"고가(24H): {high:,.0f}원\n"
            f"저가(24H): {low:,.0f}원\n"
            f"거래대금: {volume/100000000:,.1f}억원"
        )

    if indicators:
        technical_parts = []
        rsi = indicators.get("rsi")
        if rsi is not None:
            technical_parts.append(f"RSI(14): {rsi:.1f}")
        for period in [7, 14, 30, 90]:
            ma_val = indicators.get(f"ma{period}")
            if ma_val is not None:
                technical_parts.append(f"MA{period}: ${ma_val:,.2f}" if is_usd else f"MA{period}: {ma_val:,.0f}원")
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


_REPORT_PERIOD_ALIASES = {
    "today": "today", "오늘": "today",
    "week": "week", "주간": "week", "7d": "week",
    "month": "month", "월간": "month", "30d": "month",
    "all": "all", "전체": "all",
}


def parse_report_args(args: list[str]) -> tuple[str, int | None, str | None]:
    """/report 명령 인자에서 (period, group_no, ticker)를 추출한다.
    지원 형태:
    - /report [today|week|month|all]
    - /report #1 [period]  또는 /report batch:1  또는 /report 배치1
    - /report BTC [period]  또는 /report 005930 [period]
    - /report #1 BTC [period]
    """
    period = "all"
    group_no: int | None = None
    ticker: str | None = None

    for raw in args or []:
        tok = str(raw).strip()
        if not tok:
            continue
        low = tok.lower()
        if low in _REPORT_PERIOD_ALIASES:
            period = _REPORT_PERIOD_ALIASES[low]
            continue
        m_batch = re.match(r"^(?:#|batch:|배치#?|group:)(\d+)$", low)
        if m_batch:
            group_no = int(m_batch.group(1))
            continue
        # 6자리 숫자는 국내주식 종목코드(예: 005930), 1~4자리 숫자는 배치 번호로 인식
        if tok.isdigit() and len(tok) <= 4 and group_no is None:
            group_no = int(tok)
            continue
        if ticker is None:
            ticker = tok.upper()

    return period, group_no, ticker


@check_auth
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "report"): return
    user_id = str(update.effective_chat.id)
    args = context.args or []
    period, group_no, ticker = parse_report_args(args)

    dca_mgr = getattr(main, "dca_manager", None)
    om = getattr(main, "order_manager", None)
    ex_adapter = getattr(main, "exchange_adapter", None)
    cash_reports = await analyze_user_cash_sufficiency(user_id, dca_mgr, om, ex_adapter)

    is_timeseries = (group_no is not None) or (ticker is not None)
    trades = read_trades(user_id, period, group_no=group_no, ticker=ticker)

    if is_timeseries:
        dca_sched = dca_mgr.get_schedule_by_group_no(user_id, group_no) if (dca_mgr and group_no is not None) else None
        open_orders = []
        if om:
            for o in om.get_user_orders(user_id):
                if group_no is not None and o.get("group_no") != group_no:
                    continue
                if ticker is not None:
                    tk_u = ticker.upper()
                    o_tk = str(o.get("ticker") or "").upper()
                    o_base = o_tk.split("-", 1)[1] if "-" in o_tk else o_tk
                    if tk_u not in (o_tk, o_base):
                        continue
                open_orders.append(o)

        if not trades and not dca_sched and not open_orders:
            target_desc = f"#{group_no} 배치" if group_no is not None else f"{ticker} 종목"
            await update.message.reply_text(
                f"📊 {target_desc}에 해당하는 체결 기록이나 활성 전략이 없습니다.\n"
                "⚠️ 사용법: <code>/report [today|week|month|all]</code> 또는 <code>/report #[배치번호]</code> · <code>/report [종목]</code>",
                parse_mode="HTML",
            )
            return

        snapshot = {
            "timeseries": True,
            "trades": trades,
            "period": period,
            "group_no": group_no,
            "ticker": ticker,
            "dca_sched": dca_sched,
            "open_orders": open_orders,
            "cash_reports": cash_reports,
        }
        token = main.create_list_view_token(user_id, "report", {"page": 0}, snapshot=snapshot)
        text, page, total_pages = build_timeseries_report_view_page(
            trades,
            period=period,
            group_no=group_no,
            ticker=ticker,
            page=0,
            dca_sched=dca_sched,
            open_orders=open_orders,
            cash_reports=cash_reports,
        )
        markup = None
        if total_pages > 1:
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ 다음", callback_data=f"lv|report|{token}|next")]])
        await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")
        return

    if not trades:
        cash_note = ""
        if cash_reports:
            from core.dca_manager import format_cash_health_section
            cash_note = "\n\n" + format_cash_health_section(cash_reports, html=True)
        await update.message.reply_text(
            "📊 해당 기간에 체결 기록이 없습니다.\n"
            "팁: 주문이 전량 체결되면 자동으로 기록됩니다."
            f"{cash_note}",
            parse_mode="HTML",
        )
        return

    snapshot = {
        "timeseries": False,
        "trades": trades,
        "period": period,
        "cash_reports": cash_reports,
    }
    token = main.create_list_view_token(user_id, "report", {"page": 0}, snapshot=snapshot)
    text, page, total_pages = build_report_view_page(trades, period, 0, cash_reports=cash_reports)
    markup = None
    if total_pages > 1:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ 다음", callback_data=f"lv|report|{token}|next")]])
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


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

    token = main.create_list_view_token(
        user_id, "history", {"page": 0},
        snapshot={"exchange": exchange, "ticker": ticker, "history": history},
    )
    msg, markup, _ = list_view_handlers.build_history_message(exchange, ticker, history, 0, token)
    await update.message.reply_text(msg, reply_markup=markup, parse_mode="HTML")
