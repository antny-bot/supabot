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
    _format_seconds,
)
from core.formatters import (
    _b, _i, _code,
    CMD_HELP,
    format_optional_krw, format_bool, escape_markdown_text,
    format_section, format_rsi_interval, format_config_value,
    format_safety_status, format_api_validation_status, build_secret_security_status,
    build_config_view, build_report_view,
    build_start_menu_message, build_help_message,
    build_account_summary, build_manual_order_confirm_message,
    build_grid_preview_lines, build_rsi_preview_lines,
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
    ("cancel", "주문 일괄 취소"),
    ("grid", "가격 범위 분할 매수"),
    ("sgrid", "수량 분할 매도"),
    ("rsitrade", "RSI 순환 매매"),
    # 감시
    ("watch", "RSI 감시 종목 추가"),
    ("unwatch", "RSI 감시 제거"),
    # 설정
    ("config", "거래소, LLM API 설정"),
]
ADMIN_BOT_COMMANDS = DEFAULT_BOT_COMMANDS

# Conversation States
SET_EXCHANGE, SET_ACCESS, SET_SECRET, SET_KIS_APP, SET_KIS_SECRET, SET_KIS_ACCOUNT, SET_KIS_PRODUCT, SET_KIS_ENV, SET_GEMINI_KEY = range(9)

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

def _build_llm_prompt(user_text, user):
    prefs = user.get("preferences", {})
    return (
        "Parse Korean trading bot text. Return JSON only.\n"
        "Never execute. Use null for unknown fields.\n"
        "Use help only for usage/capability questions.\n"
        "Missing required fields => clarify.\n"
        "Orders/cancel/config/watch need user confirm.\n"
        "Pending/reserved/tracked strategy orders => status. Real open/unfilled exchange orders => orders.\n"
        "매도/팔아 + RSI + 분할 => sgridrsi (sell_rsi_range only, buy_rsi_range=null).\n"
        "매수/사줘 + RSI + 분할, or RSI + 분할 (no direction) => rsitrade (buy_rsi_range).\n"
        "grid/gridrsi is price-range; RSI range goes to gridrsi/sgridrsi not grid.\n"
        "Missing sell_rsi_range for rsitrade/gridrsi => null; server uses default.\n"
        "Schema: {\"action\": string, \"exchange\": string|null, \"ticker\": string|null, "
        "\"price\": number|null, \"volume\": number|null, \"amount_krw\": number|null, "
        "\"start_price\": number|null, \"end_price\": number|null, \"count\": integer|null, "
        "\"buy_rsi_range\": string|null, \"sell_rsi_range\": string|null, "
        "\"config_key\": string|null, \"config_value\": string|null, \"question\": string|null}.\n"
        "Exchange: upbit|bithumb|kis|null. Korean stock => kis. Samsung => 005930. Crypto ticker: BTC/ETH/XRP.\n"
        f"Default exchange: {prefs.get('default_exchange', 'upbit')}.\n"
        f"Commands:\n{LLM_COMMAND_CATALOG}\n"
        f"User text: {user_text}"
    )

async def parse_natural_language_intent(text, user):
    api_key = user.get("llm", {}).get("gemini_api_key", "")
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=user.get("preferences", {}).get("llm_model", "gemini-2.5-flash-lite"),
            contents=_build_llm_prompt(text, user),
            config=config,
        )
        return json.loads(response.text)
    except Exception as e:
        _log.warning("Gemini intent parse error", exc_info=e, extra={"event": "gemini_parse_error"})
        return None

def _intent_args(intent, user):
    action = intent.get("action")
    exchange = intent.get("exchange") or user.get("preferences", {}).get("default_exchange", "upbit")
    ticker = intent.get("ticker")
    args = []
    if exchange:
        args.append(exchange)
    if ticker:
        args.append(str(ticker))
    if action in ["buy", "sell"]:
        if intent.get("price") is not None:
            args.append(str(intent["price"]))
        if intent.get("volume") is not None:
            args.append(str(intent["volume"]))
    elif action in ["grid"]:
        for key in ["start_price", "end_price", "count", "amount_krw"]:
            if intent.get(key) is not None:
                args.append(str(intent[key]))
    elif action in ["sgrid"]:
        for key in ["start_price", "end_price", "count", "volume"]:
            if intent.get(key) is not None:
                args.append(str(intent[key]))
    elif action in ("rsitrade", "gridrsi"):
        if intent.get("buy_rsi_range"):
            args.append(str(intent["buy_rsi_range"]))
        if intent.get("sell_rsi_range"):
            args.append(str(intent["sell_rsi_range"]))
        if intent.get("count") is not None:
            args.append(str(intent["count"]))
        if intent.get("amount_krw") is not None:
            args.append(str(intent["amount_krw"]))
    elif action == "sgridrsi":
        if intent.get("sell_rsi_range"):
            args.append(str(intent["sell_rsi_range"]))
        if intent.get("count") is not None:
            args.append(str(intent["count"]))
        if intent.get("amount_krw") is not None:
            args.append(str(intent["amount_krw"]))
    elif action == "config_set":
        args = ["set", str(intent.get("config_key") or ""), str(intent.get("config_value") or "")]
    return args

def _is_immediate_intent(action):
    return action in {"asset", "price", "orders", "status", "config_view", "history", "help", "rsi", "indicators"}

def _intent_summary(intent):
    action = intent.get("action")
    if action == "config_set":
        return f"설정 변경: {intent.get('config_key')} = {intent.get('config_value')}"
    if action in ("rsitrade", "gridrsi"):
        exchange = intent.get("exchange") or "upbit"
        _, ticker = parse_exchange_and_ticker([exchange, intent.get("ticker")] if intent.get("ticker") else [exchange], exchange)
        buy_range = intent.get("buy_rsi_range") or "기본값"
        sell_range = intent.get("sell_rsi_range") or "기본값"
        count = intent.get("count") or "기본"
        amount = intent.get("amount_krw")
        amount_text = f"{float(amount):,.0f}원" if amount is not None else "기본 예산"
        return (
            f"{exchange_display_name(exchange)} {ticker} / "
            f"매수 RSI {buy_range} / 매도 RSI {sell_range} / "
            f"{count}분할 / 총 {amount_text}"
        )
    if action == "sgridrsi":
        exchange = intent.get("exchange") or "upbit"
        _, ticker = parse_exchange_and_ticker([exchange, intent.get("ticker")] if intent.get("ticker") else [exchange], exchange)
        sell_range = intent.get("sell_rsi_range") or "기본값"
        count = intent.get("count") or "기본"
        amount = intent.get("amount_krw")
        amount_text = f"{float(amount):,.0f}원" if amount is not None else "기본 예산"
        return (
            f"{exchange_display_name(exchange)} {ticker} / "
            f"매도 RSI {sell_range} / "
            f"{count}분할 / 총 {amount_text}"
        )
    pieces = [str(action or "unknown")]
    for key in ["exchange", "ticker", "price", "volume", "amount_krw", "start_price", "end_price", "count", "buy_rsi_range", "sell_rsi_range"]:
        if intent.get(key) is not None:
            pieces.append(f"{key}={intent[key]}")
    return " / ".join(pieces)

def _clarify_message(text, intent):
    action = intent.get("action") if isinstance(intent, dict) else None
    if action in ("rsitrade", "gridrsi") or _looks_like_rsi_split_request(text):
        return "⚠️ RSI 전략은 종목, 매수 RSI, 예산을 확인할 수 있어야 합니다."
    if action == "sgridrsi":
        return "⚠️ RSI 매도 전략은 종목, 매도 RSI, 예산을 확인할 수 있어야 합니다."
    return "⚠️ 요청을 명령으로 해석하지 못했습니다. 종목, 거래소, 가격/수량을 더 구체적으로 입력해 주세요."

async def execute_query_intent(update, context, user, intent):
    action = intent.get("action")
    context.args = _intent_args(intent, user)
    if action == "asset":
        return await asset_command(update, context)
    if action == "price":
        return await price_command(update, context)
    if action == "orders":
        return await orders_command(update, context)
    if action == "status":
        return await status_command(update, context)
    if action == "history":
        return await history_command(update, context)
    if action == "config_view":
        return await update.message.reply_text(
            build_config_view(user, active_order_count=len(order_manager.orders)),
            parse_mode="HTML",
        )
    if action == "help":
        return await help_command(update, context)
    if action in ["rsi", "indicators"]:
        return await indicators_command(update, context)
    await update.message.reply_text("⚠️ 자연어 요청을 조회 명령으로 해석하지 못했습니다.")

async def execute_confirmed_intent(query, context, user, intent):
    user_id = str(query.from_user.id)
    action = intent.get("action")
    exchange = intent.get("exchange") or user.get("preferences", {}).get("default_exchange", "upbit")
    raw_ticker = intent.get("ticker")
    _, ticker = parse_exchange_and_ticker([exchange, raw_ticker] if raw_ticker else [exchange], exchange)

    if action == "config_set":
        key = str(intent.get("config_key") or "").strip().lower()
        raw_value = str(intent.get("config_value") or "").strip()
        if key in POLL_INTERVAL_KEYS:
            await query.edit_message_text("❌ 폴링 설정은 config/.env에서 직접 변경 후 재시작해주세요.")
            return
        value = parse_config_value(key, raw_value)
        validate_config_update(user, key, value)
        user_manager.update_preference(user_id, key, value)
        await query.edit_message_text(f"✅ {key} 설정을 {format_config_value(key, value)}(으)로 저장했습니다.")
        return

    if action in ["watch", "unwatch"]:
        if exchange == "kis" and get_user_rsi_interval(user) != "day":
            await query.edit_message_text(_KIS_RSI_MINUTE_ERROR)
            return
        changed = user_manager.add_watchlist(user_id, exchange, ticker) if action == "watch" else user_manager.remove_watchlist(user_id, exchange, ticker)
        label = "등록" if action == "watch" else "삭제"
        await query.edit_message_text(f"{'✅' if changed else 'ℹ️'} {exchange_display_name(exchange)} {ticker} 관심 종목 {label} 처리했습니다.")
        return

    if action == "cancel":
        orders = [o for o in order_manager.get_user_orders(user_id, exchange) if o["ticker"] == ticker]
        success = 0
        for order in orders:
            if await exchange_adapter.cancel_order(user_id, exchange, order["uuid"], order["ticker"]):
                order_manager.remove_order(order["uuid"])
                success += 1
            await asyncio.sleep(0.1)
        await query.edit_message_text(f"✅ {ticker} 취소 완료 ({success}/{len(orders)}건 성공)")
        return

    if action in ["buy", "sell"]:
        price = float(intent.get("price") or 0)
        volume = float(intent.get("volume") or 0)
        if exchange == "kis":
            volume = int(volume)
        if price <= 0 or volume <= 0:
            await query.edit_message_text("❌ 가격과 수량을 확인할 수 없어 주문을 중단합니다.")
            return
        ok, error_msg = validate_max_order(user, price * volume)
        if not ok:
            await query.edit_message_text(error_msg)
            return
        side = "bid" if action == "buy" else "ask"
        res = await exchange_adapter.create_order(user_id, exchange, ticker, side, price, volume)
        if res and "uuid" in res:
            order_manager.add_order(user_id, exchange, ticker, res["uuid"], price, volume, side=side, strategy="manual")
            await query.edit_message_text(f"✅ {exchange_display_name(exchange)} {ticker} {'매수' if side == 'bid' else '매도'} 주문 완료\n주문ID: {res['uuid']}")
        else:
            append_operational_event("error", "natural_language_order", "order failed", f"{exchange} {ticker} {side}")
            await query.edit_message_text(f"❌ 주문 실패: {res}")
        return

    if action == "rsitrade":
        if exchange == "kis" and get_user_rsi_interval(user) != "day":
            await query.edit_message_text(_KIS_RSI_MINUTE_ERROR)
            return
        buy_range = intent.get("buy_rsi_range") or user["preferences"].get("rsi_buy_range", "25-30")
        sell_range = intent.get("sell_rsi_range") or user["preferences"].get("rsi_sell_range", "65-75")
        count = int(intent.get("count") or user["preferences"].get("rsi_order_count", 5))
        budget = float(intent.get("amount_krw") or user["preferences"].get("rsi_budget_krw") or 0)
        if budget <= 0:
            await query.edit_message_text("❌ RSI 전략 예산을 확인할 수 없어 주문을 중단합니다.")
            return
        await query.edit_message_text("🚀 자연어 RSI 전략 주문을 전송 중입니다...")
        b_start, b_end = parse_rsi_range(buy_range)
        s_start, s_end = parse_rsi_range(sell_range)
        budget_per_order = budget / count
        success = 0
        for i in range(count):
            target_rsi = interpolate_range(b_start, b_end, i, count)
            sell_target_rsi = interpolate_range(s_start, s_end, i, count)
            price = await signal_engine.get_price_by_rsi(exchange, ticker, target_rsi, side="bid", interval=get_user_rsi_interval(user), user_id=user_id)
            if not price:
                continue
            volume = round(budget_per_order / price, 4)
            if exchange == "kis":
                volume = int(volume)
            if volume <= 0:
                continue
            res = await exchange_adapter.create_order(user_id, exchange, ticker, "bid", price, volume)
            if res and "uuid" in res:
                order_manager.add_order(user_id, exchange, ticker, res["uuid"], price, volume, side="bid", strategy="rsitrade", target_rsi=target_rsi, linked_to=sell_target_rsi)
                success += 1
            await asyncio.sleep(0.2)
        await context.bot.send_message(chat_id=user_id, text=f"✅ `{ticker}` 자연어 RSI 전략 가동 완료! ({success}/{count}건 예약됨)")
        return

    if action == "sgridrsi":
        if exchange == "kis" and get_user_rsi_interval(user) != "day":
            await query.edit_message_text(_KIS_RSI_MINUTE_ERROR)
            return
        sell_range = intent.get("sell_rsi_range") or user["preferences"].get("rsi_sell_range", "65-75")
        count = int(intent.get("count") or user["preferences"].get("rsi_order_count", 5))
        budget = float(intent.get("amount_krw") or user["preferences"].get("rsi_budget_krw") or 0)
        if budget <= 0:
            await query.edit_message_text("❌ RSI 매도 전략 예산을 확인할 수 없어 주문을 중단합니다.")
            return
        await query.edit_message_text("🚀 자연어 RSI 매도 전략 주문을 전송 중입니다...")
        s_start, s_end = parse_rsi_range(sell_range)
        budget_per_order = budget / count
        success = 0
        for i in range(count):
            target_rsi = interpolate_range(s_start, s_end, i, count)
            price = await signal_engine.get_price_by_rsi(exchange, ticker, target_rsi, side="ask", interval=get_user_rsi_interval(user), user_id=user_id)
            if not price:
                continue
            volume = round(budget_per_order / price, 4)
            if exchange == "kis":
                volume = int(volume)
            if volume <= 0:
                continue
            res = await exchange_adapter.create_order(user_id, exchange, ticker, "ask", price, volume)
            if res and "uuid" in res:
                order_manager.add_order(user_id, exchange, ticker, res["uuid"], price, volume, side="ask", strategy="sgridrsi", target_rsi=target_rsi, linked_to=None)
                success += 1
            await asyncio.sleep(0.2)
        await context.bot.send_message(chat_id=user_id, text=f"✅ `{ticker}` 자연어 RSI 매도 전략 가동 완료! ({success}/{count}건 예약됨)")
        return

    await query.edit_message_text("⚠️ 이 자연어 요청은 아직 실행할 수 없습니다. /help에서 지원 명령을 확인해 주세요.")

async def build_rsi_price_points(user_id, user, exchange, ticker, buy_rsi_range, count):
    b_start, b_end = parse_rsi_range(buy_rsi_range)
    points = []
    for i in range(int(count)):
        target_rsi = interpolate_range(b_start, b_end, i, int(count))
        price = await signal_engine.get_price_by_rsi(
            exchange,
            ticker,
            target_rsi,
            side="bid",
            interval=get_user_rsi_interval(user),
            user_id=user_id,
        )
        if price:
            points.append((target_rsi, price))
    return points

async def build_rsi_sell_price_points(user_id, user, exchange, ticker, sell_rsi_range, count):
    s_start, s_end = parse_rsi_range(sell_rsi_range)
    points = []
    for i in range(int(count)):
        target_rsi = interpolate_range(s_start, s_end, i, int(count))
        price = await signal_engine.get_price_by_rsi(
            exchange,
            ticker,
            target_rsi,
            side="ask",
            interval=get_user_rsi_interval(user),
            user_id=user_id,
        )
        if price:
            points.append((target_rsi, price))
    return points

async def build_rsigrid_confirm_summary(user_id, user, intent):
    action = intent.get("action")
    exchange = intent.get("exchange") or user.get("preferences", {}).get("default_exchange", "upbit")
    _, ticker = parse_exchange_and_ticker([exchange, intent.get("ticker")] if intent.get("ticker") else [exchange], exchange)
    count = int(intent.get("count") or user["preferences"].get("rsi_order_count", 5))
    budget = float(intent.get("amount_krw") or user["preferences"].get("rsi_budget_krw") or 0)
    if not ticker or budget <= 0 or count <= 0:
        return None

    if action == "sgridrsi":
        sell_range = intent.get("sell_rsi_range") or user["preferences"].get("rsi_sell_range", "65-75")
        rsi_prices = await build_rsi_sell_price_points(user_id, user, exchange, ticker, sell_range, count)
        if not rsi_prices:
            return None
        preview_text = "\n".join(build_rsi_preview_lines(ticker, rsi_prices, budget, count))
        return (
            f"💰 RSI 매도 전략 확인\n\n"
            f"전략 설정\n"
            f"- 거래소: {exchange_display_name(exchange)}\n"
            f"- 종목: {ticker}\n"
            f"- 매도 RSI: {sell_range}\n"
            f"- 총예산: {budget:,.0f}원\n"
            f"- 분할: {count}개\n\n"
            f"예상 주문\n{preview_text}\n\n"
            f"실행 시점에 가격은 다시 계산될 수 있습니다.\n"
            f"위 내용으로 실행할까요?"
        )

    buy_range = intent.get("buy_rsi_range") or user["preferences"].get("rsi_buy_range", "25-30")
    sell_range = intent.get("sell_rsi_range") or user["preferences"].get("rsi_sell_range", "65-75")
    rsi_prices = await build_rsi_price_points(user_id, user, exchange, ticker, buy_range, count)
    if not rsi_prices:
        return None
    preview_text = "\n".join(build_rsi_preview_lines(ticker, rsi_prices, budget, count))
    return (
        f"🤖 RSI 거미줄 전략 확인\n\n"
        f"전략 설정\n"
        f"- 거래소: {exchange_display_name(exchange)}\n"
        f"- 종목: {ticker}\n"
        f"- 매수 RSI: {buy_range}\n"
        f"- 매도 RSI: {sell_range}\n"
        f"- 총예산: {budget:,.0f}원\n"
        f"- 분할: {count}개\n\n"
        f"예상 주문\n{preview_text}\n\n"
        f"실행 시점에 가격은 다시 계산될 수 있습니다.\n"
        f"위 내용으로 실행할까요?"
    )

@check_auth
async def asset_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "asset"): return
    user_id = str(update.effective_chat.id)
    if context.args:
        exchange = normalize_exchange(context.args[0])
        if not exchange:
            await update.message.reply_text("⚠️ 거래소는 업비트, 빗썸, 한투 중 하나로 입력해 주세요.")
            return
        exchanges = [exchange]
    else:
        exchanges = ["upbit", "bithumb", "kis"]
    min_display_krw = float(user["preferences"].get("asset_min_display_krw", 10000))
    
    status_msg = await update.message.reply_text("🔄 자산 정보를 불러오는 중입니다...")
    
    full_msg = "💰 <b>통합 자산 현황</b>\n\n"
    total_eval_krw = 0

    for ex in exchanges:
        if ex not in ["upbit", "bithumb", "kis"]: continue

        balances = await exchange_adapter.get_balances(user_id, ex)
        if balances is None:
            full_msg += f"❌ <b>{exchange_display_name(ex)}</b>: API 키가 설정되지 않았거나 오류 발생\n\n"
            continue

        if ex == "kis":
            full_msg += f"🏛️ <b>{exchange_display_name(ex)}</b> ({'실전' if balances.get('env') == 'real' else '모의'})\n"
            cash = float(balances.get("cash", 0))
            ex_eval = float(balances.get("total_eval", 0))
            full_msg += f"- 💵 예수금: {cash:,.0f}원\n"
            others_count = 0
            others_value = 0
            for stock in balances.get("stocks", []):
                value = float(stock.get("value", 0))
                if value > min_display_krw:
                    name = stock.get('name') or stock.get('code')
                    full_msg += f"- 📈 {name} ({stock.get('quantity', 0):,.0f}주)\n"
                    full_msg += f"   └ {value:,.0f}원\n"
                else:
                    others_count += 1
                    others_value += value
            if others_count > 0:
                full_msg += f"- 📦 기타 {others_count}개 종목: {others_value:,.0f}원\n"
            full_msg += f"   └ 계좌 평가액: {ex_eval:,.0f}원\n\n"
            total_eval_krw += ex_eval
            continue

        # 거래소별 현재가 정보 가져오기 (평가액 계산용)
        ticker_prices = await exchange_adapter.get_krw_ticker_prices(ex)

        full_msg += f"🏛️ <b>{ex.upper()}</b>\n"
        ex_eval = 0
        others_count = 0
        others_value = 0
        
        # 1차 루프: KRW 및 주요 자산 표시
        for b in balances:
            qty = float(b['balance']) + float(b['locked'])
            if qty <= 0: continue
            
            currency = b['currency']
            if currency == "KRW":
                ex_eval += qty
                full_msg += f"- 💵 KRW: {qty:,.0f}원\n"
            else:
                price = ticker_prices.get(currency, 0)
                value = qty * price
                ex_eval += value
                
                if value > min_display_krw:
                    full_msg += f"- 🪙 {currency} ({qty:.4f}개)\n"
                    if price > 0:
                        full_msg += f"   └ {value:,.0f}원\n"
                else:
                    others_count += 1
                    others_value += value
        
        # 소액 자산 요약 표시
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
    
    orders = order_manager.get_user_orders(user_id, exchange)
    if not orders:
        await update.message.reply_text("⏳ 봇이 추적 중인 거래소 미체결 주문은 없습니다.\nRSI/거미줄 전략 대기 상태는 /status에서 확인하세요.")
        return

    msg = "⏳ <b>현재 추적 중인 미체결 주문</b>\n\n"
    for ord in orders:
        msg += f"📌 <b>[{exchange_display_name(ord['exchange'])}]</b> {ord['ticker']}\n"
        msg += f"   └ {ord['price']:,.0f}원 ({ord['volume']:.4f}개)\n"

    await update.message.reply_text(msg, parse_mode="HTML")

@check_auth
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "cancel"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 취소할 종목을 입력하세요. 예: `/cancel KRW-BTC` 또는 `/cancel upbit KRW-BTC`")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)

    orders = [o for o in order_manager.get_user_orders(user_id, exchange) if o['ticker'] == ticker]
    if not orders:
        await update.message.reply_text(f"ℹ️ {exchange_display_name(exchange)}에서 추적 중인 {ticker} 주문이 없습니다.")
        return

    status_msg = await update.message.reply_text(f"🛑 {exchange_display_name(exchange)} {ticker} 주문 {len(orders)}건 취소 중...")
    
    success_count = 0
    for ord in orders:
        if await exchange_adapter.cancel_order(user_id, exchange, ord['uuid'], ord['ticker']):
            order_manager.remove_order(ord['uuid'])
            success_count += 1
        await asyncio.sleep(0.1)

    await status_msg.edit_text(f"✅ {ticker} 취소 완료 ({success_count}/{len(orders)}건 성공)")

# --- /config: API 키 설정 대화형 핸들러 ---
async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_details_help(update, "config"):
        return ConversationHandler.END

    user_id = str(update.effective_chat.id)
    user = user_manager.get_user(user_id)
    
    if not user or not user["is_active"]:
        await update.message.reply_text("👋 먼저 /start 명령어로 등록 및 승인을 완료해 주세요.")
        return ConversationHandler.END

    args = context.args
    if args and args[0].lower() in ["-v", "-view", "--view"]:
        await update.message.reply_text(
            build_config_view(user, active_order_count=len(order_manager.orders)),
            parse_mode="HTML",
        )
        return ConversationHandler.END

    # Shorthand: /config <key> <value>  (equivalent to /config set <key> <value>)
    if args and len(args) >= 2 and args[0].lower() not in ("-v", "-view", "--view", "set"):
        args = ["set"] + list(args)
        context.args = args

    if args and args[0].lower() == "set":
        if len(args) < 3:
            await update.message.reply_text("⚠️ 사용법: /config set [항목] [값]\n예: /config set rsi_budget_krw 100만")
            return ConversationHandler.END
        key = args[1].strip().lower()
        raw_value = " ".join(args[2:]).strip()
        if key in POLL_INTERVAL_KEYS:
            await update.message.reply_text("❌ 폴링 설정은 config/.env에서 직접 변경 후 재시작해주세요.")
            return ConversationHandler.END
        try:
            value = parse_config_value(key, raw_value)
            validate_config_update(user, key, value)
        except (ValueError, TypeError) as e:
            await update.message.reply_text(f"❌ 설정 저장 실패: {e}")
            return ConversationHandler.END
        user_manager.update_preference(user_id, key, value)
        formatted = format_config_value(key, value)
        await update.message.reply_text(f"✅ {key} 설정을 {formatted}(으)로 저장했습니다.")
        return ConversationHandler.END

    if args:
        await update.message.reply_text("⚠️ 알 수 없는 /config 옵션입니다. 사용법은 /config -h를 확인하세요.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Upbit", callback_data="conf_upbit"),
         InlineKeyboardButton("Bithumb", callback_data="conf_bithumb")],
        [InlineKeyboardButton("한국투자증권", callback_data="conf_kis")],
        [InlineKeyboardButton("Gemini API 키", callback_data="conf_gemini")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        build_config_view(user, active_order_count=len(order_manager.orders)),
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    return SET_EXCHANGE

async def config_exchange_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    exchange = query.data.split("_")[1]
    if exchange == "gemini":
        await query.edit_message_text("🔑 Gemini API 키를 입력해 주세요. 입력 메시지는 저장 후 삭제됩니다.")
        return SET_GEMINI_KEY
    context.user_data["temp_exchange"] = exchange
    if exchange == "kis":
        await query.edit_message_text("🔑 한국투자증권 App Key를 입력해 주세요.")
        return SET_KIS_APP
    await query.edit_message_text(f"🔑 {exchange.upper()}의 Access Key를 입력해 주세요.")
    return SET_ACCESS

async def set_gemini_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    api_key = update.message.text.strip()
    try: await update.message.delete()
    except: pass
    if not api_key:
        await update.message.reply_text("⚠️ Gemini API 키가 비어 있습니다. /config에서 다시 시도해 주세요.")
        return ConversationHandler.END
    try:
        user_manager.update_gemini_api_key(user_id, api_key)
    except ValueError as e:
        await update.message.reply_text(f"❌ 보안 키 설정 오류: {e}")
        return ConversationHandler.END
    await update.message.reply_text("✅ Gemini API 키를 저장했습니다. /config set llm_enabled on으로 자연어 기능을 켤 수 있습니다.")
    return ConversationHandler.END

async def set_access_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["temp_access"] = update.message.text
    try: await update.message.delete()
    except: pass
    await update.message.reply_text("🔒 이제 Secret Key를 입력해 주세요.")
    return SET_SECRET

async def set_secret_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    exchange = context.user_data.get("temp_exchange")
    access = context.user_data.get("temp_access")
    secret = update.message.text
    
    try: await update.message.delete()
    except: pass

    try:
        user_manager.update_exchange_keys(user_id, exchange, access, secret)
    except ValueError as e:
        await update.message.reply_text(f"❌ 보안 키 설정 오류: {e}")
        return ConversationHandler.END
    status_msg = await update.message.reply_text(f"⏳ {exchange.upper()} API 키 유효성을 검증하는 중...")
    
    is_valid = await exchange_adapter.validate_api_keys(user_id, exchange)
    user_manager.update_api_validation_status(user_id, exchange, is_valid)
    if is_valid:
        await status_msg.edit_text(f"✅ {exchange.upper()} API 키 설정이 완료되었습니다!")
    else:
        append_operational_event("warning", "api_validation", "API key validation failed", exchange)
        await status_msg.edit_text(f"⚠️ {exchange.upper()} API 키 검증에 실패했습니다. 키를 다시 확인해 주세요.")
    
    return ConversationHandler.END

async def set_kis_app_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["temp_kis_app"] = update.message.text.strip()
    try: await update.message.delete()
    except: pass
    await update.message.reply_text("🔒 한국투자증권 App Secret을 입력해 주세요.")
    return SET_KIS_SECRET

async def set_kis_secret_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["temp_kis_secret"] = update.message.text.strip()
    try: await update.message.delete()
    except: pass
    await update.message.reply_text("🏦 계좌번호 앞 8자리를 입력해 주세요. 예: 12345678")
    return SET_KIS_ACCOUNT

async def set_kis_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    account_no = update.message.text.strip().replace("-", "")
    if not account_no.isdigit() or len(account_no) != 8:
        await update.message.reply_text("⚠️ 계좌번호 앞 8자리를 숫자로 입력해 주세요. 예: 12345678")
        return SET_KIS_ACCOUNT
    context.user_data["temp_kis_account"] = account_no
    try: await update.message.delete()
    except: pass
    await update.message.reply_text("📌 계좌상품코드 2자리를 입력해 주세요. 국내주식 종합계좌는 보통 01입니다.")
    return SET_KIS_PRODUCT

async def set_kis_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product_code = update.message.text.strip()
    if not product_code.isdigit() or len(product_code) != 2:
        await update.message.reply_text("⚠️ 계좌상품코드는 숫자 2자리여야 합니다. 예: 01")
        return SET_KIS_PRODUCT
    context.user_data["temp_kis_product"] = product_code
    await update.message.reply_text("🧪 투자 환경을 입력해 주세요: paper(모의) 또는 real(실전)")
    return SET_KIS_ENV

async def set_kis_env(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    raw_env = update.message.text.strip().lower()
    if raw_env in ["paper", "demo", "mock", "모의", "모의투자"]:
        env = "paper"
    elif raw_env in ["real", "prod", "실전", "실전투자"]:
        env = "real"
    else:
        await update.message.reply_text("⚠️ 투자 환경은 paper(모의) 또는 real(실전)로 입력해 주세요.")
        return SET_KIS_ENV

    app_key = context.user_data.get("temp_kis_app", "")
    app_secret = context.user_data.get("temp_kis_secret", "")
    account_no = context.user_data.get("temp_kis_account", "")
    product_code = context.user_data.get("temp_kis_product", "01")

    try:
        user_manager.update_kis_keys(user_id, app_key, app_secret, account_no, product_code, env)
    except ValueError as e:
        await update.message.reply_text(f"❌ 보안 키 설정 오류: {e}")
        return ConversationHandler.END
    status_msg = await update.message.reply_text("⏳ 한국투자증권 API 설정을 검증하는 중...")
    is_valid = await exchange_adapter.validate_api_keys(user_id, "kis")
    user_manager.update_api_validation_status(user_id, "kis", is_valid)
    env_name = "실전" if env == "real" else "모의"
    if is_valid:
        await status_msg.edit_text(f"✅ 한국투자증권 API 설정이 완료되었습니다. ({env_name})")
    else:
        append_operational_event("warning", "api_validation", "KIS API validation failed", env_name)
        await status_msg.edit_text("⚠️ 한국투자증권 API 검증에 실패했습니다. App Key, App Secret, 계좌번호, 환경을 확인해 주세요.")

    for key in ["temp_kis_app", "temp_kis_secret", "temp_kis_account", "temp_kis_product"]:
        context.user_data.pop(key, None)
    return ConversationHandler.END

async def cancel_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ 설정이 취소되었습니다.")
    return ConversationHandler.END

# --- /grid: 거미줄 매수 핸들러 (Confirm 로직 포함) ---
@check_auth
async def grid_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "grid"): return
    args = context.args
    if len(args) < 5:
        await update.message.reply_text(
            "⚠️ 사용법 부족\n구문: /grid [거래소] [종목] [시작가] [종료가] [개수] [총예산]"
        )
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)

    # args 인덱스 보정 (거래소 명시 여부에 따라 파라미터 위치가 다름)
    offset = 2 if is_exchange_token(args[0], exchange) else 1

    try:
        start_p, end_p = parse_number(args[offset]), parse_number(args[offset+1])
        count, budget = int(args[offset+2]), parse_number(args[offset+3])
        if count <= 0:
            raise ValueError
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ 숫자 형식의 파라미터가 잘못되었습니다.")
        return

    ok, error_msg = validate_max_order(user, budget / count)
    if not ok:
        await update.message.reply_text(error_msg)
        return

    # KIS: 정규장 여부 및 최소 수량 사전 안내
    kis_notice = ""
    if exchange == "kis":
        if not is_kis_regular_session():
            await update.message.reply_text("⚠️ 현재 한국투자증권 정규장 시간이 아닙니다. 정규장(평일 09:00-15:35)에만 주문이 실행됩니다.")
            return
        mid_price = (start_p + end_p) / 2
        if mid_price > 0 and int((budget / count) / mid_price) < 1:
            await update.message.reply_text("⚠️ 예산 대비 가격이 높아 주문당 수량이 0주가 됩니다. 예산을 늘리거나 주문 개수를 줄여주세요.")
            return
        kis_notice = "\n⚠️ 한국투자증권: 주문 수량은 정수(주)로 처리됩니다."

    confirm_data = f"gridrun|{exchange}|{ticker}|{start_p}|{end_p}|{count}|{budget}"
    keyboard = [
        [InlineKeyboardButton("✅ 주문 실행", callback_data=confirm_data),
         InlineKeyboardButton("❌ 취소", callback_data="grid_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    preview_text = "\n".join(build_grid_preview_lines(ticker, start_p, end_p, count, budget))
    summary = (
        f"🕸️ 거미줄 매수 주문 확인\n\n"
        f"주문 설정\n"
        f"- 거래소: {exchange.upper()}\n"
        f"- 종목: {ticker}\n"
        f"- 가격 범위: {start_p:,.0f} ~ {end_p:,.0f}\n"
        f"- 주문 개수: {count}회\n"
        f"- 총 예산: {budget:,.0f}원\n\n"
        "위 내용으로 주문을 진행할까요?"
        f"{kis_notice}"
    )
    summary += f"\n\n예상 주문\n{preview_text}"
    await update.message.reply_text(summary, reply_markup=reply_markup)

@check_auth
async def sgrid_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "sgrid"): return
    args = context.args
    if len(args) < 5:
        await update.message.reply_text(
            "⚠️ 사용법 부족\n구문: /sgrid [거래소] [종목] [시작가] [종료가] [개수] [총수량]"
        )
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)
    offset = 2 if is_exchange_token(args[0], exchange) else 1

    try:
        start_p, end_p = parse_number(args[offset]), parse_number(args[offset+1])
        count, total_vol = int(args[offset+2]), parse_number(args[offset+3])
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ 숫자 형식의 파라미터가 잘못되었습니다.")
        return

    # KIS: 정규장 여부 및 최소 수량 확인
    kis_notice = ""
    if exchange == "kis":
        if not is_kis_regular_session():
            await update.message.reply_text("⚠️ 현재 한국투자증권 정규장 시간이 아닙니다. 정규장(평일 09:00-15:35)에만 주문이 실행됩니다.")
            return
        if int(total_vol) < count:
            await update.message.reply_text(f"⚠️ 총 수량({int(total_vol)}주)이 주문 개수({count})보다 작아 주문당 수량이 0주가 됩니다.")
            return
        kis_notice = "\n⚠️ 한국투자증권: 주문 수량은 정수(주)로 처리됩니다."

    vol_text = f"{int(total_vol):,}주" if exchange == "kis" else f"{total_vol:.4f}개"
    confirm_data = f"sgridrun|{exchange}|{ticker}|{start_p}|{end_p}|{count}|{total_vol}"
    keyboard = [
        [InlineKeyboardButton("✅ 매도 실행", callback_data=confirm_data),
         InlineKeyboardButton("❌ 취소", callback_data="grid_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    summary = (
        f"🕸️ 거미줄 매도 주문 확인\n\n"
        f"주문 설정\n"
        f"- 거래소: {exchange.upper()}\n"
        f"- 종목: {ticker}\n"
        f"- 가격 범위: {start_p:,.0f} ~ {end_p:,.0f}\n"
        f"- 주문 개수: {count}회\n"
        f"- 총 수량: {vol_text}\n\n"
        "위 내용으로 분할 매도를 진행할까요?"
        f"{kis_notice}"
    )
    await update.message.reply_text(summary, reply_markup=reply_markup)

async def grid_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "grid_cancel":
        await query.edit_message_text("❌ 주문이 취소되었습니다.")
        return

    if query.data.startswith("gridrun") or query.data.startswith("sgridrun"):
        is_sell = query.data.startswith("sgridrun")
        _, ex, tk, s_p, e_p, ct, val = query.data.split("|")
        s_p, e_p, ct, val = float(s_p), float(e_p), int(ct), float(val)
        user_id = str(query.from_user.id)
        user = user_manager.get_user(user_id)
        if not user:
            await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
            return
        if not is_sell:
            ok, error_msg = validate_max_order(user, val / ct)
            if not ok:
                await query.edit_message_text(error_msg)
                return
        
        action_name = "매도" if is_sell else "매수"
        await query.edit_message_text(f"🚀 {ex.upper()}에 거미줄 {action_name} 주문 전송을 시작합니다...")
        
        # KIS 정규장 재확인 (confirm 시점에 다시 체크)
        if ex == "kis" and not is_kis_regular_session():
            await query.edit_message_text("⚠️ 현재 한국투자증권 정규장 시간이 아닙니다. 주문을 실행할 수 없습니다.")
            return

        price_step = (e_p - s_p) / (ct - 1) if ct > 1 else 0
        success_count = 0
        skipped_count = 0

        for i in range(ct):
            target_price = s_p + (price_step * i)
            target_price = ExchangeAdapter.adjust_price_to_tick(target_price)

            if is_sell:
                raw_vol = val / ct
                volume = int(raw_vol) if ex == "kis" else round(raw_vol, 4)
                res = await exchange_adapter.create_order(user_id, ex, tk, "ask", target_price, volume)
            else:
                raw_vol = (val / ct) / target_price if target_price else 0
                volume = int(raw_vol) if ex == "kis" else round(raw_vol, 4)
                res = await exchange_adapter.buy_limit_order(user_id, ex, tk, target_price, volume)

            if ex == "kis" and volume <= 0:
                skipped_count += 1
                continue

            if res and 'uuid' in res:
                order_manager.add_order(
                    user_id, ex, tk, res['uuid'], target_price, volume,
                    side="ask" if is_sell else "bid",
                    strategy="sgrid" if is_sell else "grid",
                )
                success_count += 1

            await asyncio.sleep(0.2)

        result_msg = f"✅ `{tk}` 거미줄 {action_name} 완료! ({success_count}/{ct}건 성공)\n백그라운드에서 체결을 감시합니다."
        if skipped_count:
            result_msg += f"\n⚠️ {skipped_count}건은 수량 부족(0주)으로 건너뜀."
        await context.bot.send_message(chat_id=user_id, text=result_msg)

# --- /watch & /unwatch: 관심 종목 관리 ---
@check_auth
async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "watch"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 감시할 종목을 입력하세요. 예: `/watch KRW-BTC` 또는 `/watch bithumb BTC`")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)

    if not await ensure_rsi_supported(update, user, exchange):
        return

    if user_manager.add_watchlist(user_id, exchange, ticker):
        await update.message.reply_text(f"✅ {exchange.upper()}의 {ticker}가 관심 종목에 등록되었습니다. RSI 시그널을 감시합니다.")
    else:
        await update.message.reply_text(f"ℹ️ {ticker}는 이미 관심 종목에 등록되어 있습니다.")

@check_auth
async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "unwatch"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 삭제할 종목을 입력하세요. 예: `/unwatch KRW-BTC`")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)

    if not await ensure_rsi_supported(update, user, exchange):
        return

    if user_manager.remove_watchlist(user_id, exchange, ticker):
        await update.message.reply_text(f"✅ {exchange.upper()}의 {ticker}가 관심 종목에서 삭제되었습니다.")
    else:
        await update.message.reply_text(f"ℹ️ 관심 종목 목록에 {ticker}가 없습니다.")

@check_auth
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "price"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 종목을 입력하세요. 예: /price KRW-BTC 또는 /p KRW-ETH")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)

    ticker_data, indicators = await asyncio.gather(
        exchange_adapter.get_ticker(exchange, ticker, user_id=user_id),
        signal_engine.get_indicators(exchange, ticker, interval="day", user_id=user_id),
        return_exceptions=True,
    )

    if isinstance(ticker_data, Exception) or not ticker_data:
        await update.message.reply_text(f"❌ {exchange_display_name(exchange)}에서 {ticker} 정보를 찾을 수 없습니다.")
        return
    if isinstance(indicators, Exception):
        indicators = None

    # 업비트/빗썸 공통 필드 매핑
    price = float(ticker_data.get('trade_price', 0))
    change_rate = float(ticker_data.get('change_rate', 0)) * 100
    change_price = float(ticker_data.get('change_price', 0))
    high = float(ticker_data.get('high_price', 0))
    low = float(ticker_data.get('low_price', 0))
    volume = float(ticker_data.get('acc_trade_price_24h', 0))

    change_emoji = "📈" if change_rate > 0 else "📉" if change_rate < 0 else "➖"

    msg = (
        f"📊 <b>[{exchange_display_name(exchange)}] {ticker}</b> 실시간 시세\n\n"
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
                technical_parts.append(f"MA{period}: {ma_val:,.0f}원")
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
        exchange, ticker = parse_exchange_and_ticker(args[:-1], default_exchange)
    else:
        interval = user["preferences"].get("rsi_interval", "day")
        exchange, ticker = parse_exchange_and_ticker(args, default_exchange)

    await update.message.reply_text(f"⏳ {exchange_display_name(exchange)} {ticker} 지표 계산 중...")

    result = await signal_engine.get_indicators(exchange, ticker, interval=interval, user_id=user_id)
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
    
    exchange, ticker = parse_exchange_and_ticker(context.args, default_exchange)

    history = await exchange_adapter.get_order_history(user_id, exchange, ticker)
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

@check_auth
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "buy"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("⚠️ 사용법: /buy [거래소] [종목] [가격|market] [수량] (거래소 생략 시 업비트)")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)
    offset = 2 if is_exchange_token(args[0], exchange) else 1

    try:
        is_market = args[offset].lower() == "market"
        if is_market:
            price, volume, ord_type = 0.0, parse_number(args[offset + 1]), "market"
        else:
            price, volume, ord_type = parse_number(args[offset]), parse_number(args[offset + 1]), "limit"
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ 가격과 수량은 숫자여야 합니다.")
        return

    if not is_market:
        ok, error_msg = validate_max_order(user, price * volume)
        if not ok:
            await update.message.reply_text(error_msg)
            return

    token = create_manual_order_token(user_id, exchange, "bid", ticker, price, volume, ord_type=ord_type)
    confirm_data = f"manualrun|{token}"
    keyboard = [[InlineKeyboardButton("✅ 매수 실행", callback_data=confirm_data),
                 InlineKeyboardButton("❌ 취소", callback_data=f"manualcancel|{token}")]]
    await update.message.reply_text(
        build_manual_order_confirm_message(exchange, ticker, "bid", price, volume, user, ord_type=ord_type),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

@check_auth
async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "sell"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("⚠️ 사용법: /sell [거래소] [종목] [가격|market] [수량] (거래소 생략 시 업비트)")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)
    offset = 2 if is_exchange_token(args[0], exchange) else 1

    try:
        is_market = args[offset].lower() == "market"
        if is_market:
            price, volume, ord_type = 0.0, parse_number(args[offset + 1]), "market"
        else:
            price, volume, ord_type = parse_number(args[offset]), parse_number(args[offset + 1]), "limit"
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ 가격과 수량은 숫자여야 합니다.")
        return

    token = create_manual_order_token(user_id, exchange, "ask", ticker, price, volume, ord_type=ord_type)
    confirm_data = f"manualrun|{token}"
    keyboard = [[InlineKeyboardButton("✅ 매도 실행", callback_data=confirm_data),
                 InlineKeyboardButton("❌ 취소", callback_data=f"manualcancel|{token}")]]
    await update.message.reply_text(
        build_manual_order_confirm_message(exchange, ticker, "ask", price, volume, user, ord_type=ord_type),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def manual_order_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, token = query.data.split("|", 1)
    if action == "manualcancel":
        _pending_manual_orders.pop(token, None)
        await query.edit_message_text("❌ 주문이 취소되었습니다.")
        return

    user_id = str(query.from_user.id)
    user = user_manager.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
        return
    if not user.get("is_active"):
        await query.edit_message_text("❌ 사용자 인증을 확인할 수 없습니다.")
        return

    pending, error = pop_valid_manual_order(token, user_id)
    if error:
        await query.edit_message_text(f"⚠️ {error}")
        return
    exchange = pending["exchange"]
    side = pending["side"]
    ticker = pending["ticker"]
    price = float(pending["price"])
    volume = float(pending["volume"])
    ord_type = pending.get("ord_type", "limit")
    is_market = ord_type == "market"
    if side == "bid" and not is_market:
        ok, error_msg = validate_max_order(user, price * volume)
        if not ok:
            await query.edit_message_text(error_msg)
            return

    env_notice = ""
    if exchange == "kis":
        env = user.get("exchanges", {}).get("kis", {}).get("env", "paper")
        env_notice = f" ({'실전' if env == 'real' else '모의'})"
    action = "매수" if side == "bid" else "매도"
    order_type_label = "시장가 " if is_market else ""
    await query.edit_message_text(f"🚀 {exchange_display_name(exchange)} {ticker} {order_type_label}{action} 주문 전송 중{env_notice}...")

    res = await exchange_adapter.create_order(user_id, exchange, ticker, side, price, volume, ord_type=ord_type)
    if res and "uuid" in res:
        order_manager.add_order(user_id, exchange, ticker, res["uuid"], price, volume, side=side, strategy="manual")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ {exchange_display_name(exchange)} {ticker} {action} 주문 완료{env_notice}!\n주문ID: {res['uuid']}",
        )
    else:
        append_operational_event("error", "manual_order", "manual order failed", f"{exchange} {ticker} {side}")
        await context.bot.send_message(chat_id=user_id, text=f"❌ 주문 실패: {res}")

# --- 주문 동기화 및 자동 대응 엔진 ---
async def sync_orders(application):
    """현재 추적 중인 주문들의 상태를 거래소와 동기화하고 자동 대응 수행"""
    initial_state = [(o['uuid'], o.get('status'), o.get('filled_volume'), o.get('stop_price')) for o in order_manager.orders]
    all_orders = list(order_manager.orders)
    _price_cache = {}  # 동일 sync 사이클 내 중복 API 호출 방지: {(exchange, ticker): price}
    for ord in all_orders:
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
                expected_stop_price = ExchangeAdapter.adjust_price_to_tick(expected_stop_price)
                if expected_stop_price > float(ord["stop_price"]):
                    order_manager.update_order_stop_price(ord["uuid"], expected_stop_price)
                    ord["stop_price"] = expected_stop_price
                    _log.info(f"Trailing stop updated for {ticker}: stop_price -> {expected_stop_price:,.0f}원 (현재가: {current_price:,.0f}원)")

            if current_price and current_price < float(ord["stop_price"]):
                cancel_ok = await exchange_adapter.cancel_order(user_id, exchange, ord["uuid"], ticker)
                if cancel_ok:
                    remaining = float(ord["volume"]) - float(ord["filled_volume"])
                    sl_price = ExchangeAdapter.adjust_price_to_tick(current_price * 0.999)
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
                    if exchange == "kis":
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
                            ExchangeAdapter.adjust_price_to_tick(ord["price"] * (1 - stop_loss_pct / 100))
                            if stop_loss_pct > 0 else None
                        )
                        order_manager.add_order(user_id, exchange, ticker, s_res['uuid'], sell_price, sell_volume,
                                             side="ask", strategy="rsitrade_sell", target_rsi=target_rsi,
                                             stop_price=stop_price)
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

@check_auth
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "status"): return
    user_id = str(update.effective_chat.id)
    orders = order_manager.get_user_orders(user_id)
    
    if not orders:
        await update.message.reply_text("📊 현재 가동 중인 트레이딩 전략이 없습니다.\n거래소 실제 미체결 주문은 /orders에서 확인하세요.")
        return

    msg = "📊 트레이딩 전략 통합 대시보드\n\n"
    
    # 거래소별 그룹화
    status_names = {
        "wait": "대기",
        "partial": "부분체결",
        "market_closed": "장외 대기",
        "pending_reorder": "다음 정규장 재주문 예정",
        "done": "완료",
        "cancel": "취소",
    }
    for ex in ["upbit", "bithumb", "kis"]:
        ex_orders = [o for o in orders if o['exchange'] == ex]
        if not ex_orders: continue
        
        msg += f"🏛️ <b>{ex.upper()}</b>\n"

        tickers = sorted(list(set([o['ticker'] for o in ex_orders])))
        for tk in tickers:
            tk_orders = [o for o in ex_orders if o['ticker'] == tk]
            total = len(tk_orders)
            is_rsi = any(o['strategy'].startswith('rsitrade') for o in tk_orders)
            strategy_name = "RSI 순환 매매" if is_rsi else "거미줄 분할 매매"

            if is_rsi:
                # rsitrade_sell 주문 수 = 매수 체결 완료 후 매도 대기 중인 슬롯
                filled = len([o for o in tk_orders if o['strategy'] == 'rsitrade_sell'])
            else:
                filled = len([o for o in tk_orders if o['status'] == 'done'])

            prog_bar = "🔵" * filled + "⚪" * (total - filled)

            msg += f"• <b>{tk}</b> ({strategy_name})\n"
            if is_rsi and filled > 0:
                msg += f"  └ 진행: {prog_bar} ({total}건 추적, {filled}건 매수완료·매도대기)\n"
            else:
                msg += f"  └ 진행: {prog_bar} ({total}건 추적)\n"

            for i, o in enumerate(tk_orders[:3]):
                side_str = "매수" if o['side'] == 'bid' else "매도"
                target = f"RSI {o['target_rsi']}" if o['target_rsi'] else f"{o['price']:,.0f}원"
                state_text = status_names.get(o.get("status"), o.get("status", "대기"))
                msg += f"  ▫️ {i+1}. {side_str}[{state_text}]: {target}\n"
            if len(tk_orders) > 3: msg += "  ▫️ ... 그 외 생략\n"
        msg += "\n"

    msg += "ℹ️ 체결 및 외부 취소 시 실시간 알림이 전송됩니다.\n"
    msg += "📊 더 상세한 내역과 리포트는 [웹 대시보드]에서 확인하실 수 있습니다."
    await update.message.reply_text(msg, parse_mode="HTML")

@check_auth
async def rsitrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """RSI 기반 자동 순환 매매 설정"""
    if await check_details_help(update, "rsitrade"): return
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 사용법: /rsitrade [거래소] [종목] [매수RSI구간] [매도RSI구간] [횟수] [예산]\n예: /rsitrade BTC 25-30 65-75 5 100만")
        return

    user_id = str(update.effective_chat.id)
    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)
    if not ticker:
        await update.message.reply_text("⚠️ 종목은 반드시 입력해야 합니다. 예: /rsitrade BTC")
        return
    if not await ensure_rsi_supported(update, user, exchange):
        return

    offset = 2 if is_exchange_token(args[0], exchange) else 1
    
    try:
        preferences = user["preferences"]
        buy_rsi_range = args[offset] if len(args) > offset else preferences.get("rsi_buy_range", "25-30")
        _sell_arg = args[offset+1] if len(args) > offset + 1 else None
        sell_rsi_range = None if _sell_arg in ("-", "없음", "none") else (_sell_arg or preferences.get("rsi_sell_range", "65-75"))
        count = int(args[offset+2]) if len(args) > offset + 2 else int(preferences.get("rsi_order_count", 5))
        budget = parse_number(args[offset+3]) if len(args) > offset + 3 else preferences.get("rsi_budget_krw")
        if budget is None:
            await update.message.reply_text(
                "⚠️ RSI 전략 예산이 필요합니다. 명령어에 예산을 입력하거나 /config set rsi_budget_krw 100만으로 기본 예산을 저장하세요."
            )
            return
        budget = float(budget)

        b_start, b_end = parse_rsi_range(buy_rsi_range)
        if sell_rsi_range:
            parse_rsi_range(sell_rsi_range)
        if count <= 0:
            raise ValueError
    except (ValueError, TypeError, IndexError):
        await update.message.reply_text("⚠️ 파라미터 형식이 잘못되었습니다. (예: 25-30)")
        return

    ok, error_msg = validate_max_order(user, budget / count)
    if not ok:
        await update.message.reply_text(error_msg)
        return

    # 1. 거래소 최소 주문 금액 검증
    min_amt = exchange_adapter.get_min_order_amount(exchange)
    if (budget / count) < min_amt:
        await update.message.reply_text(f"❌ 예산이 너무 적습니다. 건당 최소 {min_amt:,.0f}원 이상이어야 합니다.")
        return

    status_msg = await update.message.reply_text(f"🔍 {ticker} RSI 가격 분석 중...")
    
    # 2. RSI 구간별 가격 역산
    buy_prices = []
    rsi_step = (b_end - b_start) / (count - 1) if count > 1 else 0
    for i in range(count):
        target_rsi = b_start + (rsi_step * i)
        p = await signal_engine.get_price_by_rsi(
            exchange,
            ticker,
            target_rsi,
            side="bid",
            interval=get_user_rsi_interval(user),
            user_id=user_id,
        )
        if p: buy_prices.append((target_rsi, p))
    
    if not buy_prices:
        await status_msg.edit_text("❌ RSI 가격 역산에 실패했습니다. 데이터를 불러올 수 없습니다.")
        return

    # 3. 요약 및 확인 버튼
    confirm_data = f"rsitrun|{exchange}|{ticker}|{buy_rsi_range}|{sell_rsi_range or '-'}|{count}|{budget}"
    keyboard = [[InlineKeyboardButton("✅ 전략 가동 시작", callback_data=confirm_data),
                 InlineKeyboardButton("❌ 취소", callback_data="grid_cancel")]]

    preview_text = "\n".join(build_rsi_preview_lines(ticker, buy_prices, budget, count))
    sell_line = f"- 익절(RSI): {sell_rsi_range} 목표\n" if sell_rsi_range else "- 익절 예약: 없음 (매수만)\n"
    auto_sell_note = "체결 시 자동으로 익절 주문이 예약됩니다. 시작할까요?" if sell_rsi_range else "매수만 진행합니다. 시작할까요?"
    summary = (
        f"🤖 RSI 순환 매매 전략 확인\n\n"
        f"전략 설정\n"
        f"- 거래소: {exchange.upper()}\n"
        f"- 종목: {ticker}\n"
        f"- 매집(RSI): {buy_rsi_range} ({buy_prices[0][1]:,.0f} ~ {buy_prices[-1][1]:,.0f}원)\n"
        f"{sell_line}"
        f"- 분할: {count}회 | 총예산: {budget:,.0f}원\n\n"
        f"{auto_sell_note}"
    )
    summary += f"\n\n예상 주문\n{preview_text}\n\n실행 시점에 가격은 다시 계산될 수 있습니다."
    await status_msg.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))

async def rsitrade_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, ex, tk, b_rsi, s_rsi, ct, bg = query.data.split("|")
    ct, bg = int(ct), float(bg)
    user_id = str(query.from_user.id)
    user = user_manager.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
        return
    if ex == "kis" and get_user_rsi_interval(user) != "day":
        await query.edit_message_text(_KIS_RSI_MINUTE_ERROR)
        return
    ok, error_msg = validate_max_order(user, bg / ct)
    if not ok:
        await query.edit_message_text(error_msg)
        return
    
    has_sell = s_rsi and s_rsi != "-"
    await query.edit_message_text(f"🚀 {tk} RSI 순환 매매를 시작합니다. 매수 주문 전송 중...")

    b_start, b_end = parse_rsi_range(b_rsi)
    s_start, s_end = parse_rsi_range(s_rsi) if has_sell else (0, 0)
    budget_per_order = bg / ct

    success = 0
    for i in range(ct):
        target_rsi = interpolate_range(b_start, b_end, i, ct)
        sell_target_rsi = interpolate_range(s_start, s_end, i, ct) if has_sell else None
        price = await signal_engine.get_price_by_rsi(
            ex,
            tk,
            target_rsi,
            side="bid",
            interval=get_user_rsi_interval(user),
            user_id=user_id,
        )
        if not price:
            await asyncio.sleep(0.2)
            continue
        volume = round(budget_per_order / price, 4)
        if ex == "kis":
            volume = int(volume)
            if volume <= 0:
                await asyncio.sleep(0.2)
                continue

        res = await exchange_adapter.create_order(user_id, ex, tk, "bid", price, volume)
        if res and "uuid" in res:
            order_manager.add_order(user_id, ex, tk, res["uuid"], price, volume,
                                    side="bid", strategy="rsitrade", target_rsi=target_rsi, linked_to=sell_target_rsi)
            success += 1
        await asyncio.sleep(0.2)

    await context.bot.send_message(chat_id=user_id, text=f"✅ {tk} 전략 가동 완료! ({success}/{ct}건 예약됨)")

async def grid_quick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, exchange, ticker = query.data.split("_", 3)
    await query.edit_message_text(
        f"🕸️ 거미줄 설정 안내\n\n"
        f"- 거래소: {exchange_display_name(exchange)}\n"
        f"- 종목: {ticker}\n\n"
        f"예: /grid {exchange} {ticker} [시작가] [종료가] [횟수] [예산]\n"
        f"또는 RSI 전략은 /rsitrade {exchange} {ticker} [매수RSI] [매도RSI] [횟수] [예산]"
    )

@check_auth
async def sgridrsi_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """RSI 목표 구간 분할 매도 — 보유 코인을 RSI 가격에서 직접 매도"""
    if await check_details_help(update, "sgridrsi"): return
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 사용법: /sgridrsi [거래소] [종목] [RSI구간] [횟수] [예산]\n예: /sgridrsi 빗썸 ETH 80-90 10 100만")
        return

    user_id = str(update.effective_chat.id)
    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)
    if not ticker:
        await update.message.reply_text("⚠️ 종목은 반드시 입력해야 합니다. 예: /sgridrsi ETH")
        return
    if not await ensure_rsi_supported(update, user, exchange):
        return

    offset = 2 if is_exchange_token(args[0], exchange) else 1

    try:
        preferences = user["preferences"]
        sell_rsi_range = args[offset] if len(args) > offset else preferences.get("rsi_sell_range", "65-75")
        count = int(args[offset+1]) if len(args) > offset + 1 else int(preferences.get("rsi_order_count", 5))
        budget = parse_number(args[offset+2]) if len(args) > offset + 2 else preferences.get("rsi_budget_krw")
        if budget is None:
            await update.message.reply_text(
                "⚠️ RSI 매도 전략 예산이 필요합니다. 명령어에 예산을 입력하거나 /config set rsi_budget_krw 100만으로 기본 예산을 저장하세요."
            )
            return
        budget = float(budget)
        s_start, s_end = parse_rsi_range(sell_rsi_range)
        if count <= 0:
            raise ValueError
    except (ValueError, TypeError, IndexError):
        await update.message.reply_text("⚠️ 파라미터 형식이 잘못되었습니다. (예: 80-90)")
        return

    ok, error_msg = validate_max_order(user, budget / count)
    if not ok:
        await update.message.reply_text(error_msg)
        return

    min_amt = exchange_adapter.get_min_order_amount(exchange)
    if (budget / count) < min_amt:
        await update.message.reply_text(f"❌ 예산이 너무 적습니다. 건당 최소 {min_amt:,.0f}원 이상이어야 합니다.")
        return

    status_msg = await update.message.reply_text(f"🔍 {ticker} RSI 매도 가격 분석 중...")

    sell_prices = []
    rsi_step = (s_end - s_start) / (count - 1) if count > 1 else 0
    for i in range(count):
        target_rsi = s_start + (rsi_step * i)
        p = await signal_engine.get_price_by_rsi(
            exchange, ticker, target_rsi, side="ask",
            interval=get_user_rsi_interval(user), user_id=user_id,
        )
        if p: sell_prices.append((target_rsi, p))

    if not sell_prices:
        await status_msg.edit_text("❌ RSI 가격 역산에 실패했습니다. 데이터를 불러올 수 없습니다.")
        return

    confirm_data = f"sgridrsirun|{exchange}|{ticker}|{sell_rsi_range}|{count}|{budget}"
    keyboard = [[InlineKeyboardButton("✅ 매도 전략 가동", callback_data=confirm_data),
                 InlineKeyboardButton("❌ 취소", callback_data="grid_cancel")]]

    preview_text = "\n".join(build_rsi_preview_lines(ticker, sell_prices, budget, count))
    summary = (
        f"💰 RSI 매도 전략 확인\n\n"
        f"전략 설정\n"
        f"- 거래소: {exchange.upper()}\n"
        f"- 종목: {ticker}\n"
        f"- 매도(RSI): {sell_rsi_range} ({sell_prices[0][1]:,.0f} ~ {sell_prices[-1][1]:,.0f}원)\n"
        f"- 분할: {count}회 | 총예산: {budget:,.0f}원\n\n"
        "보유 코인을 RSI 목표가에서 분할 매도합니다. 시작할까요?"
    )
    summary += f"\n\n예상 주문\n{preview_text}\n\n실행 시점에 가격은 다시 계산될 수 있습니다."
    await status_msg.edit_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))

async def sgridrsi_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, ex, tk, s_rsi, ct, bg = query.data.split("|")
    ct, bg = int(ct), float(bg)
    user_id = str(query.from_user.id)
    user = user_manager.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
        return
    if ex == "kis" and get_user_rsi_interval(user) != "day":
        await query.edit_message_text(_KIS_RSI_MINUTE_ERROR)
        return
    ok, error_msg = validate_max_order(user, bg / ct)
    if not ok:
        await query.edit_message_text(error_msg)
        return

    await query.edit_message_text(f"🚀 {tk} RSI 매도 전략을 시작합니다. 매도 주문 전송 중...")

    s_start, s_end = parse_rsi_range(s_rsi)
    budget_per_order = bg / ct

    success = 0
    for i in range(ct):
        target_rsi = interpolate_range(s_start, s_end, i, ct)
        price = await signal_engine.get_price_by_rsi(
            ex, tk, target_rsi, side="ask",
            interval=get_user_rsi_interval(user), user_id=user_id,
        )
        if not price:
            await asyncio.sleep(0.2)
            continue
        volume = round(budget_per_order / price, 4)
        if ex == "kis":
            volume = int(volume)
            if volume <= 0:
                await asyncio.sleep(0.2)
                continue

        res = await exchange_adapter.create_order(user_id, ex, tk, "ask", price, volume)
        if res and "uuid" in res:
            order_manager.add_order(user_id, ex, tk, res["uuid"], price, volume,
                                    side="ask", strategy="sgridrsi", target_rsi=target_rsi, linked_to=None)
            success += 1
        await asyncio.sleep(0.2)

    await context.bot.send_message(chat_id=user_id, text=f"✅ {tk} RSI 매도 전략 가동 완료! ({success}/{ct}건 예약됨)")

async def signal_snooze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime, timedelta, timezone
    query = update.callback_query
    await query.answer()
    # data: "signal_snooze_{mode}_{exchange}_{ticker}"
    parts = query.data.split("_", 4)
    mode, exchange, ticker = parts[2], parts[3], parts[4]
    user_id = str(query.from_user.id)
    expires = signal_engine.set_snooze(user_id, exchange, ticker, mode)
    label = {"1h": "1시간", "2h": "2시간", "day": "오늘 하루"}.get(mode, mode)
    kst = timezone(timedelta(hours=9))
    exp_str = datetime.fromtimestamp(expires, tz=kst).strftime("%H:%M")
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"🔕 {exchange.upper()} {ticker} 알람을 {label}({exp_str}까지) 스누즈했습니다.",
    )

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
            await sync_orders(application)
            metrics.record_poll_ok()
            interval = prefs["poll_active_interval"] if order_manager.orders \
                       else prefs["poll_no_order_interval"]
            await _interruptible_sleep(interval)
        except Exception as e:
            _log.error("Order sync loop error", exc_info=e, extra={"event": "order_sync_loop_error"})
            append_operational_event("error", "order_sync_loop", "order sync loop error", e)
            await _interruptible_sleep(60)

async def _check_ops_health(application):
    """메트릭 임계 초과 시 관리자에게 알림 전송."""
    if not ADMIN_CHAT_ID:
        return
    issues = metrics.ops_alerts()
    if not issues:
        return
    msg = "🚨 <b>운영 알림</b>\n\n" + "\n".join(f"• {issue}" for issue in issues)
    try:
        await application.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="HTML")
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
        
        async def run_grid():
            price_step = (e_p - s_p) / (ct - 1) if ct > 1 else 0
            success_count = 0
            skipped_count = 0
            for i in range(ct):
                target_price = s_p + (price_step * i)
                target_price = ExchangeAdapter.adjust_price_to_tick(target_price)
                raw_vol = (val / ct) / target_price if target_price else 0
                volume = int(raw_vol) if ex == "kis" else round(raw_vol, 4)
                
                if ex == "kis" and volume <= 0:
                    skipped_count += 1
                    continue
                
                try:
                    res = await exchange_adapter.buy_limit_order(user_id, ex, tk, target_price, volume)
                    if res and 'uuid' in res:
                        order_manager.add_order(
                            user_id, ex, tk, res['uuid'], target_price, volume,
                            side="bid",
                            strategy="grid",
                        )
                        success_count += 1
                except Exception as e:
                    _log.error(f"Grid order placement failed at index {i}", exc_info=e)
                await asyncio.sleep(0.2)
            
            result_msg = f"✅ `{tk}` 거미줄 매수 완료! ({success_count}/{ct}건 성공)\n백그라운드에서 체결을 감시합니다."
            if skipped_count:
                result_msg += f"\n⚠️ {skipped_count}건은 수량 부족(0주)으로 건너뜀."
            
            asyncio.create_task(trigger_realtime_sync())
            try:
                await app.bot.send_message(chat_id=user_id, text=result_msg)
            except Exception as e:
                _log.warning("Failed to send telegram grid execution message", exc_info=e)

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

        user = user_manager.get_user(user_id)
        if not user:
            return _web.Response(status=404, text="User not found")

        if ex == "kis" and get_user_rsi_interval(user) != "day":
            return _web.Response(status=400, text="한투 KIS는 일봉(day) 기준 RSI만 지원합니다.")

        ok, error_msg = validate_max_order(user, bg / ct)
        if not ok:
            return _web.Response(status=400, text=error_msg)

        min_amt = exchange_adapter.get_min_order_amount(ex)
        if (bg / ct) < min_amt:
            return _web.Response(status=400, text=f"건당 주문 금액이 거래소 최소 주문 금액({min_amt:,.0f}원)보다 작습니다.")

        app = request.app["bot_application"]

        async def run_rsitrade():
            b_start, b_end = parse_rsi_range(b_rsi)
            s_start, s_end = parse_rsi_range(s_rsi)
            budget_per_order = bg / ct
            
            success = 0
            for i in range(ct):
                target_rsi = interpolate_range(b_start, b_end, i, ct)
                sell_target_rsi = interpolate_range(s_start, s_end, i, ct)
                price = await signal_engine.get_price_by_rsi(
                    ex,
                    tk,
                    target_rsi,
                    side="bid",
                    interval=get_user_rsi_interval(user),
                    user_id=user_id,
                )
                if not price:
                    await asyncio.sleep(0.2)
                    continue
                volume = round(budget_per_order / price, 4)
                if ex == "kis":
                    volume = int(volume)
                    if volume <= 0:
                        await asyncio.sleep(0.2)
                        continue
                
                try:
                    res = await exchange_adapter.create_order(user_id, ex, tk, "bid", price, volume)
                    if res and 'uuid' in res:
                        order_manager.add_order(
                            user_id, ex, tk, res['uuid'], price, volume, 
                            side="bid", strategy="rsitrade", target_rsi=target_rsi, linked_to=sell_target_rsi
                        )
                        success += 1
                except Exception as e:
                    _log.error(f"RSITrade order placement failed at index {i}", exc_info=e)
                await asyncio.sleep(0.2)

            result_msg = f"✅ `{tk}` RSI 순환 매매 전략 가동 완료! ({success}/{ct}건 예약됨)\n백그라운드에서 RSI 체결을 감시합니다."
            asyncio.create_task(trigger_realtime_sync())
            try:
                await app.bot.send_message(chat_id=user_id, text=result_msg)
            except Exception as e:
                _log.warning("Failed to send telegram rsitrade execution message", exc_info=e)

        asyncio.create_task(run_rsitrade())
        return _web.Response(text="RSITrade execution started")
    except Exception as e:
        _log.warning("Internal rsitrade execution failed", exc_info=e)
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
        notify_app.router.add_post("/internal/execute_rsitrade", _internal_execute_rsitrade_handler)
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

# --- 디버그용 글로벌 메시지 핸들러 ---
async def global_debug_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        _log.debug("Telegram message received", extra={"event": "debug_message", "user_id": str(update.effective_user.id), "length": len(update.message.text)})
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
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "info"): return
    short_sha = GIT_SHA[:7] if GIT_SHA != "unknown" else "unknown"
    msg = (
        f"ℹ️ <b>{_html.escape(BOT_DISPLAY_NAME)} 빌드 정보</b>\n\n"
        f"- 버전: {_html.escape(VERSION)}\n"
        f"- 빌드: {_html.escape(BUILD_DATE)}\n"
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

@check_auth
async def natural_language_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    text = (update.message.text or "").strip()
    if not text or text.startswith("/"):
        return
    log_command(str(update.effective_user.id), "nl", source="nl")
    prefs = user.get("preferences", {})

    preprocessed = preprocess_natural_language_intent(text, user)
    if preprocessed:
        append_preprocess_hit(preprocessed)
        if preprocessed.get("action") == "clarify":
            await update.message.reply_text(preprocessed.get("question") or _clarify_message(text, preprocessed))
            return
        if _is_immediate_intent(preprocessed.get("action")):
            await execute_query_intent(update, context, user, preprocessed)
            return
        intent = normalize_natural_language_intent(text, preprocessed, user)
        confirm_text = f"🧠 자연어 요청 확인\n\n{_intent_summary(intent)}\n\n위 내용으로 실행할까요?"
        token = str(len(_pending_nl_intents) + 1)
        _pending_nl_intents[token] = {"user_id": str(update.effective_chat.id), "intent": intent}
        keyboard = [[InlineKeyboardButton("✅ 실행", callback_data=f"nlrun|{token}"),
                     InlineKeyboardButton("❌ 취소", callback_data=f"nlcancel|{token}")]]
        await update.message.reply_text(confirm_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if not prefs.get("llm_enabled") or not has_gemini_key(user):
        await update.message.reply_text("💬 자연어 명령을 사용하려면 /config에서 Gemini API 키를 저장한 뒤 /config set llm_enabled on을 실행해 주세요.")
        return

    llm_intent = await parse_natural_language_intent(text, user)
    intent = normalize_natural_language_intent(text, llm_intent, user)
    append_natural_language_log(text, llm_intent, intent)
    if not intent or intent.get("action") in [None, "clarify"]:
        question = intent.get("question") if isinstance(intent, dict) else None
        await update.message.reply_text(question or _clarify_message(text, intent))
        return

    action = intent.get("action")
    if _is_immediate_intent(action):
        await execute_query_intent(update, context, user, intent)
        return

    confirm_text = f"🧠 자연어 요청 확인\n\n{_intent_summary(intent)}\n\n위 내용으로 실행할까요?"
    if action in ("rsitrade", "gridrsi", "sgridrsi"):
        status_msg = await update.message.reply_text(f"🔍 RSI 가격 분석 중...")
        confirm_text = await build_rsigrid_confirm_summary(str(update.effective_chat.id), user, intent)
        if not confirm_text:
            await status_msg.edit_text("❌ RSI 가격 역산에 실패했습니다. 데이터를 불러올 수 없습니다.")
            return

    token = str(len(_pending_nl_intents) + 1)
    _pending_nl_intents[token] = {"user_id": str(update.effective_chat.id), "intent": intent}
    keyboard = [[InlineKeyboardButton("✅ 실행", callback_data=f"nlrun|{token}"),
                 InlineKeyboardButton("❌ 취소", callback_data=f"nlcancel|{token}")]]
    if action in ("rsitrade", "gridrsi", "sgridrsi"):
        await status_msg.edit_text(confirm_text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(
            confirm_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

async def natural_language_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, token = query.data.split("|", 1)
    pending = _pending_nl_intents.pop(token, None)
    if not pending:
        await query.edit_message_text("⚠️ 만료된 자연어 요청입니다. 다시 입력해 주세요.")
        return
    if action == "nlcancel":
        await query.edit_message_text("❌ 자연어 요청을 취소했습니다.")
        return
    user_id = str(query.from_user.id)
    if pending.get("user_id") != user_id:
        await query.edit_message_text("❌ 다른 사용자의 요청은 실행할 수 없습니다.")
        return
    user = user_manager.get_user(user_id)
    if not user or not user.get("is_active"):
        await query.edit_message_text("❌ 사용자 인증을 확인할 수 없습니다.")
        return
    try:
        await execute_confirmed_intent(query, context, user, pending["intent"])
    except Exception as e:
        await query.edit_message_text(f"❌ 자연어 요청 실행 실패: {e}")

# ==========================================
# 🚀 메인 실행부
# ==========================================
def main():
    _validate_env()

    # post_init을 통해 백그라운드 태스크를 봇 생명주기에 안전하게 편입시킵니다.
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    # 명령어 사용 로깅 (group=-1: 모든 command 핸들러보다 먼저 실행)
    application.add_handler(MessageHandler(filters.COMMAND, _command_usage_handler), group=-1)

    # 운영 기본값은 민감정보 보호를 위해 텔레그램 본문 로깅을 끕니다.
    if DEBUG_TELEGRAM_MESSAGES:
        application.add_handler(MessageHandler(filters.ALL, global_debug_handler), group=-1)

    config_conv = ConversationHandler(
        entry_points=[CommandHandler("config", config_command)],
        states={
            SET_EXCHANGE: [CallbackQueryHandler(config_exchange_callback, pattern="^conf_")],
            SET_ACCESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_access_key)],
            SET_SECRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_secret_key)],
            SET_KIS_APP: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_kis_app_key)],
            SET_KIS_SECRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_kis_secret_key)],
            SET_KIS_ACCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_kis_account)],
            SET_KIS_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_kis_product)],
            SET_KIS_ENV: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_kis_env)],
            SET_GEMINI_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_gemini_key)],
        },
        fallbacks=[CommandHandler("cancel", cancel_config)],
        allow_reentry=True  # /config 중복 입력 허용
    )

    # 핸들러 등록 (ConversationHandler를 최상단에 유지)
    application.add_handler(config_conv)
    application.add_handler(CommandHandler("cfg", config_command)) # 테스트용 단순 명령어
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("commands", help_command))
    application.add_handler(CommandHandler("info", info_command))
    for command_name in ACCOUNT_COMMAND_ALIASES:
        application.add_handler(CommandHandler(command_name, whoami_command))
    application.add_handler(CommandHandler("asset", asset_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("p", price_command))
    application.add_handler(CommandHandler("indicators", indicators_command))
    application.add_handler(CommandHandler("ind", indicators_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("sell", sell_command))
    application.add_handler(CommandHandler("orders", orders_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("grid", grid_command))
    application.add_handler(CommandHandler("sgrid", sgrid_command))
    for command_name in RSI_GRID_COMMAND_ALIASES:
        application.add_handler(CommandHandler(command_name, rsitrade_command))
    application.add_handler(CommandHandler("watch", watch_command))
    application.add_handler(CommandHandler("unwatch", unwatch_command))
    application.add_handler(CallbackQueryHandler(grid_quick_callback, pattern="^grid_quick_"))
    application.add_handler(CallbackQueryHandler(signal_snooze_callback, pattern="^signal_snooze_"))
    application.add_handler(CallbackQueryHandler(grid_confirm_callback, pattern="^(gridrun|sgridrun|grid_cancel)"))
    application.add_handler(CallbackQueryHandler(rsitrade_confirm_callback, pattern="^rsitrun"))
    application.add_handler(CommandHandler("sgridrsi", sgridrsi_command))
    application.add_handler(CallbackQueryHandler(sgridrsi_confirm_callback, pattern="^sgridrsirun"))
    application.add_handler(CallbackQueryHandler(manual_order_confirm_callback, pattern="^(manualrun|manualcancel)\\|"))
    application.add_handler(CallbackQueryHandler(natural_language_confirm_callback, pattern="^nl(run|cancel)\\|"))
    
    # [중요] 알 수 없는 명령어 처리 (가장 마지막에 등록)
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_language_command))

    _log.info(f"{BOT_DISPLAY_NAME} starting", extra={"event": "bot_start", "version": VERSION})
    
    # 동기식으로 실행 (자체 이벤트 루프를 안전하게 생성합니다)
    application.run_polling()
    
if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
