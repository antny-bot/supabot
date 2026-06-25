"""/help, /info, /whoami, /dbsync 등 시스템·진단 커맨드 및 글로벌 메시지 핸들러.

`_log`/`GIT_SHA`/`VERSION`/`BUILD_DATE`/`BOT_DISPLAY_NAME`/`user_manager`/
`order_manager` 등은 main.py 소유 상태로 남는다 (main.<name>으로 접근).
"""
import asyncio
import html as _html
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from main import check_auth, check_details_help
import main
from core.command_log import log_command
from core.db import get_db, is_db_available
from core.formatters import build_help_message, build_account_summary
from core import trading_gate
from core.operational_events import append_operational_event
from core.trade_log import clear_user_trades


# --- 디버그용 글로벌 메시지 핸들러 ---
async def global_debug_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        main._log.debug("Telegram message received", extra={"event": "debug_message", "user_id": str(update.effective_user.id), "length": len(update.message.text)})
    return


# --- 명령어 사용 로깅 핸들러 (group=-1, fire-and-forget) ---
async def _command_usage_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text and update.effective_user:
        cmd = update.message.text.split()[0].lstrip("/").split("@")[0].lower()
        log_command(str(update.effective_user.id), cmd, source="direct")


@check_auth
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    await update.message.reply_text(build_help_message(user), parse_mode="HTML")


@check_auth
async def dbsync_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if not user.get("is_admin"):
        await update.message.reply_text("❌ 어드민 전용 명령어입니다.")
        return
    orders_ok = main.order_manager.reload_from_db()
    users_ok = main.user_manager.reload_from_db()
    if orders_ok and users_ok:
        await update.message.reply_text(
            f"✅ DB 동기화 완료 — 주문 {len(main.order_manager.orders)}건, "
            f"유저 {len(main.user_manager.users)}명 로드됨.",
            parse_mode="HTML",
        )
    elif orders_ok or users_ok:
        parts = []
        parts.append(f"주문 {len(main.order_manager.orders)}건" if orders_ok else "주문 동기화 실패")
        parts.append(f"유저 {len(main.user_manager.users)}명" if users_ok else "유저 동기화 실패")
        await update.message.reply_text("⚠️ DB 동기화 일부 실패 — " + ", ".join(parts), parse_mode="HTML")
    else:
        await update.message.reply_text("❌ DB 동기화 실패 (DB 미연결 또는 오류).")


@check_auth
async def halt_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """전체 거래 즉시 중지 (관리자 전용)."""
    if not user.get("is_admin"):
        await update.message.reply_text("❌ 어드민 전용 명령어입니다.")
        return
    trading_gate.set_trading_halt(True, by_user_id=str(update.effective_chat.id))
    active = len(main.order_manager.orders)
    await update.message.reply_text(
        "🛑 전체 거래를 중지했습니다.\n"
        "신규 수동/전략 주문 및 KIS 재주문이 차단됩니다. (손절·익절 보호 매도는 계속 동작)\n"
        f"현재 추적 중인 미체결 주문: {active}건\n"
        "재개하려면 /resume 를 입력하세요."
    )


@check_auth
async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """전체 거래 재개 (관리자 전용)."""
    if not user.get("is_admin"):
        await update.message.reply_text("❌ 어드민 전용 명령어입니다.")
        return
    trading_gate.set_trading_halt(False, by_user_id=str(update.effective_chat.id))
    await update.message.reply_text("✅ 전체 거래를 재개했습니다. 신규 주문이 다시 허용됩니다.")


@check_auth
async def resetuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """특정 유저의 주문 추적·실적을 완전 초기화 (관리자 전용). 거래소 미체결 주문은 먼저 취소를 시도한다."""
    if not user.get("is_admin"):
        await update.message.reply_text("❌ 어드민 전용 명령어입니다.")
        return
    admin_user_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 리셋할 유저 ID를 입력하세요. 예: <code>/resetuser 123456789</code>", parse_mode="HTML")
        return
    target_user_id = args[0]
    target_user = main.user_manager.get_user(target_user_id)
    if not target_user:
        await update.message.reply_text(f"❌ 유저 {_html.escape(target_user_id)}를 찾을 수 없습니다.")
        return

    open_orders = [o for o in main.order_manager.get_user_orders(target_user_id) if o.get("status") not in ("done", "cancel")]
    failed = []
    for ord in open_orders:
        try:
            ok = await main.exchange_adapter.cancel_order(target_user_id, ord["exchange"], ord["uuid"], ord["ticker"])
        except Exception:
            ok = False
        if ok:
            main.order_manager.remove_order(ord["uuid"])
        else:
            failed.append(ord)
        await asyncio.sleep(0.1)

    if failed:
        lines = "\n".join(f"- [{f['exchange']}] {f['ticker']} ({f['uuid']})" for f in failed)
        await update.message.reply_text(
            "⚠️ 다음 미체결 주문의 거래소 취소에 실패하여 리셋을 중단했습니다:\n"
            f"{_html.escape(lines)}\n\n"
            "거래소 상태를 직접 확인한 뒤 다시 시도해 주세요.",
            parse_mode="HTML",
        )
        return

    token = main.create_reset_token(admin_user_id, target_user_id)
    keyboard = [[InlineKeyboardButton("✅ 리셋 확정", callback_data=f"resetrun|{token}"),
                 InlineKeyboardButton("❌ 취소", callback_data=f"resetabort|{token}")]]
    await update.message.reply_text(
        f"🧨 유저 <code>{_html.escape(target_user_id)}</code>의 주문 추적과 거래 실적을 "
        "<b>완전히 초기화</b>합니다.\n"
        "(미체결 주문 취소 완료 — orders/trade_logs 전체 삭제, 되돌릴 수 없습니다)\n\n"
        "계속하시겠습니까?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def reset_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, token = query.data.split("|", 1)
    if action == "resetabort":
        main._pending_reset_users.pop(token, None)
        await query.edit_message_text("ℹ️ 리셋을 취소했습니다.")
        return

    admin_user_id = str(query.from_user.id)
    pending, error = main.pop_valid_reset_token(token, admin_user_id)
    if error:
        await query.edit_message_text(f"⚠️ {error}")
        return

    target_user_id = pending["target_user_id"]
    order_count = main.order_manager.clear_user_orders(target_user_id)
    trade_count = clear_user_trades(target_user_id)

    append_operational_event(
        "warning", "resetuser",
        f"admin reset user orders/trades",
        f"admin={admin_user_id} target={target_user_id} orders={order_count} trades={trade_count}",
    )

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text="🧨 관리자에 의해 주문 추적과 거래 실적이 초기화되었습니다.",
        )
    except Exception:
        pass

    await query.edit_message_text(
        f"✅ 유저 {target_user_id} 리셋 완료 — 주문 {order_count}건, 체결 내역 {trade_count}건 삭제됨."
    )


@check_auth
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "info"): return
    short_sha = main.GIT_SHA[:7] if main.GIT_SHA != "unknown" else "unknown"
    msg = (
        f"ℹ️ <b>{_html.escape(main.BOT_DISPLAY_NAME)} 빌드 정보</b>\n\n"
        f"- 버전: {_html.escape(main.VERSION)}\n"
        f"- 빌드: {_html.escape(main.BUILD_DATE)}\n"
        f"- 커밋: <code>{_html.escape(short_sha)}</code>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


@check_auth
async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    user_id = str(update.effective_chat.id)
    await update.message.reply_text(build_account_summary(user_id, user), parse_mode="HTML")


@check_auth
async def nlstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if not user.get("is_admin"):
        await update.message.reply_text("❌ 어드민 전용 명령어입니다.")
        return
    if not is_db_available():
        await update.message.reply_text("❌ DB 미연결.")
        return
    try:
        now = time.time()
        since_7d = now - 7 * 86400

        q = get_db().table("nl_logs").select("final_action,llm_action,logged_at")
        q._params.update({"logged_at": f"gte.{since_7d}", "order": "logged_at.desc", "limit": "500"})
        rows = q.execute().data or []

        total = len(rows)
        final_counts: dict[str, int] = {}
        llm_counts: dict[str, int] = {}
        for r in rows:
            fa = r.get("final_action") or "unmatched"
            la = r.get("llm_action") or "unmatched"
            final_counts[fa] = final_counts.get(fa, 0) + 1
            llm_counts[la] = llm_counts.get(la, 0) + 1

        top_final = sorted(final_counts.items(), key=lambda x: -x[1])[:10]
        top_llm = sorted(llm_counts.items(), key=lambda x: -x[1])[:10]

        lines = [f"📊 <b>NL 로그 통계</b> (최근 7일, 최대 500건)\n총 {total}건\n"]
        lines.append("<b>최종 액션 Top 10</b>")
        for action, cnt in top_final:
            lines.append(f"  {_html.escape(action)}: {cnt}")
        lines.append("\n<b>LLM 액션 Top 10</b>")
        for action, cnt in top_llm:
            lines.append(f"  {_html.escape(action)}: {cnt}")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ 조회 실패: {_html.escape(str(e))}", parse_mode="HTML")


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """등록되지 않은 명령어가 입력되었을 때 호출됩니다."""
    await update.message.reply_text(
        "❓ 알 수 없는 명령어입니다.\n\n"
        "사용 가능한 명령어 목록은 /help 를 입력하여 확인해 주세요."
    )
