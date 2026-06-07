"""/help, /info, /whoami, /dbsync 등 시스템·진단 커맨드 및 글로벌 메시지 핸들러.

`_log`/`GIT_SHA`/`VERSION`/`BUILD_DATE`/`BOT_DISPLAY_NAME`/`user_manager`/
`order_manager` 등은 main.py 소유 상태로 남는다 (main.<name>으로 접근).
"""
import html as _html

from telegram import Update
from telegram.ext import ContextTypes

from main import check_auth, check_details_help
import main
from core.command_log import log_command
from core.formatters import build_help_message, build_account_summary


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
    ok = main.order_manager.reload_from_db()
    if ok:
        await update.message.reply_text(
            f"✅ DB 동기화 완료 — 주문 {len(main.order_manager.orders)}건 로드됨.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("❌ DB 동기화 실패 (DB 미연결 또는 오류).")


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


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """등록되지 않은 명령어가 입력되었을 때 호출됩니다."""
    await update.message.reply_text(
        "❓ 알 수 없는 명령어입니다.\n\n"
        "사용 가능한 명령어 목록은 /help 를 입력하여 확인해 주세요."
    )
