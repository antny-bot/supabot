"""/status — 전략 대시보드."""
from telegram import Update
from telegram.ext import ContextTypes

import main
from main import check_auth, check_details_help
from handlers import list_view_handlers


@check_auth
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "status"): return
    user_id = str(update.effective_chat.id)
    orders = main.order_manager.get_user_orders(user_id)

    if not orders:
        await update.message.reply_text("📊 현재 가동 중인 트레이딩 전략이 없습니다.\n거래소 실제 미체결 주문은 /orders에서 확인하세요.")
        return

    token = main.create_list_view_token(user_id, "status", {"expanded": False})
    msg, markup = list_view_handlers.build_status_message(orders, False, token)
    await update.message.reply_text(msg, reply_markup=markup, parse_mode="HTML")
