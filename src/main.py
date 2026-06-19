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
from core.order_execution import execute_grid_orders, execute_rsitrade_orders, execute_sgridrsi_orders
from core.operational_events import append_operational_event
from core.secret_crypto import can_decrypt_secrets, has_secret_key
from core.parsers import (
    KST,
    RSI_INTERVAL_ALIASES, RSI_MINUTE_INTERVALS, POLL_INTERVAL_KEYS,
    normalize_exchange, is_exchange_token, exchange_display_name,
    parse_exchange_and_ticker, parse_number, parse_rsi_range, parse_optional_krw,
    parse_rsi_interval, parse_config_value, validate_max_order, validate_config_update,
    has_gemini_key, get_user_rsi_interval, is_strategy_order,
    is_kis_regular_session, next_kis_regular_session, kis_next_check_timestamp,
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
from core.command_log import log_command

_log = get_logger("main")

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
_pending_manual_orders = {}
_pending_cancel_orders = {}
MANUAL_ORDER_TTL_SECONDS = 600
RSI_GRID_COMMAND_ALIASES = ("rsigrid", "rsitrade", "gridrsi")
ACCOUNT_COMMAND_ALIASES = ("whomai", "me")
DEFAULT_BOT_COMMANDS = [
    # 시스템
    ("start", "시스템 접속 및 메뉴"),
    ("help", "전체 명령어 도움말"),
    ("info", "버전 및 빌드 정보"),
    ("whomai", "내 계정 권한 확인"),
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
        await update.message.reply_text(build_start_menu_message(user), parse_mode="HTML")


_KIS_RSI_MINUTE_ERROR = "⚠️ 한국투자증권 RSI는 일봉만 지원합니다. /config set rsi_interval day 후 다시 시도하세요."

async def ensure_rsi_supported(update, user, exchange):
    if exchange == "kis" and get_user_rsi_interval(user) != "day":
        await update.message.reply_text(_KIS_RSI_MINUTE_ERROR)
        return False
    return True

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

def create_manual_order_token(user_id, exchange, side, ticker, price, volume, ord_type="limit"):
    token = str(len(_pending_manual_orders) + 1)
    while token in _pending_manual_orders:
        token = str(int(token) + 1)
    _pending_manual_orders[token] = {
        "user_id": str(user_id),
        "exchange": exchange,
        "side": side,
        "ticker": ticker,
        "price": float(price),
        "volume": float(volume),
        "ord_type": ord_type,
        "created_at": time.time(),
    }
    return token

def pop_valid_manual_order(token, user_id):
    token = str(token)
    pending = _pending_manual_orders.get(token)
    if not pending:
        return None, "만료되었거나 찾을 수 없는 주문 확인 요청입니다. 다시 입력해 주세요."
    if pending.get("user_id") != str(user_id):
        return None, "다른 사용자의 주문 확인 요청은 실행할 수 없습니다."
    if time.time() - float(pending.get("created_at", 0)) > MANUAL_ORDER_TTL_SECONDS:
        _pending_manual_orders.pop(token, None)
        append_operational_event("warning", "manual_order", "manual order confirmation expired", pending.get("ticker"))
        return None, "주문 확인 요청이 만료되었습니다. 다시 입력해 주세요."
    _pending_manual_orders.pop(token, None)
    return pending, None

def create_cancel_token(user_id, orders):
    token = str(len(_pending_cancel_orders) + 1)
    while token in _pending_cancel_orders:
        token = str(int(token) + 1)
    _pending_cancel_orders[token] = {
        "user_id": str(user_id),
        "orders": [{"exchange": o["exchange"], "uuid": o["uuid"], "ticker": o["ticker"]} for o in orders],
        "created_at": time.time(),
    }
    return token

def pop_valid_cancel_token(token, user_id):
    token = str(token)
    pending = _pending_cancel_orders.get(token)
    if not pending:
        return None, "만료되었거나 찾을 수 없는 취소 요청입니다. 다시 시도해 주세요."
    if pending.get("user_id") != str(user_id):
        return None, "다른 사용자의 취소 요청은 실행할 수 없습니다."
    if time.time() - float(pending.get("created_at", 0)) > MANUAL_ORDER_TTL_SECONDS:
        _pending_cancel_orders.pop(token, None)
        return None, "취소 요청이 만료되었습니다. 다시 시도해 주세요."
    _pending_cancel_orders.pop(token, None)
    return pending, None

# --- 주문 동기화 및 자동 대응 엔진 ---
async def sync_orders(application):
    """현재 추적 중인 주문들의 상태를 거래소와 동기화하고 자동 대응 수행"""
    initial_state = [(o['uuid'], o.get('status'), o.get('filled_volume'), o.get('stop_price')) for o in order_manager.orders]
    all_orders = list(order_manager.orders)
    _price_cache = {}  # 동일 sync 사이클 내 중복 API 호출 방지: {(exchange, ticker): price}
    for ord in all_orders:
        # /cancel, /cancelno, NL 취소 등으로 이번 사이클 도중 이미 제거된 주문은
        # 거래소 재조회를 건너뛴다 (외부 개입 오탐 방지)
        if not any(o["uuid"] == ord["uuid"] for o in order_manager.orders):
            continue

        user_id = ord['user_id']
        exchange = ord['exchange']
        ticker = ord['ticker']

        if exchange == "kis" and not is_kis_regular_session():
            next_check = kis_next_check_timestamp()
            status = "pending_reorder" if ord.get("status") == "pending_reorder" else "market_closed"
            order_manager.update_order_status(ord["uuid"], status)
            order_manager.update_next_check_at(ord["uuid"], next_check)
            continue

        if exchange == "kis" and ord.get("status") == "pending_reorder":
            remaining = max(float(ord.get("volume", 0)) - float(ord.get("filled_volume", 0)), 0)
            if remaining <= 0:
                order_manager.remove_order(ord["uuid"])
                continue
            res = await exchange_adapter.create_order(user_id, exchange, ticker, ord.get("side", "bid"), ord.get("price"), int(remaining))
            if res and "uuid" in res:
                old_uuid = ord["uuid"]
                order_manager.replace_order_uuid(old_uuid, res["uuid"])
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ [한국투자증권] {ticker} 전략 주문 재주문 완료\n"
                         f"• 가격: {float(ord.get('price', 0)):,.0f}원\n"
                         f"• 잔량: {remaining:,.0f}주\n"
                         f"• 새 주문ID: {res['uuid']}",
                )
            else:
                order_manager.update_next_check_at(ord["uuid"], kis_next_check_timestamp())
                append_operational_event("warning", "sync_orders", "KIS strategy reorder failed", ticker)
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ [한국투자증권] {ticker} 전략 주문 재주문 실패\n다음 정규장 체크 때 다시 시도합니다.",
                )
            await asyncio.sleep(0.2)
            continue

        res = await exchange_adapter.get_order_status(user_id, exchange, ord['uuid'], ticker)
        if not res:
            if exchange == "kis" and is_strategy_order(ord):
                order_manager.mark_reorder_pending(ord["uuid"], kis_next_check_timestamp())
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"⏳ [한국투자증권] {ticker} 전략 주문 확인이 불가하여 다음 정규장 재주문 대기로 전환합니다.",
                )
            elif exchange == "kis":
                order_manager.remove_order(ord["uuid"])
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"🛑 [한국투자증권] {ticker} 수동 주문 확인이 불가하여 추적을 종료합니다.\n자동 재주문은 하지 않습니다.",
                )
            continue
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
                expected_stop_price = (
                    ExchangeAdapter.adjust_krx_price_to_tick(expected_stop_price)
                    if exchange in ("kis", "toss")
                    else ExchangeAdapter.adjust_price_to_tick(expected_stop_price)
                )
                if expected_stop_price > float(ord["stop_price"]):
                    order_manager.update_order_stop_price(ord["uuid"], expected_stop_price)
                    ord["stop_price"] = expected_stop_price
                    _log.info(f"Trailing stop updated for {ticker}: stop_price -> {expected_stop_price:,.0f}원 (현재가: {current_price:,.0f}원)")

            if current_price and current_price < float(ord["stop_price"]):
                cancel_ok = await exchange_adapter.cancel_order(user_id, exchange, ord["uuid"], ticker)
                if cancel_ok:
                    remaining = float(ord["volume"]) - float(ord["filled_volume"])
                    sl_price = (
                        ExchangeAdapter.adjust_krx_price_to_tick(current_price * 0.999)
                        if exchange in ("kis", "toss")
                        else ExchangeAdapter.adjust_price_to_tick(current_price * 0.999)
                    )
                    sl_res = await exchange_adapter.create_order(
                        user_id, exchange, ticker, "ask", sl_price, remaining
                    )
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
                await asyncio.sleep(0.2)
                continue

        # 1. 부분 체결 또는 전량 체결 발생 시
        if exec_vol > ord['filled_volume']:
            newly_filled = exec_vol - ord['filled_volume']
            
            # 매수 체결 시 -> 연동된 매도(익절) 주문 생성 (rsitrade 전략인 경우)
            if ord['side'] == 'bid' and ord['strategy'] == 'rsitrade' and ord['linked_to']:
                target_rsi = resolve_linked_rsi_target(ord['linked_to'])
                
                user = user_manager.get_user(user_id) or {"preferences": UserManager.DEFAULT_PREFERENCES}
                sell_price = await signal_engine.get_price_by_rsi(
                    exchange,
                    ticker,
                    target_rsi,
                    side="ask",
                    interval=get_user_rsi_interval(user),
                    user_id=user_id,
                )
                if sell_price:
                    sell_volume = newly_filled
                    if exchange in ("kis", "toss"):
                        sell_volume = int(sell_volume)
                        if sell_volume <= 0:
                            keep_order_for_retry = True
                            await asyncio.sleep(0.2)
                            continue
                    # 매도 주문 전송
                    s_res = await exchange_adapter.create_order(user_id, exchange, ticker, "ask", sell_price, sell_volume)
                    if s_res and 'uuid' in s_res:
                        stop_loss_pct = float(user.get("preferences", {}).get("stop_loss_pct", 0) or 0)
                        stop_price = (
                            (
                                ExchangeAdapter.adjust_krx_price_to_tick(ord["price"] * (1 - stop_loss_pct / 100))
                                if exchange in ("kis", "toss")
                                else ExchangeAdapter.adjust_price_to_tick(ord["price"] * (1 - stop_loss_pct / 100))
                            )
                            if stop_loss_pct > 0 else None
                        )
                        order_manager.add_order(user_id, exchange, ticker, s_res['uuid'], sell_price, sell_volume,
                                             side="ask", strategy="rsitrade_sell", target_rsi=target_rsi,
                                             stop_price=stop_price, group_no=ord.get("group_no"))
                        order_manager.update_order_fill(ord['uuid'], exec_vol, state)
                        await application.bot.send_message(
                            chat_id=user_id,
                            text=f"✅ [{ticker}] 매수 체결 및 익절 예약 완료\n"
                                 f"• 체결: {newly_filled:.4f}개\n"
                                 f"• 익절가: {sell_price:,.0f}원 (RSI {target_rsi} 목표)",
                        )
                    else:
                        keep_order_for_retry = True
                else:
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
                if exchange == "kis" and is_strategy_order(ord):
                    next_check = kis_next_check_timestamp()
                    order_manager.mark_reorder_pending(ord['uuid'], next_check)
                    await application.bot.send_message(
                        chat_id=user_id,
                        text=f"⏳ [한국투자증권] {ticker} 전략 주문이 만료/취소되어 다음 정규장 재주문 예정입니다.",
                    )
                    await asyncio.sleep(0.2)
                    continue
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"🛑 [{exchange.upper()}] {ticker} 외부 개입 감지\n"
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
        asyncio.create_task(trigger_realtime_sync())

# --- 백그라운드 루프 엔진 ---
def _get_admin_prefs() -> dict:
    from core.db import get_db, is_db_available
    base = dict(UserManager.DEFAULT_PREFERENCES)
    if is_db_available():
        try:
            rows = get_db().table("system_config").select("key,value").in_(
                "key", ["poll_active_interval", "poll_no_order_interval", "signal_analysis_interval"]
            ).execute().data
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
            prefs = _get_admin_prefs()
            order_manager.reload_from_db()
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
        if now - _ops_alert_last_sent.get(issue, 0) >= _OPS_ALERT_COOLDOWN_SECONDS
    ]
    if not due_issues:
        return
    msg = "🚨 <b>운영 알림</b>\n\n" + "\n".join(f"• {issue}" for issue in due_issues)
    try:
        await application.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
        for issue in due_issues:
            _ops_alert_last_sent[issue] = now
    except Exception as e:
        _log.warning("Ops health alert failed", exc_info=e, extra={"event": "ops_alert_failed"})

async def signal_analysis_loop(application):
    _log.info("Signal analysis loop started", extra={"event": "signal_analysis_loop_start"})
    await asyncio.sleep(5)
    _ops_check_counter = 0
    while True:
        try:
            prefs = _get_admin_prefs()
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
    """봇 시작 시 미완료된 전략 주문들을 점검하고 복구"""
    _log.info("Startup recovery started", extra={"event": "startup_recovery_start"})
    all_orders = list(order_manager.orders)
    recovered_count = 0
    
    for ord in all_orders:
        # 매수 주문인데 거래소 상태 확인
        res = await exchange_adapter.get_order_status(ord['user_id'], ord['exchange'], ord['uuid'], ord.get("ticker"))
        if res and res['state'] == 'done':
            # 매수는 완료되었으나 봇이 꺼져서 매도 주문을 못 낸 경우 복구
            if ord['side'] == 'bid' and ord['strategy'] == 'rsitrade' and ord['linked_to']:
                # (sync_orders와 동일한 로직으로 매도 주문 생성 시도)
                recovered_count += 1
                # 로직 중복 방지를 위해 sync_orders가 다음 루프에서 처리하도록 filled_volume만 0으로 세팅되어 있다면 
                # 자연스럽게 sync_orders에서 처리됩니다.
    
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

async def _verify_webhook_request(request: _web.Request) -> bool:
    """웹훅 요청의 HMAC 서명 및 IP 화이트리스트 검증"""
    import hmac
    import hashlib
    import time

    # 1. IP 화이트리스팅 검증
    allowed_ips_str = os.environ.get("ALLOWED_WEBHOOK_IPS", "").strip()
    if allowed_ips_str:
        allowed_ips = [ip.strip() for ip in allowed_ips_str.split(",") if ip.strip()]
        client_ip = request.remote
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            client_ip = xff.split(",")[0].strip()
        if client_ip not in allowed_ips and client_ip != "127.0.0.1":
            _log.warning(f"Webhook blocked: IP {client_ip} is not in whitelist")
            return False

    # 2. HMAC 서명 검증
    api_key = os.environ.get("MANAGER_API_KEY", "")
    if not api_key:
        return False

    timestamp = request.headers.get("X-Timestamp")
    signature = request.headers.get("X-Signature")

    if not timestamp or not signature:
        _log.warning("Webhook blocked: Missing X-Timestamp or X-Signature headers")
        return False

    # 시간 오차 검증 (리플레이 공격 방지, 5분 허용)
    try:
        req_time = int(timestamp)
        if abs(int(time.time()) - req_time) > 300:
            _log.warning("Webhook blocked: Timestamp drift too large")
            return False
    except ValueError:
        return False

    # 바디 페이로드 읽기
    body_bytes = await request.read()

    # 예상 서명 계산
    msg = timestamp.encode("utf-8") + body_bytes
    expected_sig = hmac.new(api_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        _log.warning("Webhook blocked: Signature verification failed")
        return False

    return True

async def _internal_notify_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        app = request.app["bot_application"]
        await app.bot.send_message(
            chat_id=data["chat_id"],
            text=data["text"],
            parse_mode=data.get("parse_mode", "HTML"),
        )
    except Exception as e:
        _log.warning("internal notify failed", exc_info=e, extra={"event": "notify_error"})
        return _web.Response(status=500, text=str(e))
    return _web.Response(text="ok")

async def trigger_realtime_sync():
    """매니저의 /api/realtime/trigger를 호출하여 프론트엔드 실시간 갱신을 트리거합니다."""
    manager_url = os.environ.get("MANAGER_BACKEND_URL", "http://localhost:8000")
    api_key = os.environ.get("MANAGER_API_KEY", "")
    if not api_key:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            headers = {"X-API-Key": api_key}
            async with session.post(f"{manager_url}/api/realtime/trigger", headers=headers, json={"event": "refresh"}) as resp:
                if resp.status != 200:
                    _log.warning(f"Failed to trigger realtime sync, status: {resp.status}")
    except Exception as e:
        _log.warning("Error triggering realtime sync", exc_info=e)

async def _internal_execute_grid_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        user_id = str(data["user_id"])
        ex = data["exchange"].lower()
        tk = data["ticker"].upper()
        s_p = float(data["start_price"])
        e_p = float(data["end_price"])
        ct = int(data["count"])
        val = float(data["budget"])

        user = user_manager.get_user(user_id)
        if not user:
            return _web.Response(status=404, text="User not found")

        ok, error_msg = validate_max_order(user, val / ct)
        if not ok:
            return _web.Response(status=400, text=error_msg)

        if ex == "kis" and not is_kis_regular_session():
            return _web.Response(status=400, text="한국투자증권 정규장 시간이 아닙니다.")

        app = request.app["bot_application"]
        group_no = order_manager.get_next_group_no(user_id)

        async def run_grid():
            await execute_grid_orders(
                exchange_adapter=exchange_adapter, order_manager=order_manager,
                user_id=user_id, exchange=ex, ticker=tk,
                start_price=s_p, end_price=e_p, count=ct, budget_or_volume=val,
                is_sell=False, group_no=group_no,
                bot=app.bot, notify_chat_id=user_id,
                trigger_sync_fn=trigger_realtime_sync,
            )

        asyncio.create_task(run_grid())
        return _web.Response(text="Grid execution started")
    except Exception as e:
        _log.warning("Internal grid execution failed", exc_info=e)
        return _web.Response(status=500, text=str(e))

async def _internal_execute_rsitrade_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        user_id = str(data["user_id"])
        ex = data["exchange"].lower()
        tk = data["ticker"].upper()
        b_rsi = str(data["buy_rsi_range"])
        s_rsi = str(data["sell_rsi_range"])
        ct = int(data["count"])
        bg = float(data["budget"])
        dca_mode = bool(data.get("weighted", False))

        user = user_manager.get_user(user_id)
        if not user:
            return _web.Response(status=404, text="User not found")

        if ex == "kis" and get_user_rsi_interval(user) != "day":
            return _web.Response(status=400, text="한투 KIS는 일봉(day) 기준 RSI만 지원합니다.")

        dca_weights = get_dca_weights(ct) if dca_mode else None
        per_order_budgets = [bg * w for w in dca_weights] if dca_weights else [bg / ct] * ct

        ok, error_msg = validate_max_order(user, max(per_order_budgets))
        if not ok:
            return _web.Response(status=400, text=error_msg)

        min_amt = exchange_adapter.get_min_order_amount(ex)
        if min(per_order_budgets) < min_amt:
            return _web.Response(status=400, text=f"건당 주문 금액이 거래소 최소 주문 금액({min_amt:,.0f}원)보다 작습니다.")

        app = request.app["bot_application"]
        group_no = order_manager.get_next_group_no(user_id)

        async def run_rsitrade():
            await execute_rsitrade_orders(
                exchange_adapter=exchange_adapter, order_manager=order_manager, signal_engine=signal_engine,
                user_id=user_id, exchange=ex, ticker=tk,
                buy_rsi_range=b_rsi, sell_rsi_range=s_rsi,
                count=ct, per_order_budgets=per_order_budgets,
                user=user, group_no=group_no, bot=app.bot, notify_chat_id=user_id,
                trigger_sync_fn=trigger_realtime_sync,
            )

        asyncio.create_task(run_rsitrade())
        return _web.Response(text="RSITrade execution started")
    except Exception as e:
        _log.warning("Internal rsitrade execution failed", exc_info=e)
        return _web.Response(status=500, text=str(e))


async def _internal_execute_sgrid_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        user_id = str(data["user_id"])
        ex = data["exchange"].lower()
        tk = data["ticker"].upper()
        s_p = float(data["start_price"])
        e_p = float(data["end_price"])
        ct = int(data["count"])
        total_vol = float(data["total_volume"])

        user = user_manager.get_user(user_id)
        if not user:
            return _web.Response(status=404, text="User not found")

        if ex == "kis" and not is_kis_regular_session():
            return _web.Response(status=400, text="한국투자증권 정규장 시간이 아닙니다.")

        if ex == "kis" and int(total_vol) < ct:
            return _web.Response(status=400, text=f"총 수량({int(total_vol)}주)이 주문 개수({ct})보다 작습니다.")

        app = request.app["bot_application"]
        group_no = order_manager.get_next_group_no(user_id)

        async def run_sgrid():
            await execute_grid_orders(
                exchange_adapter=exchange_adapter, order_manager=order_manager,
                user_id=user_id, exchange=ex, ticker=tk,
                start_price=s_p, end_price=e_p, count=ct, budget_or_volume=total_vol,
                is_sell=True, group_no=group_no,
                bot=app.bot, notify_chat_id=user_id,
                trigger_sync_fn=trigger_realtime_sync,
            )

        asyncio.create_task(run_sgrid())
        return _web.Response(text="sGrid execution started")
    except Exception as e:
        _log.warning("Internal sgrid execution failed", exc_info=e)
        return _web.Response(status=500, text=str(e))


async def _internal_cancel_order_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        user_id = data["user_id"]
        exchange = data["exchange"]
        uuid = data["uuid"]
        ticker = data["ticker"]
        ok = await exchange_adapter.cancel_order(user_id, exchange, uuid, ticker)
        if ok:
            order_manager.remove_order(uuid)
        import json as _json
        return _web.Response(text=_json.dumps({"ok": bool(ok)}), content_type="application/json")
    except Exception as e:
        _log.warning("internal cancel_order failed", exc_info=e, extra={"event": "cancel_order_error"})
        return _web.Response(status=500, text=str(e))


async def post_init(application):
    """봇 초기화 후 백그라운드 태스크 실행"""
    global _order_wake_event, _notify_runner
    _order_wake_event = asyncio.Event()
    
    def _on_order_added():
        _order_wake_event.set()
        asyncio.create_task(trigger_realtime_sync())
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
    asyncio.create_task(order_sync_loop(application))
    asyncio.create_task(signal_analysis_loop(application))
    
    # DB 장애 복구 후 데이터 동기화 백그라운드 태스크 기동
    from core.db_sync import start_sync_loop
    start_sync_loop()

    # 실시간 시세 WebSocket 수집 엔진 기동
    from core.websocket_client import init_ticker_engine
    init_ticker_engine(user_manager)


    if os.environ.get("MANAGER_API_KEY"):
        notify_app = _web.Application()
        notify_app["bot_application"] = application
        notify_app.router.add_post("/internal/notify", _internal_notify_handler)
        notify_app.router.add_post("/internal/execute_grid", _internal_execute_grid_handler)
        notify_app.router.add_post("/internal/execute_sgrid", _internal_execute_sgrid_handler)
        notify_app.router.add_post("/internal/execute_rsitrade", _internal_execute_rsitrade_handler)
        notify_app.router.add_post("/internal/cancel_order", _internal_cancel_order_handler)
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
    application.add_handler(CallbackQueryHandler(nl_intent_handlers.natural_language_confirm_callback, pattern="^nl(run|cancel)\\|"))
    
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
