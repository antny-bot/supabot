"""/help, /info, /whoami, /dbsync 등 시스템·진단 커맨드 및 글로벌 메시지 핸들러.

`_log`/`GIT_SHA`/`VERSION`/`BUILD_DATE`/`BOT_DISPLAY_NAME`/`user_manager`/
`order_manager` 등은 main.py 소유 상태로 남는다 (main.<name>으로 접근).
"""
import html as _html
import time

from telegram import Update
from telegram.ext import ContextTypes

from main import check_auth, check_details_help
import main
from core.command_log import log_command
from core.db import get_db, is_db_available
from core.formatters import build_help_message, build_account_summary
from core import trading_gate


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
