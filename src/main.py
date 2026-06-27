import os
import sys
import asyncio
import html as _html
import json
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
    task = asyncio.create_task(coro)
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
signal_engine = SignalEngine(user_manager, exchange_adapter)
_order_wake_event: asyncio.Event = None  # post_init에서 초기화
_pending_nl_intents = {}
RSI_GRID_COMMAND_ALIASES = ("rsigrid", "rsitrade", "gridrsi")
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
    except Exception:
        pass


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

# 손절매도 발행 일시 실패 시 동일 사이클 내 재시도 횟수 (미보호 포지션 창 축소).
_STOPLOSS_PLACE_RETRIES = 3

# KIS/Toss 수동 주문 상태 조회가 None을 반환할 때, 일시 오류(토큰만료/레이트리밋/타임아웃)와
# 실제 "주문 없음"을 구분할 수 없으므로 연속 실패가 이 횟수에 도달해야 추적을 종료한다.
_STATUS_CHECK_FAIL_LIMIT = 3
_status_check_failures: dict = {}

# 재주문/예약주문 매칭 시 가격 비교 허용 오차(원). 거래소 틱 단위 보정 잔차를 흡수한다.
_REORDER_PRICE_TOLERANCE = 1.0


async def _find_duplicate_open_order(exchange_adapter, user_id, exchange, ticker, side, price, volume):
    """재주문/예약주문 발행 직전, 이전 사이클의 create_order 응답이 유실됐을 뿐 실제로는
    거래소에 이미 제출된 동일 스펙의 미체결 주문이 있는지 확인한다.

    응답 유실 시 그냥 재시도하면 거래소엔 살아있는 주문이 그대로 있는 채로 동일 주문을
    한 번 더 제출해 중복 주문이 발생할 수 있다(M3). KIS/Toss만 get_open_orders를 지원한다.
    """
    try:
        open_orders = await exchange_adapter.get_open_orders(user_id, exchange, ticker)
    except Exception:
        return None
    if not open_orders:
        return None
    for o in open_orders:
        if not o.get("uuid"):
            continue
        if o.get("side") != side:
            continue
        if abs(float(o.get("price", 0)) - float(price)) > _REORDER_PRICE_TOLERANCE:
            continue
        if abs(float(o.get("volume", 0)) - float(volume)) > 1e-6:
            continue
        return o
    return None


def _find_linked_sell_order(buy_uuid):
    """주어진 rsitrade 매수 주문에 연동된 익절매도 주문(reorder_of==buy_uuid)을 찾는다.

    add_order(매도 생성)와 update_order_fill(매수 체결 기록)은 둘 다 fire-and-forget DB
    쓰기라 그 사이 크래시 시 DB엔 매도 주문만 남고 매수의 filled_volume은 갱신되지 않을 수
    있다(M4). 재시작/재폴링 시 같은 체결을 다시 감지해도 이미 매도 주문이 존재하면 중복
    발행하지 않도록 reorder_of를 매수-매도 연결 키로 사용한다.
    """
    for o in order_manager.orders:
        if o.get("strategy") == "rsitrade_sell" and o.get("reorder_of") == buy_uuid:
            return o
    return None


async def _create_linked_sell_order(application, ord, exec_vol, state):
    """rsitrade 매수 체결 시 연동된 익절매도 주문을 생성한다.

    sync_orders의 정상 처리 경로와 startup_recovery의 크래시 복구 경로가 동일 로직을
    공유한다. 생성 전 _find_linked_sell_order로 멱등성을 확인해, 직전 실행이 매도 주문
    생성까지는 마쳤으나 매수 체결 기록(filled_volume) 갱신 전에 죽은 경우에도 매도를
    중복 발행하지 않고 매수의 filled_volume만 동기화한다.

    Returns: "created" | "exists" | "no_price" | "zero_volume" | "failed"
    """
    user_id = ord["user_id"]
    exchange = ord["exchange"]
    ticker = ord["ticker"]
    newly_filled = exec_vol - ord["filled_volume"]

    if _find_linked_sell_order(ord["uuid"]):
        order_manager.update_order_fill(ord["uuid"], exec_vol, state)
        return "exists"

    target_rsi = resolve_linked_rsi_target(ord["linked_to"])
    user = user_manager.get_user(user_id) or {"preferences": UserManager.DEFAULT_PREFERENCES}
    sell_price = await signal_engine.get_price_by_rsi(
        exchange,
        ticker,
        target_rsi,
        side="ask",
        interval=get_user_rsi_interval(user),
        user_id=user_id,
    )
    if not sell_price:
        return "no_price"

    ex = exchange_adapter.get_exchange(exchange)
    sell_volume = ex.round_volume(newly_filled)
    if ex.requires_integer_volume() and sell_volume <= 0:
        return "zero_volume"

    s_res = await exchange_adapter.create_order(user_id, exchange, ticker, "ask", sell_price, sell_volume)
    if not (s_res and "uuid" in s_res):
        return "failed"

    stop_loss_pct = float(user.get("preferences", {}).get("stop_loss_pct", 0) or 0)
    stop_price = (
        ex.adjust_price_to_tick(ord["price"] * (1 - stop_loss_pct / 100), ticker)
        if stop_loss_pct > 0 else None
    )
    order_manager.add_order(user_id, exchange, ticker, s_res["uuid"], sell_price, sell_volume,
                             side="ask", strategy="rsitrade_sell", target_rsi=target_rsi,
                             stop_price=stop_price, group_no=ord.get("group_no"),
                             reorder_of=ord["uuid"])
    order_manager.update_order_fill(ord["uuid"], exec_vol, state)
    await application.bot.send_message(
        chat_id=user_id,
        text=f"✅ [{ticker}] 매수 체결 및 익절 예약 완료\n"
             f"• 체결: {newly_filled:.4f}개\n"
             f"• 익절가: {sell_price:,.0f}원 (RSI {target_rsi} 목표)",
    )
    return "created"


# --- 주문 동기화 및 자동 대응 엔진 ---
async def sync_orders(application):
    """현재 추적 중인 주문들의 상태를 거래소와 동기화하고 자동 대응 수행"""
    initial_state = [(o['uuid'], o.get('status'), o.get('filled_volume'), o.get('stop_price')) for o in order_manager.orders]
    all_orders = list(order_manager.orders)
    _price_cache = {}  # 동일 sync 사이클 내 중복 API 호출 방지: {(exchange, ticker): price}
    now_ts = time.time()
    for ord in all_orders:
        # /cancel, /cancelno, NL 취소 등으로 이번 사이클 도중 이미 제거된 주문은
        # 거래소 재조회를 건너뛴다 (외부 개입 오탐 방지). O(1) 인덱스 조회.
        if not order_manager.has_order(ord["uuid"]):
            continue

        # next_check_at이 미래로 설정된 주문(KIS 장외/pending_reorder)은 해당 시점까지
        # 거래소 재조회를 건너뛴다. 활성 wait 주문은 next_check_at=0이라 매번 점검된다.
        if float(ord.get("next_check_at") or 0) > now_ts:
            continue

        user_id = ord['user_id']
        exchange = ord['exchange']
        ticker = ord['ticker']

        ex_obj = exchange_adapter.get_exchange(exchange)
        if exchange == "toss" and str(ticker).isdigit():
            # NXT 애프터마켓(15:30~20:00 KST)을 반영한 실제 운영시간 캐시 갱신 — 캐시는
            # 당일 1회만 조회되고(ensure_toss_kr_calendar 내부 dedup) 이후 호출은 즉시 반환됨.
            await exchange_adapter.ensure_toss_kr_calendar(user_id)
        if not ex_obj.is_market_open(ticker):
            next_check = ex_obj.next_check_timestamp(ticker)
            status = ord.get("status") if ord.get("status") in ("pending_reorder", "reserved") else "market_closed"
            order_manager.update_order_status(ord["uuid"], status)
            order_manager.update_next_check_at(ord["uuid"], next_check)
            continue

        if getattr(ex_obj, "supports_reserved_orders", False) and ord.get("status") in ("pending_reorder", "reserved"):
            remaining = max(float(ord.get("volume", 0)) - float(ord.get("filled_volume", 0)), 0)
            if remaining <= 0:
                order_manager.remove_order(ord["uuid"])
                continue
            # 글로벌 거래 중지 중에는 신규 노출인 재주문/예약주문 제출을 보류한다 (보호성 매도는 별도 경로).
            if trading_gate.is_trading_halted():
                order_manager.update_next_check_at(ord["uuid"], ex_obj.next_check_timestamp(ticker))
                continue
            vol = int(remaining) if ex_obj.requires_integer_volume() else remaining
            side = ord.get("side", "bid")
            price = ord.get("price")
            # M3: 직전 사이클에서 create_order 응답이 유실됐을 수 있으므로, 재발행 전에
            # 동일 스펙의 미체결 주문이 이미 거래소에 있는지 먼저 확인해 중복 제출을 막는다.
            dup = await _find_duplicate_open_order(exchange_adapter, user_id, exchange, ticker, side, price, vol)
            res = dup if dup else await exchange_adapter.create_order(user_id, exchange, ticker, side, price, vol)
            action = "재주문" if ord.get("status") == "pending_reorder" else "예약주문 실행"
            order_kind = "전략" if is_strategy_order(ord) else "자동 재주문 설정"
            label = exchange_display_name(exchange)
            if res and "uuid" in res:
                old_uuid = ord["uuid"]
                order_manager.replace_order_uuid(old_uuid, res["uuid"])
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ [{label}] {ticker} {order_kind} 주문 {action} 완료\n"
                         f"• 가격: {float(ord.get('price', 0)):,.0f}원\n"
                         f"• 잔량: {remaining:,.0f}주\n"
                         f"• 새 주문ID: {res['uuid']}",
                )
            else:
                order_manager.update_next_check_at(ord["uuid"], ex_obj.next_check_timestamp(ticker))
                append_operational_event("warning", "sync_orders", f"{exchange} strategy {action} failed", ticker)
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ [{label}] {ticker} {order_kind} 주문 {action} 실패\n다음 정규장 체크 때 다시 시도합니다.",
                )
            await asyncio.sleep(0.2)
            continue

        res = await exchange_adapter.get_order_status(user_id, exchange, ord['uuid'], ticker)
        if not res:
            # KIS/Toss(RegularSessionExchange, supports_reserved_orders)는 정규장 정책을 공유한다
            # (docs/detail/kis_market_policy.md: "이 문서 제목은 KIS 기준이지만 Toss도 동일하게 적용된다").
            # exchange == "kis" 하드코딩 분기는 Toss 주문을 누락시켜 체결 감지·trade_log 기록이
            # 영구히 멈추는 원인이었다 — capability 기반으로 일반화.
            # is_strategy_order(grid/sgrid/rsitrade) OR 수동 주문에 auto_reorder opt-in 플래그가
            # 켜진 경우 모두 동일하게 다음 정규장 재주문 대기로 전환한다.
            if getattr(ex_obj, "supports_reserved_orders", False) and (is_strategy_order(ord) or ord.get("auto_reorder")):
                order_manager.mark_reorder_pending(ord["uuid"], ex_obj.next_check_timestamp(ticker))
                order_kind = "전략" if is_strategy_order(ord) else "자동 재주문 설정"
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"⏳ [{exchange_display_name(exchange)}] {ticker} {order_kind} 주문 확인이 불가하여 다음 정규장 재주문 대기로 전환합니다.",
                )
            elif getattr(ex_obj, "supports_reserved_orders", False):
                # KIS/Toss 수동 주문 조회 None은 토큰만료·레이트리밋·타임아웃 등 일시 오류로도
                # 발생한다 — 단 1회 실패로 살아있는 미체결 주문 추적을 끊으면 안 된다(과거 버그).
                # 연속 _STATUS_CHECK_FAIL_LIMIT회 실패해야 비로소 "주문 없음"으로 보고 종료한다.
                fails = _status_check_failures.get(ord["uuid"], 0) + 1
                if fails < _STATUS_CHECK_FAIL_LIMIT:
                    _status_check_failures[ord["uuid"]] = fails
                    append_operational_event(
                        "warning", "sync_orders",
                        f"{exchange} manual order status check failed ({fails}/{_STATUS_CHECK_FAIL_LIMIT}), retrying",
                        ticker,
                    )
                else:
                    _status_check_failures.pop(ord["uuid"], None)
                    order_manager.remove_order(ord["uuid"])
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=f"🛑 [{exchange_display_name(exchange)}] {ticker} 수동 주문 확인이 불가하여 추적을 종료합니다.\n자동 재주문은 하지 않습니다.",
                    )
            else:
                append_operational_event("warning", "sync_orders", f"{exchange} get_order_status returned no result", ticker)
            continue
        # 조회가 성공하면 누적 실패 카운터를 초기화한다.
        _status_check_failures.pop(ord["uuid"], None)
        state = res['state']
        exec_vol = res['executed_volume']
        keep_order_for_retry = False

        # 손절(Stop-Loss) 조건 평가 — rsitrade_sell 포지션이 stop_price 미만으로 하락 시
        if (
            ord.get("strategy") == "rsitrade_sell"
            and ord.get("stop_price")
            and state == "wait"
        ):
            cache_key = (exchange, ticker)
            if cache_key not in _price_cache:
                tkr = await exchange_adapter.get_ticker(exchange, ticker, user_id)
                _price_cache[cache_key] = float(tkr.get("trade_price", 0)) if tkr else 0.0
            current_price = _price_cache.get(cache_key, 0.0)

            # 트레일링 스톱 (Trailing Stop) 로직
            if ord.get("trailing_stop_pct") is not None and current_price > 0:
                trailing_pct = float(ord["trailing_stop_pct"])
                expected_stop_price = current_price * (1 - trailing_pct / 100)
                expected_stop_price = exchange_adapter.get_exchange(exchange).adjust_price_to_tick(expected_stop_price, ticker)
                if expected_stop_price > float(ord["stop_price"]):
                    order_manager.update_order_stop_price(ord["uuid"], expected_stop_price)
                    ord["stop_price"] = expected_stop_price
                    _log.info(f"Trailing stop updated for {ticker}: stop_price -> {expected_stop_price:,.0f}원 (현재가: {current_price:,.0f}원)")

            if current_price and current_price < float(ord["stop_price"]):
                cancel_ok = await exchange_adapter.cancel_order(user_id, exchange, ord["uuid"], ticker)
                if cancel_ok:
                    remaining = float(ord["volume"]) - float(ord["filled_volume"])
                    sl_price = exchange_adapter.get_exchange(exchange).adjust_price_to_tick(current_price * 0.999, ticker)
                    # 익절매도를 취소해 잔량을 푼 뒤 손절매도를 발행한다. 발행이 일시적으로
                    # 실패(거래소 거부/네트워크)할 수 있으므로 짧게 재시도해 미보호 포지션 창을 줄인다.
                    sl_res = None
                    for _sl_attempt in range(_STOPLOSS_PLACE_RETRIES):
                        sl_res = await exchange_adapter.create_order(
                            user_id, exchange, ticker, "ask", sl_price, remaining
                        )
                        if sl_res and "uuid" in sl_res:
                            break
                        await asyncio.sleep(0.3)
                    # 익절매도는 이미 취소됐으므로 원주문(쉬고 있던 ask)은 더 이상 거래소에 없다 →
                    # 추적에서 제거한다(유지하면 다음 사이클에 "외부 개입"으로 오인됨).
                    order_manager.remove_order(ord["uuid"])
                    if sl_res and "uuid" in sl_res:
                        order_manager.add_order(
                            user_id, exchange, ticker, sl_res["uuid"],
                            sl_price, remaining, side="ask", strategy="stoploss",
                        )
                        await application.bot.send_message(
                            chat_id=user_id,
                            text=f"🛑 [{ticker}] 손절 실행\n"
                                 f"• 현재가: {current_price:,.0f}원\n"
                                 f"• 손절 기준가: {float(ord['stop_price']):,.0f}원\n"
                                 f"• 손절 주문이 제출되었습니다.",
                        )
                    else:
                        # 익절매도는 취소됐는데 손절매도 발행이 끝내 실패 → 잔량이 무방비로 남는다.
                        # 자동 재발행할 수단이 없으므로(쉬던 주문 uuid는 이미 죽음) 정직하게 실패를
                        # 알리고 즉시 수동 매도를 요청한다. 과거엔 항상 "제출되었습니다"로 오보했다.
                        append_operational_event(
                            "error", "sync_orders",
                            f"{exchange} stop-loss order placement failed after retries (position unprotected)",
                            ticker,
                        )
                        await application.bot.send_message(
                            chat_id=user_id,
                            text=f"🚨 [{ticker}] 손절 주문 발행 실패\n"
                                 f"• 현재가: {current_price:,.0f}원\n"
                                 f"• 손절 기준가: {float(ord['stop_price']):,.0f}원\n"
                                 f"• 기존 익절 주문은 취소되었으나 손절 매도가 접수되지 않았습니다.\n"
                                 f"• ⚠️ 잔량이 무방비 상태입니다. 즉시 수동으로 매도해 주세요.",
                        )
                await asyncio.sleep(0.2)
                continue

        # 1. 부분 체결 또는 전량 체결 발생 시
        if exec_vol > ord['filled_volume']:
            newly_filled = exec_vol - ord['filled_volume']
            
            # 매수 체결 시 -> 연동된 매도(익절) 주문 생성 (rsitrade 전략인 경우)
            if ord['side'] == 'bid' and ord['strategy'] == 'rsitrade' and ord['linked_to']:
                outcome = await _create_linked_sell_order(application, ord, exec_vol, state)
                if outcome == "zero_volume":
                    keep_order_for_retry = True
                    await asyncio.sleep(0.2)
                    continue
                if outcome in ("no_price", "failed"):
                    keep_order_for_retry = True
            
            # 일반 체결 알림
            else:
                order_manager.update_order_fill(ord['uuid'], exec_vol, state)
                if state == "done":
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ [{exchange.upper()}] {ticker} 주문 완료\n"
                             f"• {'매수' if ord['side']=='bid' else '매도'} 전량 체결되었습니다.",
                    )

        # 2. 주문 종료 처리 (체결 완료 또는 취소)
        if state in ["done", "cancel"] and not keep_order_for_retry:
            if state == "cancel":
                # supports_reserved_orders(KIS/Toss)는 정규장 정책을 공유한다 — exchange == "kis"
                # 하드코딩은 Toss 전략 주문이 거래소측 만료/취소(예: 장 마감 후 미체결 잔량 정리)를
                # "외부 개입"으로 오인해 재주문 없이 추적을 끊는 버그였다(line 410의 동일 버그 패턴).
                # is_strategy_order OR 수동 주문 auto_reorder opt-in 모두 동일하게 재주문 대기로 전환.
                if getattr(ex_obj, "supports_reserved_orders", False) and (is_strategy_order(ord) or ord.get("auto_reorder")):
                    next_check = ex_obj.next_check_timestamp(ticker)
                    order_manager.mark_reorder_pending(ord['uuid'], next_check)
                    order_kind = "전략" if is_strategy_order(ord) else "자동 재주문 설정"
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=f"⏳ [{exchange_display_name(exchange)}] {ticker} {order_kind} 주문이 만료/취소되어 다음 정규장 재주문 예정입니다.",
                    )
                    await asyncio.sleep(0.2)
                    continue
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"🛑 [{exchange_display_name(exchange)}] {ticker} 외부 개입 감지\n"
                         f"• 주문이 거래소에서 취소되었습니다. 추적을 중단합니다.",
                )
            if state == "done":
                append_trade(
                    user_id=user_id,
                    exchange=exchange,
                    ticker=ticker,
                    side=ord["side"],
                    price=ord["price"],
                    volume=float(exec_vol) if exec_vol else float(ord.get("filled_volume", ord["volume"])),
                    strategy=ord.get("strategy", "manual"),
                    uuid=ord["uuid"],
                    fee_amount=float(res.get("fee_amount") or 0),
                )
            order_manager.remove_order(ord['uuid'])
        elif state != ord.get("status"):
            order_manager.update_order_status(ord['uuid'], state)
        
        await asyncio.sleep(0.2)

    # 상태 변경 여부 체크 후 실시간 동기화 트리거
    final_state = [(o['uuid'], o.get('status'), o.get('filled_volume'), o.get('stop_price')) for o in order_manager.orders]
    if initial_state != final_state:
        _spawn_bg(trigger_realtime_sync())

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
        except Exception:
            pass
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
        try:
            prefs = await _get_admin_prefs_async()
            await order_manager.reload_from_db_async()
            await sync_orders(application)
            metrics.record_poll_ok()
            interval = prefs["poll_active_interval"] if order_manager.orders \
                       else prefs["poll_no_order_interval"]
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

# --- 자동 복구 및 초기화 로직 ---
async def startup_recovery(application):
    """봇 시작 시 rsitrade 매수 체결 후 연동 익절매도 발행이 누락된 주문을 복구한다.

    sync_orders의 매수체결→익절매도 생성(add_order)과 매수 체결기록(update_order_fill)
    사이에 봇이 크래시하면, 재시작 시 매수의 filled_volume이 stale한 채로 남아있을 수
    있다(M4). 정상적으로는 다음 sync_orders 폴링에서 자연 복구되지만, 그 창을 줄이기
    위해 기동 시 즉시 1회 점검한다. _create_linked_sell_order의 멱등성 체크 덕분에
    이미 매도 주문이 생성된 경우(매도만 남고 매수 기록이 안 된 경우)에도 중복 발행 없이
    매수의 filled_volume만 동기화한다.
    """
    _log.info("Startup recovery started", extra={"event": "startup_recovery_start"})
    targets = [
        ord for ord in list(order_manager.orders)
        if ord.get('side') == 'bid' and ord.get('strategy') == 'rsitrade' and ord.get('linked_to')
    ]
    recovered_count = 0

    for ord in targets:
        if not order_manager.has_order(ord["uuid"]):
            continue
        try:
            res = await exchange_adapter.get_order_status(ord['user_id'], ord['exchange'], ord['uuid'], ord.get("ticker"))
        except Exception as e:
            _log.warning("Startup recovery: order status check failed", exc_info=e,
                         extra={"event": "startup_recovery_status_error", "uuid": ord['uuid']})
            continue
        if not res:
            continue
        exec_vol = float(res.get('executed_volume', 0) or 0)
        if exec_vol <= float(ord.get('filled_volume', 0)):
            continue
        outcome = await _create_linked_sell_order(application, ord, exec_vol, res['state'])
        if outcome == "created":
            recovered_count += 1
            _log.info("Startup recovery: linked sell order created", extra={"event": "startup_recovery_recovered", "uuid": ord['uuid']})

    if recovered_count > 0:
        _log.info("Startup recovery complete", extra={"event": "startup_recovery_done", "recovered": recovered_count})

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
    _spawn_bg(order_sync_loop(application))
    _spawn_bg(signal_analysis_loop(application))
    
    # DB 장애 복구 후 데이터 동기화 백그라운드 태스크 기동
    from core.db_sync import start_sync_loop
    start_sync_loop()

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
        notify_app.router.add_post("/internal/cancel_order", internal_api._internal_cancel_order_handler)
        notify_app.router.add_post("/internal/sync_order", internal_api._internal_sync_order_handler)
        notify_app.router.add_post("/internal/force_update_order", internal_api._internal_force_update_order_handler)
        notify_app.router.add_post("/internal/get_prices", internal_api._internal_get_prices_handler)
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

    from handlers import watch_handlers, manual_order_handlers, status_handlers, query_handlers, config_handlers, strategy_handlers, nl_intent_handlers, system_handlers

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
    application.add_handler(CallbackQueryHandler(manual_order_handlers.manual_order_confirm_callback, pattern="^(manualrun|manualcancel)\\|"))
    application.add_handler(CallbackQueryHandler(query_handlers.cancel_confirm_callback, pattern="^(cancelrun|cancelabort)\\|"))
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
