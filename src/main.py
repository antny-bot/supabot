import os
import sys
import asyncio
import html as _html
import json
from collections import defaultdict
import re
import time
from aiohttp import web as _web
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters
)

from core.user_manager import UserManager, is_quiet_hours
from core.trade_log import append_trade, read_trades
from core.exchange_adapter import ExchangeAdapter
from core.order_manager import OrderManager
from core.dca_manager import DcaManager, execute_due_dca_schedules, check_daily_cash_alerts
from core.signal_engine import SignalEngine
from core.natural_language import (
    append_natural_language_log,
    append_preprocess_hit,
    normalize_natural_language_intent,
    preprocess_natural_language_intent,
)
from core.operational_events import append_operational_event
from core.manual_order_tokens import (
    MANUAL_ORDER_TTL_SECONDS,
    create_manual_order_token,
    pop_valid_manual_order,
    create_cancel_token,
    pop_valid_cancel_token,
    create_reset_token,
    pop_valid_reset_token,
    _pending_manual_orders,
    _pending_cancel_orders,
    _pending_reset_users,
)
from core.stock_resolver import find_kr_stock_candidates
from core.ticker_disambiguation import (
    create_disambiguation_token,
    pop_valid_disambiguation,
)
from core.list_view_tokens import (
    create_list_view_token,
    peek_list_view,
    update_list_view_state,
    discard_list_view,
)
import internal_api
from internal_api import trigger_realtime_sync
from core.secret_crypto import can_decrypt_secrets, has_secret_key
from core.parsers import (
    KST,
    RSI_INTERVAL_ALIASES, RSI_MINUTE_INTERVALS, POLL_INTERVAL_KEYS,
    normalize_exchange, is_exchange_token, exchange_display_name,
    parse_exchange_and_ticker, parse_number, parse_rsi_range, parse_optional_krw,
    parse_rsi_interval, parse_config_value, validate_config_update,
    has_gemini_key, get_user_rsi_interval, is_strategy_order,
    is_kis_regular_session, next_kis_regular_session,
    interpolate_range, resolve_linked_rsi_target,
    _format_seconds, get_dca_weights,
)
from core.formatters import (
    CMD_HELP,
    build_secret_security_status,
    build_start_menu_message,
)
from core.bot_logger import get_logger
from core.metrics import metrics
from core import trading_gate
from core.command_log import log_command

_log = get_logger("main")

# fire-and-forget 백그라운드 태스크 강한 참조 보관 (asyncio는 weak-ref만 잡아
# 참조를 놓치면 완료 전 GC될 수 있음 — 실시간 동기화/폴링 루프 유실 방지).
_bg_tasks: set = set()


def _spawn_bg(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        import inspect
        if inspect.iscoroutine(coro):
            coro.close()
        return None
    task = loop.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task

try:
    from build_info import BUILD_DATE, VERSION, GIT_SHA
except ImportError:
    BUILD_DATE = VERSION = GIT_SHA = "unknown"

# 환경 변수 로드
load_dotenv(dotenv_path="config/.env")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
DEBUG_TELEGRAM_MESSAGES = os.getenv("DEBUG_TELEGRAM_MESSAGES", "").lower() in ["1", "true", "yes"]
BOT_DISPLAY_NAME = "TTBot"

# 전역 객체 초기화
user_manager = UserManager()
user_manager.initialize_admin(ADMIN_CHAT_ID)
exchange_adapter = ExchangeAdapter(user_manager)
order_manager = OrderManager()
dca_manager = DcaManager()
signal_engine = SignalEngine(user_manager, exchange_adapter)
_order_wake_event: asyncio.Event = None  # post_init에서 초기화
_pending_nl_intents = {}
RSI_GRID_COMMAND_ALIASES = ("rsigrid", "rsitrade", "gridrsi")
DCA_COMMAND_ALIASES = ("dca", "autoinvest", "periodic")
ACCOUNT_COMMAND_ALIASES = ("whoami", "me")
DEFAULT_BOT_COMMANDS = [
    # 시스템
    ("start", "시스템 접속 및 메뉴"),
    ("help", "전체 명령어 도움말"),
    ("info", "버전 및 빌드 정보"),
    ("whoami", "내 계정 권한 확인"),
    # 자산
    ("asset", "통합 자산 현황"),
    ("price", "실시간 시세 조회"),
    ("indicators", "RSI/MACD/BB/Stoch 멀티지표"),
    ("history", "최근 체결 내역"),
    ("report", "기간별 수익률 리포트"),
    # 매매
    ("status", "트레이딩 전략 대시보드"),
    ("orders", "미체결 주문 목록"),
    ("buy", "단일 지정가 매수"),
    ("sell", "단일 지정가 매도"),
    ("cancel", "종목 전체 주문 취소"),
    ("cancelno", "배치 번호로 주문 취소"),
    ("grid", "가격 범위 분할 매수"),
    ("sgrid", "수량 분할 매도"),
    ("rsitrade", "RSI 순환 매매"),
    ("dca", "정기 적립식 매수/매도"),
    # 감시
    ("watch", "RSI 감시 종목 추가"),
    ("unwatch", "RSI 감시 제거"),
    # 설정
    ("config", "거래소, LLM API 설정"),
]
ADMIN_BOT_COMMANDS = DEFAULT_BOT_COMMANDS + [
    ("dbsync", "주문 DB 수동 동기화 (관리자)"),
]

# Conversation States
SET_EXCHANGE, SET_ACCESS, SET_SECRET, SET_KIS_APP, SET_KIS_SECRET, SET_KIS_ACCOUNT, SET_KIS_PRODUCT, SET_KIS_ENV, SET_GEMINI_KEY, SET_TOSS_CLIENT_ID, SET_TOSS_SECRET = range(11)

async def check_details_help(update: Update, command_name: str):
    if update.message and update.message.text:
        text = update.message.text.lower()
        if any(opt in text for opt in [" -h", "-help", "--help"]):
            help_text = CMD_HELP.get(command_name, "해당 명령어에 대한 상세 도움말이 아직 없습니다.")
            await update.message.reply_text(help_text, parse_mode="HTML")
            return True
    return False

# ==========================================
# 🔍 환경변수 검증
# ==========================================

def _validate_env():
    missing = []
    if not BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not ADMIN_CHAT_ID:
        missing.append("ADMIN_CHAT_ID")
    if not os.getenv("USER_SECRET_KEY", "").strip():
        missing.append("USER_SECRET_KEY")
    if missing:
        _log.critical("Missing required env vars: %s", ", ".join(missing), extra={"event": "env_missing", "vars": missing})
        _log.critical("Check config/.env — see config/.env.template for reference.")
        sys.exit(1)
    if not can_decrypt_secrets():
        _log.critical("USER_SECRET_KEY is invalid", extra={"event": "env_invalid_key"})
        _log.critical('Regenerate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"')
        sys.exit(1)


def _write_heartbeat():
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/health.json", "w") as f:
            json.dump({"ts": time.time()}, f)
    except Exception as e:
        _log.debug("Failed to write local health heartbeat: %s", e)


_last_db_heartbeat = 0.0


async def _record_db_heartbeat_async():
    global _last_db_heartbeat
    now = time.time()
    # 최소 60초 간격으로 DB 하트비트 기록
    if now - _last_db_heartbeat < 60:
        return
    try:
        from core.db import get_db, is_db_available
        if not is_db_available():
            return
        iso_now = datetime.now(timezone.utc).isoformat()
        await get_db().table("system_config").upsert({
            "key": "bot_heartbeat",
            "value": iso_now,
        }).execute_async()
        _last_db_heartbeat = now
    except Exception as e:
        _log.debug("Failed to record DB heartbeat: %s", e)


# ==========================================
# 🔒 권한 검증 미들웨어
# ==========================================
def check_auth(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_chat.id)
        user = user_manager.get_user(user_id)

        if not user:
            if update.message:
                await update.message.reply_text("👋 안녕하세요! 봇을 사용하시려면 먼저 /start 명령어를 입력해 주세요.")
            return

        if not user["is_active"]:
            await update.effective_chat.send_message("⏳ 관리자의 승인을 기다리는 중입니다. 승인이 완료되면 알려드릴게요!")
            return

        return await func(update, context, user)
    return wrapper

# ==========================================
# 🤖 명령어 핸들러
# ==========================================



async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_details_help(update, "start"): return
    user_id = str(update.effective_chat.id)
    username = update.effective_user.first_name
    user = user_manager.get_user(user_id)
    if user and not user["is_active"]:
        user_manager.refresh_user(user_id)
        user = user_manager.get_user(user_id)

    if not user:
        user_manager.add_user(user_id, username)
        await update.message.reply_text(
            f"🎁 반갑습니다, {username}님!\n\n"
            "봇 사용 등록이 요청되었습니다. 관리자 승인 후 모든 기능을 사용하실 수 있습니다.\n"
            f"내 ID: {user_id}"
        )
        if ADMIN_CHAT_ID:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"🔔 신규 유저 등록 요청\n\n- 이름: {username}\n- ID: {user_id}\n\n승인하려면 서버에서 직접 처리해주세요.",
            )
    elif not user["is_active"]:
        await update.message.reply_text("⏳ 현재 승인 대기 중입니다. 잠시만 기다려 주세요!")
    else:
        if username and username != user.get("username"):
            user_manager.update_username(user_id, username)
            user["username"] = username
        await update.message.reply_text(build_start_menu_message(user), parse_mode="HTML")


_KIS_RSI_MINUTE_ERROR = "⚠️ 한국투자증권 RSI는 일봉만 지원합니다. /config set rsi_interval day 후 다시 시도하세요."

async def ensure_rsi_supported(update, user, exchange):
    if not exchange_adapter.get_exchange(exchange).supports_minute_candles() and get_user_rsi_interval(user) != "day":
        await update.message.reply_text(_KIS_RSI_MINUTE_ERROR)
        return False
    return True


async def resolve_ticker_for_command(
    update, user_id: str, args: list, default_exchange: str, cmd_hint: str = ""
):
    """parse_exchange_and_ticker + resolve_ticker 를 합친 핸들러 공통 헬퍼.

    Returns (exchange, ticker) on success, ticker may be None if not provided in args.
    Returns (exchange, None) with error already sent if Korean name resolution failed
    (후보가 있으면 선택 버튼을 보내고, 없으면 기존 에러 메시지를 보낸다).
    """
    exchange, raw = parse_exchange_and_ticker(args, default_exchange)
    if not raw:
        return exchange, None
    ticker = await exchange_adapter.resolve_ticker(user_id, exchange, raw)
    if exchange_adapter.get_exchange(exchange).requires_numeric_ticker() and ticker and any('가' <= c <= '힣' for c in ticker):
        candidates = await find_kr_stock_candidates(raw, exchange_adapter, user_id, exchange)
        if candidates:
            await _send_ticker_disambiguation(update, user_id, raw, candidates)
            return exchange, None
        hint = f"\n예: {cmd_hint}" if cmd_hint else ""
        await update.message.reply_text(
            f"⚠️ {exchange_display_name(exchange)}은 종목코드로 입력하세요.{hint}"
        )
        return exchange, None
    return exchange, ticker


async def _send_ticker_disambiguation(update, user_id: str, raw_name: str, candidates: list):
    """후보 종목 목록을 인라인 버튼으로 제시한다. 선택 시 원본 명령을 코드로 치환해 재실행."""
    original_text = update.message.text or ""
    token = create_disambiguation_token(user_id, original_text, raw_name, candidates)
    buttons = [
        [InlineKeyboardButton(f"{name} ({code})", callback_data=f"tickerpick|{token}|{idx}")]
        for idx, (name, code) in enumerate(candidates)
    ]
    await update.message.reply_text(
        f"🔍 '{raw_name}'과 정확히 일치하는 종목을 찾지 못했습니다. 후보 중 선택해 주세요:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def ticker_disambiguation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_chat.id)
    try:
        _, token, idx_s = query.data.split("|")
        idx = int(idx_s)
    except (ValueError, AttributeError):
        await query.edit_message_text("⚠️ 잘못된 요청입니다.")
        return

    code, original_text_or_err, raw_name = pop_valid_disambiguation(token, user_id, idx)
    if code is None:
        await query.edit_message_text(f"⚠️ {original_text_or_err}")
        return

    original_text = original_text_or_err
    patched_text = original_text.replace(raw_name, code, 1)
    await query.edit_message_text(f"✅ 선택한 종목으로 다시 실행합니다: {patched_text}")

    from telegram import Message, MessageEntity
    # CommandHandler.check_update는 message.entities[0]이 offset=0의 BOT_COMMAND여야
    # 명령으로 인식한다 — 합성 메시지는 직접 채워줘야 함.
    entities = []
    command_part = patched_text.split(maxsplit=1)[0] if patched_text else ""
    if command_part.startswith("/"):
        entities = [MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=len(command_part))]
    synthetic_message = Message(
        message_id=query.message.message_id,
        date=query.message.date,
        chat=query.message.chat,
        from_user=query.from_user,
        text=patched_text,
        entities=entities,
    )
    synthetic_message.set_bot(context.bot)
    synthetic_update = Update(update_id=0, message=synthetic_message)
    await context.application.process_update(synthetic_update)

LLM_COMMAND_CATALOG = "\n".join([
    "asset req=- opt=exchange run=now ex=show my assets",
    "price req=ticker opt=exchange run=now ex=btc price",
    "orders req=- opt=exchange run=now ex=open orders",
    "status req=- opt=- run=now ex=strategy status",
    "config_view req=- opt=- run=now ex=show settings",
    "history req=- opt=exchange,ticker run=now ex=btc history",
    "buy req=exchange,ticker,price,volume run=confirm ex=buy btc at 95000000 qty 0.01",
    "sell req=exchange,ticker,price,volume run=confirm ex=sell btc at 120000000 qty 0.01",
    "grid req=ticker,start_price,end_price,count,amount_krw opt=exchange run=confirm ex=grid buy btc 90m-95m 5 1m",
    "sgrid req=ticker,start_price,end_price,count,volume opt=exchange run=confirm ex=grid sell btc 100m-110m 5 qty 0.1",
    "rsitrade req=ticker,amount_krw opt=exchange,buy_rsi_range,sell_rsi_range,count run=confirm ex=btc rsi 25-30 budget 1m",
    "gridrsi req=ticker,amount_krw opt=exchange,buy_rsi_range,sell_rsi_range,count run=confirm ex=btc rsi 25-30 100만 5분할",
    "sgridrsi req=ticker,amount_krw opt=exchange,sell_rsi_range,count run=confirm ex=eth rsi 80-90 100만 10개 매도",
    "watch req=ticker opt=exchange run=confirm ex=watch btc",
    "unwatch req=ticker opt=exchange run=confirm ex=stop watching btc",
    "config_set req=config_key,config_value opt=- run=confirm ex=set max order 500000",
    "cancel req=ticker opt=exchange run=confirm ex=cancel btc orders",
    "help req=- opt=- run=now ex=what can you do",
])

# --- 주문 동기화 및 생명주기 관리 엔진 (core.order_sync 모듈화 및 re-export) ---
from core.order_sync import (
    _STOPLOSS_PLACE_RETRIES,
    _STATUS_CHECK_FAIL_LIMIT,
    _status_check_failures,
    _REORDER_FAIL_LIMIT,
    _reorder_failures,
    _limit_warned_orders,
    _REORDER_PRICE_TOLERANCE,
    _exchange_status_semaphores,
    _exchange_user_semaphores,
    _cleanup_stale_caches,
    _find_duplicate_open_order,
    _extract_order_submit_failure_reason,
    _find_linked_sell_orders,
    _find_linked_sell_order,
    _create_linked_sell_order,
    reconcile_external_sells_fifo,
    cancel_and_remove_order,
    _handle_market_closed,
    _submit_reserved_or_reorder,
    _apply_stop_loss,
    _process_order_fill,
    _handle_cancel_requested,
    sync_orders,
    startup_recovery,
)

# --- 백그라운드 루프 엔진 ---
async def _get_admin_prefs_async() -> dict:
    from core.db import get_db, is_db_available
    base = dict(UserManager.DEFAULT_PREFERENCES)
    if is_db_available():
        try:
            res = await get_db().table("system_config").select("key,value").in_(
                "key", ["poll_active_interval", "poll_no_order_interval", "signal_analysis_interval"]
            ).execute_async()
            rows = res.data
            for row in rows:
                base[row["key"]] = int(row["value"])
            return base
        except Exception as e:
            _log.debug("Failed to read admin prefs from DB, using fallback: %s", e)
    # Fallback: admin user preferences
    for user in user_manager.users.values():
        if user.get("is_admin"):
            return {**base, **user.get("preferences", {})}
    return base

async def _interruptible_sleep(seconds: float):
    try:
        await asyncio.wait_for(_order_wake_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass

async def order_sync_loop(application):
    _log.info("Order sync loop started", extra={"event": "order_sync_loop_start"})
    while True:
        _order_wake_event.clear()
        _write_heartbeat()
        await _record_db_heartbeat_async()
        try:
            prefs = await _get_admin_prefs_async()
            await order_manager.reload_from_db_async()
            await dca_manager.reload_from_db_async()
            await user_manager.reload_from_db_async()
            await execute_due_dca_schedules(
                application, dca_manager, exchange_adapter, order_manager, user_manager
            )
            await sync_orders(application)
            await check_daily_cash_alerts(
                application, dca_manager, order_manager, exchange_adapter, user_manager
            )
            metrics.record_poll_ok()
            interval = prefs["poll_active_interval"] if order_manager.orders \
                       else prefs["poll_no_order_interval"]
            dca_delay = dca_manager.nearest_next_run_delay()
            if dca_delay is not None:
                interval = min(float(interval), max(1.0, float(dca_delay)))
            await _interruptible_sleep(interval)
        except Exception as e:
            _log.error("Order sync loop error", exc_info=e, extra={"event": "order_sync_loop_error"})
            append_operational_event("error", "order_sync_loop", "order sync loop error", e)
            await _interruptible_sleep(60)

_OPS_ALERT_COOLDOWN_SECONDS = 6 * 3600  # 동일 알림 재전송 최소 간격
_ops_alert_last_sent: dict = {}


def _ops_alert_key(issue: str) -> str:
    """이슈 문자열에서 변동되는 수치를 제거해 쿨다운 dedup 키로 쓴다.

    issue 문자열 자체(예: "주문 실패율 높음 [toss]: 17/22건 (77% 실패)")는 실패 건수가
    매 사이클 바뀌므로 그대로 키로 쓰면 동일 사안인데도 쿨다운이 매번 풀려 알림이 반복 발송된다.
    """
    return re.sub(r"\d+", "#", issue)


async def _check_ops_health(application):
    """메트릭 임계 초과 시 관리자에게 알림 전송. 동일 알림은 쿨다운 내 재전송하지 않는다."""
    if not ADMIN_CHAT_ID:
        return
    issues = metrics.ops_alerts()
    if not issues:
        return
    now = time.time()
    due_issues = [
        issue for issue in issues
        if now - _ops_alert_last_sent.get(_ops_alert_key(issue), 0) >= _OPS_ALERT_COOLDOWN_SECONDS
    ]
    if not due_issues:
        return
    msg = "🚨 <b>운영 알림</b>\n\n" + "\n".join(f"• {issue}" for issue in due_issues)
    try:
        await application.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
        for issue in due_issues:
            _ops_alert_last_sent[_ops_alert_key(issue)] = now
    except Exception as e:
        _log.warning("Ops health alert failed", exc_info=e, extra={"event": "ops_alert_failed"})

async def signal_analysis_loop(application):
    _log.info("Signal analysis loop started", extra={"event": "signal_analysis_loop_start"})
    await asyncio.sleep(5)
    _ops_check_counter = 0
    while True:
        try:
            prefs = await _get_admin_prefs_async()
            await user_manager.reload_from_db_async()
            await signal_engine.analyze_watchlist(application)
            metrics.record_signal_ok()
            _ops_check_counter += 1
            if _ops_check_counter % 6 == 0:  # 매 6회 주기(~30분)마다 운영 상태 점검
                await _check_ops_health(application)
            await asyncio.sleep(prefs["signal_analysis_interval"])
        except Exception as e:
            _log.error("Signal analysis loop error", exc_info=e, extra={"event": "signal_analysis_loop_error"})
            append_operational_event("error", "signal_analysis_loop", "signal analysis loop error", e)
            await asyncio.sleep(300)

async def notify_admin_security_status(application):
    if not ADMIN_CHAT_ID:
        return
    admin = user_manager.get_user(str(ADMIN_CHAT_ID))
    if not admin:
        return
    status = build_secret_security_status(admin)
    if status == "정상":
        return
    message = (
        "⚠️ 보안 키 상태 확인 필요\n\n"
        f"- USER_SECRET_KEY: {status}\n"
        "- /config -v에서 상태를 확인하세요."
    )
    append_operational_event("warning", "security", "USER_SECRET_KEY status requires attention", status)
    try:
        await application.bot.send_message(chat_id=ADMIN_CHAT_ID, text=message)
    except Exception as e:
        append_operational_event("warning", "security", "failed to notify admin security status", e)

_notify_runner: "_web.AppRunner | None" = None

async def post_init(application):
    """봇 초기화 후 백그라운드 태스크 실행"""
    global _order_wake_event, _notify_runner
    _order_wake_event = asyncio.Event()

    def _on_order_added():
        _order_wake_event.set()
        _spawn_bg(trigger_realtime_sync())
    order_manager.on_order_added = _on_order_added
    dca_manager.on_schedule_changed = _on_order_added

    try:
        await application.bot.set_my_commands(
            [BotCommand(cmd, desc) for cmd, desc in DEFAULT_BOT_COMMANDS],
            scope=BotCommandScopeDefault(),
        )
        for user_id, user in user_manager.users.items():
            if user.get("is_admin"):
                await application.bot.set_my_commands(
                    [BotCommand(cmd, desc) for cmd, desc in ADMIN_BOT_COMMANDS],
                    scope=BotCommandScopeChat(chat_id=int(user_id)),
                )
    except Exception as e:
        _log.warning("Telegram command menu update failed", exc_info=e, extra={"event": "command_menu_update_failed"})
        append_operational_event("warning", "post_init", "Telegram command menu update failed", e)
    await notify_admin_security_status(application)
    await startup_recovery(application)
    await _record_db_heartbeat_async()
    _spawn_bg(order_sync_loop(application))
    _spawn_bg(signal_analysis_loop(application))

    # DB 장애 복구 후 데이터 동기화 백그라운드 태스크 기동
    from core.db_sync import start_sync_loop
    start_sync_loop()

    # 정기 데이터 백업 루프 기동
    from core.backup_manager import start_backup_loop
    start_backup_loop()

    # 실시간 시세 WebSocket 수집 엔진 기동
    from core.websocket_client import init_ticker_engine
    init_ticker_engine(user_manager)


    if os.environ.get("MANAGER_API_KEY"):
        internal_api.init(exchange_adapter, order_manager, user_manager)
        notify_app = _web.Application()
        notify_app["bot_application"] = application
        notify_app["signal_engine"] = signal_engine
        notify_app.router.add_post("/internal/notify", internal_api._internal_notify_handler)
        notify_app.router.add_post("/internal/execute_grid", internal_api._internal_execute_grid_handler)
        notify_app.router.add_post("/internal/execute_sgrid", internal_api._internal_execute_sgrid_handler)
        notify_app.router.add_post("/internal/execute_rsitrade", internal_api._internal_execute_rsitrade_handler)
        notify_app.router.add_post("/internal/execute_dca", internal_api._internal_execute_dca_handler)
        notify_app.router.add_post("/internal/cancel_order", internal_api._internal_cancel_order_handler)
        notify_app.router.add_post("/internal/sync_order", internal_api._internal_sync_order_handler)
        notify_app.router.add_post("/internal/force_update_order", internal_api._internal_force_update_order_handler)
        notify_app.router.add_post("/internal/get_prices", internal_api._internal_get_prices_handler)
        notify_app.router.add_post("/internal/get_balances", internal_api._internal_get_balances_handler)
        notify_app.router.add_post("/internal/backup/trigger", internal_api._internal_backup_trigger_handler)
        notify_app.router.add_get("/internal/backup/status", internal_api._internal_backup_status_handler)
        _notify_runner = _web.AppRunner(notify_app)
        await _notify_runner.setup()
        port = int(os.environ.get("INTERNAL_PORT", 8765))
        site = _web.TCPSite(_notify_runner, "0.0.0.0", port)
        await site.start()
        _log.info(f"Internal notify server started on port {port}", extra={"event": "notify_server_start"})

async def post_shutdown(application):
    """봇 종료 시 외부 연결을 정리합니다."""
    global _notify_runner
    if _notify_runner:
        await _notify_runner.cleanup()
        _notify_runner = None

    # 웹소켓 엔진 정지
    from core.websocket_client import ticker_engine
    if ticker_engine:
        ticker_engine.stop()

    await exchange_adapter.close()

# ==========================================
# 🚀 메인 실행부
# ==========================================
def main():
    _validate_env()

    from handlers import watch_handlers, manual_order_handlers, status_handlers, query_handlers, config_handlers, strategy_handlers, nl_intent_handlers, system_handlers, list_view_handlers

    # post_init을 통해 백그라운드 태스크를 봇 생명주기에 안전하게 편입시킵니다.
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    # 명령어 사용 로깅 (group=-1: 모든 command 핸들러보다 먼저 실행)
    application.add_handler(MessageHandler(filters.COMMAND, system_handlers._command_usage_handler), group=-1)

    # 운영 기본값은 민감정보 보호를 위해 텔레그램 본문 로깅을 끕니다.
    if DEBUG_TELEGRAM_MESSAGES:
        application.add_handler(MessageHandler(filters.ALL, system_handlers.global_debug_handler), group=-1)

    config_conv = ConversationHandler(
        entry_points=[CommandHandler("config", config_handlers.config_command)],
        states={
            SET_EXCHANGE: [CallbackQueryHandler(config_handlers.config_exchange_callback, pattern="^conf_")],
            SET_ACCESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_handlers.set_access_key)],
            SET_SECRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_handlers.set_secret_key)],
            SET_KIS_APP: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_handlers.set_kis_app_key)],
            SET_KIS_SECRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_handlers.set_kis_secret_key)],
            SET_KIS_ACCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_handlers.set_kis_account)],
            SET_KIS_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_handlers.set_kis_product)],
            SET_KIS_ENV: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_handlers.set_kis_env)],
            SET_GEMINI_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_handlers.set_gemini_key)],
            SET_TOSS_CLIENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_handlers.set_toss_client_id)],
            SET_TOSS_SECRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, config_handlers.set_toss_secret)],
        },
        fallbacks=[CommandHandler("cancel", config_handlers.cancel_config)],
        allow_reentry=True  # /config 중복 입력 허용
    )

    # 핸들러 등록 (ConversationHandler를 최상단에 유지)
    application.add_handler(config_conv)
    application.add_handler(CommandHandler("cfg", config_handlers.config_command)) # 테스트용 단순 명령어
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", system_handlers.help_command))
    application.add_handler(CommandHandler("commands", system_handlers.help_command))
    application.add_handler(CommandHandler("dbsync", system_handlers.dbsync_command))
    application.add_handler(CommandHandler("backup", system_handlers.backup_command))
    application.add_handler(CommandHandler("halt", system_handlers.halt_command))
    application.add_handler(CommandHandler("resume", system_handlers.resume_command))
    application.add_handler(CommandHandler("resetuser", system_handlers.resetuser_command))
    application.add_handler(CommandHandler("nlstats", system_handlers.nlstats_command))
    application.add_handler(CommandHandler("info", system_handlers.info_command))
    for command_name in ACCOUNT_COMMAND_ALIASES:
        application.add_handler(CommandHandler(command_name, system_handlers.whoami_command))
    application.add_handler(CommandHandler("asset", query_handlers.asset_command))
    application.add_handler(CommandHandler("status", status_handlers.status_command))
    application.add_handler(CommandHandler("price", query_handlers.price_command))
    application.add_handler(CommandHandler("p", query_handlers.price_command))
    application.add_handler(CommandHandler("indicators", query_handlers.indicators_command))
    application.add_handler(CommandHandler("ind", query_handlers.indicators_command))
    application.add_handler(CommandHandler("history", query_handlers.history_command))
    application.add_handler(CommandHandler("report", query_handlers.report_command))
    application.add_handler(CommandHandler("buy", manual_order_handlers.buy_command))
    application.add_handler(CommandHandler("sell", manual_order_handlers.sell_command))
    application.add_handler(CommandHandler("orders", query_handlers.orders_command))
    application.add_handler(CommandHandler("cancel", query_handlers.cancel_command))
    application.add_handler(CommandHandler("cancelno", query_handlers.cancelno_command))
    application.add_handler(CommandHandler("grid", strategy_handlers.grid_command))
    application.add_handler(CommandHandler("sgrid", strategy_handlers.sgrid_command))
    for command_name in RSI_GRID_COMMAND_ALIASES:
        application.add_handler(CommandHandler(command_name, strategy_handlers.rsitrade_command))
    application.add_handler(CommandHandler("watch", watch_handlers.watch_command))
    application.add_handler(CommandHandler("unwatch", watch_handlers.unwatch_command))
    application.add_handler(CallbackQueryHandler(strategy_handlers.grid_quick_callback, pattern="^grid_quick_"))
    application.add_handler(CallbackQueryHandler(strategy_handlers.signal_snooze_callback, pattern="^signal_snooze_"))
    application.add_handler(CallbackQueryHandler(strategy_handlers.grid_confirm_callback, pattern="^(gridrun|sgridrun|grid_cancel)"))
    application.add_handler(CallbackQueryHandler(strategy_handlers.rsitrade_confirm_callback, pattern="^rsitrun"))
    application.add_handler(CommandHandler("sgridrsi", strategy_handlers.sgridrsi_command))
    application.add_handler(CallbackQueryHandler(strategy_handlers.sgridrsi_confirm_callback, pattern="^sgridrsirun"))
    for command_name in DCA_COMMAND_ALIASES:
        application.add_handler(CommandHandler(command_name, strategy_handlers.dca_command))
    application.add_handler(CommandHandler("sdca", strategy_handlers.sdca_command))
    application.add_handler(CallbackQueryHandler(strategy_handlers.dca_confirm_callback, pattern="^dcarun\\|"))
    application.add_handler(CallbackQueryHandler(strategy_handlers.dca_delete_callback, pattern="^dcadel\\|"))
    application.add_handler(CallbackQueryHandler(manual_order_handlers.manual_order_confirm_callback, pattern="^(manualrun|manualcancel)\\|"))
    application.add_handler(CallbackQueryHandler(query_handlers.cancel_confirm_callback, pattern="^(cancelrun|cancelabort)\\|"))
    application.add_handler(CallbackQueryHandler(list_view_handlers.list_view_callback, pattern="^lv\\|"))
    application.add_handler(CallbackQueryHandler(system_handlers.reset_confirm_callback, pattern="^(resetrun|resetabort)\\|"))
    application.add_handler(CallbackQueryHandler(nl_intent_handlers.natural_language_confirm_callback, pattern="^nl(run|cancel)\\|"))
    application.add_handler(CallbackQueryHandler(ticker_disambiguation_callback, pattern="^tickerpick\\|"))
    application.add_handler(CallbackQueryHandler(nl_intent_handlers.nl_ticker_disambiguation_callback, pattern="^nltickerpick\\|"))

    # [중요] 알 수 없는 명령어 처리 (가장 마지막에 등록)
    application.add_handler(MessageHandler(filters.COMMAND, system_handlers.unknown_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, nl_intent_handlers.natural_language_command))

    _log.info(f"{BOT_DISPLAY_NAME} starting", extra={"event": "bot_start", "version": VERSION})

    # 동기식으로 실행 (자체 이벤트 루프를 안전하게 생성합니다)
    application.run_polling()

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
