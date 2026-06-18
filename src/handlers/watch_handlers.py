"""/watch, /unwatch — RSI 감시 종목 관리."""
from telegram import Update
from telegram.ext import ContextTypes

import main
from main import check_auth, check_details_help, ensure_rsi_supported
from core.parsers import parse_exchange_and_ticker


@check_auth
async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "watch"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 감시할 종목을 입력하세요. 예: `/watch BTC` 또는 `/watch 빗썸 SOL`")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)

    if not await ensure_rsi_supported(update, user, exchange):
        return

    resolved = await main.exchange_adapter.resolve_ticker(user_id, exchange, ticker)
    if resolved != ticker:
        display_name = ticker
        ticker = resolved
    else:
        display_name = ticker

    if main.user_manager.add_watchlist(user_id, exchange, ticker):
        await update.message.reply_text(f"✅ {exchange.upper()}의 {display_name}({ticker})가 관심 종목에 등록되었습니다. RSI 시그널을 감시합니다.")
    else:
        await update.message.reply_text(f"ℹ️ {display_name}({ticker})는 이미 관심 종목에 등록되어 있습니다.")


@check_auth
async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "unwatch"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 삭제할 종목을 입력하세요. 예: `/unwatch BTC`")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)

    if not await ensure_rsi_supported(update, user, exchange):
        return

    if main.user_manager.remove_watchlist(user_id, exchange, ticker):
        await update.message.reply_text(f"✅ {exchange.upper()}의 {ticker}가 관심 종목에서 삭제되었습니다.")
    else:
        await update.message.reply_text(f"ℹ️ 관심 종목 목록에 {ticker}가 없습니다.")
