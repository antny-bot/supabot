import os
import asyncio
import json
import re
from datetime import datetime, time as dt_time, timedelta, timezone
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

from core.user_manager import UserManager
from core.exchange_adapter import ExchangeAdapter
from core.order_manager import OrderManager
from core.signal_engine import SignalEngine
from core.natural_language import (
    append_natural_language_log,
    append_preprocess_hit,
    clear_natural_language_logs,
    normalize_natural_language_intent,
    preprocess_natural_language_intent,
    read_natural_language_log_stats,
    read_preprocess_hit_stats,
    read_recent_natural_language_logs,
)
from core.secret_crypto import can_decrypt_secrets, has_secret_key

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
KST = timezone(timedelta(hours=9))
_pending_nl_intents = {}
RSI_GRID_COMMAND_ALIASES = ("rsigrid", "rsitrade")
ACCOUNT_COMMAND_ALIASES = ("whomai", "me")
DEFAULT_BOT_COMMANDS = [
    ("start", "시스템 접속 및 메뉴 확인"),
    ("help", "전체 명령어 사용 설명서"),
    ("status", "트레이딩 전략 대시보드"),
    ("asset", "통합 자산 현황 조회"),
    ("price", "종목 실시간 시세 조회"),
    ("history", "최근 체결 내역 조회"),
    ("orders", "추적 중인 미체결 주문"),
    ("rsitrade", "RSI 순환 매매 전략"),
    ("grid", "가격 범위 분할 매수"),
    ("sgrid", "보유 수량 분할 매도"),
    ("buy", "단일 지정가 매수"),
    ("sell", "단일 지정가 매도"),
    ("cancel", "종목 주문 일괄 취소"),
    ("watch", "RSI 감시 종목 추가"),
    ("unwatch", "RSI 감시 종목 제거"),
    ("config", "거래소, LLM API 설정"),
    ("info", "봇 버전 및 빌드 정보"),
    ("whomai", "내 계정 권한과 상태 확인"),
]
ADMIN_BOT_COMMANDS = [
    *DEFAULT_BOT_COMMANDS,
    ("nlstats", "관리자 전용 자연어 패턴 통계"),
    ("diag", "관리자 운영 진단"),
]

# Conversation States
SET_EXCHANGE, SET_ACCESS, SET_SECRET, SET_KIS_APP, SET_KIS_SECRET, SET_KIS_ACCOUNT, SET_KIS_PRODUCT, SET_KIS_ENV, SET_GEMINI_KEY = range(9)

# ==========================================
# 📖 명령어별 상세 도움말 데이터
# ==========================================
CMD_HELP = {
    "start": (
        "🎁 */start 상세 가이드*\n\n"
        "**기능:** 봇을 시작하고 시스템에 등록을 요청하거나 메뉴를 불러옵니다.\n"
        "**사용법:** `/start`만 입력\n\n"
        "**안내:**\n"
        "• 처음 사용 시 관리자의 승인이 필요합니다.\n"
        "• 승인 후에는 언제든지 `/start`로 주요 메뉴를 다시 볼 수 있습니다."
    ),
    "config": (
        "⚙️ */config 상세 가이드*\n\n"
        "**기능:** 거래소 API 키와 사용자 기본 설정을 관리합니다.\n\n"
        "**API 키 설정:** `/config` 입력 후 버튼 클릭\n"
        "1. 거래소 선택 (Upbit, Bithumb, 한국투자증권, Gemini)\n"
        "2. 거래소별 Key 입력 (메시지 삭제됨)\n"
        "3. 한국투자증권은 계좌번호, 상품코드, 모의/실전 환경까지 입력\n"
        "4. 자동 유효성 검증 수행\n\n"
        "**설정 조회:** `/config -v`\n"
        "API 키 값은 표시하지 않고 설정 여부만 보여줍니다.\n\n"
        "**설정 변경:** `/config set [항목] [값]`\n"
        "• `default_exchange`: upbit, bithumb, kis, 업비트, 빗썸, 한투\n"
        "• `asset_min_display_krw`: `/asset` 개별 표시 최소 평가액\n"
        "• `rsi_buy_range`: 예: 25-30\n"
        "• `rsi_sell_range`: 예: 65-75\n"
        "• `rsi_order_count`: 예: 5\n"
        "• `rsi_budget_krw`: 예: 100만 또는 off\n"
        "• `rsi_interval`: day 또는 1/3/5/10/15/30/60/240\n"
        "• `signal_alerts`: on/off\n"
        "• `signal_rsi_threshold`: 예: 30\n"
        "• `max_order_krw`: 예: 50만 또는 off\n"
        "• `llm_enabled`: on/off\n"
        "• `llm_model`: 예: gemini-2.5-flash-lite\n\n"
        "**폴링 설정 (관리자 전용):**\n"
        "• `poll_active_interval`: 오더 있을 때 주기 (초, 기본 60)\n"
        "• `poll_no_order_interval`: 오더 없을 때 fallback 주기 (초, 기본 300)\n"
        "• `signal_analysis_interval`: 시그널 분석 주기 (초, 기본 300)\n\n"
        "**예시:**\n"
        "`/config set asset_min_display_krw 10000`\n"
        "`/config set rsi_budget_krw 100만`\n"
        "`/config set rsi_interval day`\n"
        "`/config set llm_enabled on`\n"
        "`/config set max_order_krw 50만`\n"
        "`/config set poll_active_interval 30`\n\n"
        "⚠️ 보안을 위해 입력한 키 메시지는 즉시 자동 삭제됩니다."
    ),
    "asset": (
        "💰 */asset 상세 가이드*\n\n"
        "**기능:** 내 거래소 잔고와 총 평가액을 조회합니다.\n"
        "**구문:** `/asset [거래소]`\n\n"
        "**옵션:**\n"
        "• `업비트` 또는 `빗썸`: 특정 거래소만 조회 (생략 시 전체 조회)\n\n"
        "**예시:**\n"
        "1. `/asset` (모든 거래소 조회)\n"
        "2. `/asset 빗썸` (빗썸 잔고만 조회)\n"
        "⚠️ 설정한 최소 표시 금액 이하의 소액 자산은 '기타'로 합산 표시됩니다."
    ),
    "price": (
        "📊 */price 상세 가이드*\n\n"
        "**기능:** 특정 종목의 실시간 시세를 조회합니다.\n"
        "**구문:** `/price [거래소] [종목]`\n\n"
        "**옵션:**\n"
        "• `거래소`: 업비트, 빗썸, 한투 (생략 시 기본 거래소 우선)\n"
        "• `종목`: 암호화폐는 BTC, ETH 등, 한국투자증권은 005930 같은 국내주식 종목코드\n\n"
        "**예시:**\n"
        "1. `/p BTC` (업비트 비트코인 시세)\n"
        "2. `/price 빗썸 ETH` (빗썸 이더리움 시세)\n"
        "3. `/p KRW-XRP` (심볼 직접 입력)\n"
        "4. `/price 한투 005930` (한국투자증권 삼성전자 시세)"
    ),
    "history": (
        "📜 */history 상세 가이드*\n\n"
        "**기능:** 나의 최근 체결(완료)된 주문 내역을 보여줍니다.\n"
        "**구문:** `/history [거래소] [종목]`\n\n"
        "**옵션:**\n"
        "• `거래소`: 업비트, 빗썸\n"
        "• `종목`: 특정 코인 내역만 필터링 (생략 시 전체)\n\n"
        "**예시:**\n"
        "1. `/history` (업비트 전체 최근 내역)\n"
        "2. `/history 빗썸` (빗썸 전체 최근 내역)\n"
        "3. `/history BTC` (업비트 비트코인 거래 내역)"
    ),
    "buy": (
        "🛍️ */buy 상세 가이드 (단일 매수)*\n\n"
        "**기능:** 지정한 거래소에 단일 매수 주문을 즉시 전송합니다.\n"
        "**구문:** `/buy [거래소] [종목] [가격] [수량]`\n\n"
        "**예시:**\n"
        "`/buy 빗썸 BTC 95000000 0.1` (빗썸에서 0.1 BTC를 9500만원에 매수)\n"
        "`/buy 한투 005930 70000 1` (한국투자증권에서 삼성전자 1주 매수 확인)\n\n"
        "⚠️ 한국투자증권 주문은 확인 버튼을 거친 뒤 전송됩니다."
    ),
    "sell": (
        "🛍️ */sell 상세 가이드 (단일 매도)*\n\n"
        "**기능:** 지정한 거래소에 단일 매도 주문을 즉시 전송합니다.\n"
        "**구문:** `/sell [거래소] [종목] [가격] [수량]`\n\n"
        "**예시:**\n"
        "`/sell BTC 120000000 0.5` (업비트에서 0.5 BTC를 1.2억원에 매도)\n\n"
        "⚠️ 보유 수량이 주문 수량보다 많아야 합니다."
    ),
    "grid": (
        "🕸️ */grid 상세 가이드 (분할 매수)*\n\n"
        "**기능:** 지정가 범위 내에서 예산을 분할하여 여러 개의 매수 주문을 겁니다.\n"
        "**구문:** `/grid [거래소] [종목] [시작가] [종료가] [횟수] [총예산]`\n\n"
        "**사용 예시:**\n"
        "`/grid BTC 1억 9천 10 100만` (1억~9천 사이 10번 분할 매수)\n\n"
        "**상세 파라미터:**\n"
        "• 횟수: 몇 번에 나눠서 주문할지 지정\n"
        "• 총예산: 전체 주문에 투입할 원화(KRW) 총액"
    ),
    "sgrid": (
        "🕸️ */sgrid 상세 가이드 (분할 매도)*\n\n"
        "**기능:** 지정가 범위 내에서 보유 수량을 분할하여 여러 개의 매도 주문을 겁니다.\n"
        "**구문:** `/sgrid [거래소] [종목] [시작가] [종료가] [횟수] [총수량]`\n\n"
        "**사용 예시:**\n"
        "`/sgrid 빗썸 ETH 400만 450만 5 0.5` (400~450만 사이 0.5개 분할 매도)\n\n"
        "**상세 파라미터:**\n"
        "• 횟수: 몇 번에 나눠서 팔지 지정\n"
        "• 총수량: 전체 매도할 코인 개수"
    ),
    "orders": (
        "⏳ */orders 상세 가이드*\n\n"
        "**기능:** 현재 거래소에 걸려있는 미체결 주문 목록을 확인합니다.\n"
        "**구문:** `/orders [거래소]`\n\n"
        "**옵션:**\n"
        "• `업비트` 또는 `빗썸` (생략 시 기본 거래소)\n\n"
        "**안내:**\n"
        "봇을 통해 생성한 주문뿐만 아니라 직접 거래소에서 건 미체결 주문도 모두 조회됩니다."
    ),
    "cancel": (
        "🛑 */cancel 상세 가이드*\n\n"
        "**기능:** 특정 종목의 모든 미체결 주문을 일괄 취소합니다.\n"
        "**구문:** `/cancel [거래소] [종목]`\n\n"
        "**예시:**\n"
        "1. `/cancel BTC` (업비트 비트코인 주문 취소)\n"
        "2. `/cancel 빗썸 SOL` (빗썸 솔라나 주문 취소)"
    ),
    "watch": (
        "🔔 */watch 상세 가이드*\n\n"
        "**기능:** 특정 종목의 RSI 지표를 실시간 감시하여 매수 시그널을 알립니다.\n"
        "**구문:** `/watch [거래소] [종목]`\n\n"
        "**예시:**\n"
        "1. `/watch BTC` (업비트 비트코인 감시 시작)\n"
        "2. `/watch 빗썸 SOL` (빗썸 솔라나 감시 시작)"
    ),
    "unwatch": (
        "🔕 */unwatch 상세 가이드*\n\n"
        "**기능:** RSI 시그널 감시 목록에서 특정 종목을 제거합니다.\n"
        "**구문:** `/unwatch [거래소] [종목]`\n\n"
        "**예시:**\n"
        "`/unwatch BTC` (비트코인 감시 종료)"
    ),
    "rsitrade": (
        "🤖 */rsitrade 상세 가이드*\n\n"
        "**기능:** RSI 목표 구간을 기준으로 분할 매수하고, 체결 시 RSI 매도 목표 주문을 예약합니다.\n"
        "**구문:** `/rsitrade [거래소] [종목] [매수RSI] [매도RSI] [횟수] [예산]`\n\n"
        "**기본값:** 종목만 입력하면 `/config`에 저장된 매수RSI, 매도RSI, 횟수, 예산을 사용합니다.\n\n"
        "**예시:**\n"
        "1. `/rsitrade BTC`\n"
        "2. `/rsitrade 빗썸 BTC`\n"
        "3. `/rsitrade BTC 20-30 60-75 7 200만`"
    ),
    "info": (
        "ℹ️ */info 상세 가이드*\n\n"
        "**기능:** 현재 실행 중인 봇의 버전 및 빌드 정보를 표시합니다.\n"
        "**사용법:** `/info`만 입력"
    ),
}

async def check_details_help(update: Update, command_name: str):
    """인자값에 -h, -help, --help가 포함되어 있는지 확인하고 상세 도움말을 출력합니다."""
    if update.message and update.message.text:
        text = update.message.text.lower()
        if any(opt in text for opt in [" -h", "-help", "--help"]):
            help_text = CMD_HELP.get(command_name, "해당 명령어에 대한 상세 도움말이 아직 없습니다.")
            await update.message.reply_text(help_text)
            return True
    return False

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

def build_start_menu_message(user):
    return (
        f"🤖 {BOT_DISPLAY_NAME} 시스템 접속 완료\n\n"
        f"어서오세요, {user.get('username', '사용자')}님. 현재 정상 이용 가능합니다.\n\n"
        "주요 명령어\n"
        "- /asset: 전체 자산 현황 조회\n"
        "- /orders: 미체결 주문 확인\n"
        "- /grid: 거미줄 매수 설정\n"
        "- /config: 거래소, LLM API 설정\n"
        "- /watch: 시그널 감시 종목 추가\n"
        "- /help: 전체 명령어 확인"
    )

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
            keyboard = [[InlineKeyboardButton("✅ 승인하기", callback_data=f"approve_{user_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"🔔 신규 유저 등록 요청\n\n- 이름: {username}\n- ID: {user_id}",
                reply_markup=reply_markup,
            )
    elif not user["is_active"]:
        await update.message.reply_text("⏳ 현재 승인 대기 중입니다. 잠시만 기다려 주세요!")
    else:
        msg = build_start_menu_message(user)
        await update.message.reply_text(msg)

async def approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if str(query.from_user.id) != str(ADMIN_CHAT_ID):
        return

    user_id = query.data.split("_")[1]
    if user_manager.set_active(user_id, True):
        await query.edit_message_text(text=f"✅ 유저(ID: {user_id}) 승인이 완료되었습니다.")
        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 축하합니다! 봇 사용 승인이 완료되었습니다. 이제 /start 명령어로 메뉴를 확인해 보세요!"
        )

def parse_exchange_and_ticker(args, default_exchange):
    """사용자 입력 args에서 거래소와 종목(Ticker)을 분리하여 반환합니다."""
    if not args:
        return default_exchange, None
    
    exchange = default_exchange
    raw_ticker = None
    
    arg0_exchange = normalize_exchange(args[0])
    if arg0_exchange:
        exchange = arg0_exchange
        raw_ticker = args[1].upper() if len(args) > 1 else None
    else:
        raw_ticker = args[0].upper()

    if raw_ticker:
        if exchange in ["upbit", "bithumb"] and "-" not in raw_ticker:
            raw_ticker = f"KRW-{raw_ticker}"
        elif exchange == "kis":
            raw_ticker = raw_ticker.replace("KRW-", "")
            
    return exchange, raw_ticker

def normalize_exchange(value):
    text = str(value).strip().lower()
    if text in ["upbit", "업비트"]:
        return "upbit"
    if text in ["bithumb", "빗썸"]:
        return "bithumb"
    if text in ["kis", "한투", "한국투자", "한국투자증권"]:
        return "kis"
    return None

def is_exchange_token(value, exchange):
    return normalize_exchange(value) == exchange

def exchange_display_name(exchange):
    return {
        "upbit": "UPBIT",
        "bithumb": "BITHUMB",
        "kis": "한국투자증권",
    }.get(exchange, exchange.upper())

def parse_number(value):
    """텔레그램 입력 숫자와 간단한 한글 단위를 숫자로 변환합니다."""
    text = str(value).replace(",", "").strip()
    multipliers = [("억", 100000000), ("만", 10000), ("천", 1000)]
    for suffix, multiplier in multipliers:
        if text.endswith(suffix):
            return float(text[:-len(suffix)]) * multiplier
    return float(text)

def parse_rsi_range(rsi_range):
    start, end = map(float, str(rsi_range).split("-"))
    if not (0 <= start <= 100 and 0 <= end <= 100 and start <= end):
        raise ValueError("RSI 범위는 0-100 사이의 오름차순이어야 합니다.")
    return start, end

def parse_optional_krw(value):
    if str(value).strip().lower() in ["off", "none", "unset", "미설정", "해제", "0"]:
        return None
    amount = parse_number(value)
    if amount <= 0:
        raise ValueError("금액은 0보다 커야 합니다.")
    return amount

def format_optional_krw(value):
    return "미설정" if value is None else f"{float(value):,.0f}원"

def format_bool(value):
    return "on" if bool(value) else "off"

def escape_markdown_text(value):
    text = str(value or "")
    for char in ["\\", "_", "*", "`", "["]:
        text = text.replace(char, f"\\{char}")
    return text

def format_section(title, lines):
    body = [str(line) for line in lines if str(line) != ""]
    return "\n".join([title, *body])

RSI_INTERVAL_ALIASES = {
    "day": "day",
    "daily": "day",
    "d": "day",
    "1d": "day",
}
RSI_MINUTE_INTERVALS = {"1", "3", "5", "10", "15", "30", "60", "240"}
POLL_INTERVAL_KEYS = {"poll_active_interval", "poll_no_order_interval", "signal_analysis_interval"}
ADMIN_ONLY_KEYS = POLL_INTERVAL_KEYS

def parse_rsi_interval(value):
    text = str(value).strip().lower()
    if text in RSI_INTERVAL_ALIASES:
        return RSI_INTERVAL_ALIASES[text]
    if text in RSI_MINUTE_INTERVALS:
        return text
    raise ValueError("RSI 캔들 기준은 day 또는 1,3,5,10,15,30,60,240 분봉 중 하나여야 합니다.")

def format_rsi_interval(value):
    value = parse_rsi_interval(value)
    if value == "day":
        return "day (일봉)"
    return f"{value}분봉"

def has_gemini_key(user):
    return bool(user.get("llm", {}).get("gemini_api_key"))

def _format_seconds(seconds: int) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}초"
    m, s = divmod(seconds, 60)
    return f"{m}분" if s == 0 else f"{m}분 {s}초"

def _as_kst_now(now=None):
    if now is None:
        return datetime.now(KST).replace(tzinfo=None)
    if getattr(now, "tzinfo", None):
        return now.astimezone(KST).replace(tzinfo=None)
    return now

def is_kis_regular_session(now=None):
    now = _as_kst_now(now)
    if now.weekday() >= 5:
        return False
    start = dt_time(9, 0)
    end = dt_time(15, 35)
    return start <= now.time() <= end

def next_kis_regular_session(now=None):
    now = _as_kst_now(now)
    next_day = now
    if now.weekday() < 5 and now.time() < dt_time(9, 0):
        return now.replace(hour=9, minute=0, second=0, microsecond=0)
    next_day = now + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    return next_day.replace(hour=9, minute=0, second=0, microsecond=0)

def kis_next_check_timestamp(now=None):
    return next_kis_regular_session(now).replace(tzinfo=KST).timestamp()

def is_strategy_order(order):
    return str(order.get("strategy", "")).startswith("rsitrade") or str(order.get("strategy", "")).startswith("grid")

def get_user_rsi_interval(user):
    return user.get("preferences", {}).get("rsi_interval", "day")

async def ensure_rsi_supported(update, user, exchange):
    if exchange == "kis" and get_user_rsi_interval(user) != "day":
        await update.message.reply_text("⚠️ 한국투자증권 RSI는 일봉만 지원합니다. /config set rsi_interval day 후 다시 시도하세요.")
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
        "RSI + split/grid/거미줄 + budget => rsitrade.\n"
        "grid is price-range only, not RSI.\n"
        "Missing sell_rsi_range => null; server uses default.\n"
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
        print(f"⚠️ Gemini intent parse error: {e}")
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
    elif action == "rsitrade":
        if intent.get("buy_rsi_range"):
            args.append(str(intent["buy_rsi_range"]))
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
    return action in {"asset", "price", "orders", "status", "config_view", "history", "help"}

def _intent_summary(intent):
    action = intent.get("action")
    if action == "config_set":
        return f"설정 변경: {intent.get('config_key')} = {intent.get('config_value')}"
    if action == "rsitrade":
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
    pieces = [str(action or "unknown")]
    for key in ["exchange", "ticker", "price", "volume", "amount_krw", "start_price", "end_price", "count", "buy_rsi_range", "sell_rsi_range"]:
        if intent.get(key) is not None:
            pieces.append(f"{key}={intent[key]}")
    return " / ".join(pieces)

def _clarify_message(text, intent):
    action = intent.get("action") if isinstance(intent, dict) else None
    if action == "rsitrade" or _looks_like_rsi_split_request(text):
        return "⚠️ RSI 전략은 종목, 매수 RSI, 예산을 확인할 수 있어야 합니다."
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
        return await update.message.reply_text(build_config_view(user))
    if action == "help":
        return await help_command(update, context)
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
        if key in ADMIN_ONLY_KEYS and not user.get("is_admin"):
            await query.edit_message_text("❌ 이 설정은 관리자만 변경할 수 있습니다.")
            return
        value = parse_config_value(key, raw_value)
        validate_config_update(user, key, value)
        user_manager.update_preference(user_id, key, value)
        await query.edit_message_text(f"✅ {key} 설정을 {format_config_value(key, value)}(으)로 저장했습니다.")
        return

    if action in ["watch", "unwatch"]:
        if exchange == "kis" and get_user_rsi_interval(user) != "day":
            await query.edit_message_text("⚠️ 한국투자증권 RSI는 일봉만 지원합니다. /config set rsi_interval day 후 다시 시도하세요.")
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
            await query.edit_message_text(f"❌ 주문 실패: {res}")
        return

    if action == "rsitrade":
        if exchange == "kis" and get_user_rsi_interval(user) != "day":
            await query.edit_message_text("⚠️ 한국투자증권 RSI는 일봉만 지원합니다. /config set rsi_interval day 후 다시 시도하세요.")
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

    await query.edit_message_text("⚠️ 이 자연어 요청은 아직 실행할 수 없습니다. /help에서 지원 명령을 확인해 주세요.")

def format_config_value(key, value):
    if isinstance(value, bool):
        return format_bool(value)
    if key == "rsi_interval":
        return format_rsi_interval(value)
    if key in ["rsi_budget_krw", "max_order_krw"]:
        return format_optional_krw(value)
    if key == "asset_min_display_krw":
        return f"{float(value):,.0f}원"
    if key in POLL_INTERVAL_KEYS:
        return _format_seconds(value)
    return value

def validate_max_order(user, order_krw):
    max_order_krw = user.get("preferences", {}).get("max_order_krw")
    if max_order_krw is None:
        return True, None
    if order_krw > float(max_order_krw):
        return False, f"❌ 단일 주문 금액 {order_krw:,.0f}원이 설정된 최대 주문 금액 {float(max_order_krw):,.0f}원을 초과합니다."
    return True, None

def validate_config_update(user, key, value):
    if key == "llm_enabled" and value and not has_gemini_key(user):
        raise ValueError("Gemini API 키를 먼저 /config에서 설정해야 llm_enabled를 켤 수 있습니다.")
    return True

def build_secret_security_status(user):
    if not has_secret_key():
        return "없음"
    if not can_decrypt_secrets():
        return "형식 오류"
    if user.get("_secret_error"):
        return "복호화 오류"
    return "정상"

def format_api_validation_status(user, exchange):
    validation = user.get("api_validation", {}).get(exchange)
    if not validation:
        return "검증 이력 없음"
    status = "마지막 검증 성공" if validation.get("ok") else "마지막 검증 실패"
    checked_at = str(validation.get("checked_at") or "").split("+")[0].replace("T", " ")
    return f"{status} {checked_at}".strip()

def build_config_view(user):
    preferences = user["preferences"]
    api_lines = []
    for exchange in ["upbit", "bithumb", "kis"]:
        keys = user.get("exchanges", {}).get(exchange, {})
        if exchange == "kis":
            is_set = bool(keys.get("app_key") and keys.get("app_secret") and keys.get("account_no"))
            account = keys.get("account_no", "")
            masked_account = f"{account[:2]}****{account[-2:]}" if len(account) >= 4 else "미설정"
            env_name = "실전" if keys.get("env") == "real" else "모의"
            api_lines.append(f"- {exchange_display_name(exchange)}: {'설정됨' if is_set else '미설정'} / {env_name} / 계좌 {masked_account} / {format_api_validation_status(user, exchange)}")
        else:
            is_set = bool(keys.get("access_key") and keys.get("secret_key"))
            api_lines.append(f"- {exchange_display_name(exchange)}: {'설정됨' if is_set else '미설정'} / {format_api_validation_status(user, exchange)}")

    sections = [
        "⚙️ 현재 사용자 설정",
        "",
        format_section("API 키 상태", api_lines),
        "",
        format_section("기본 설정", [
        f"- default_exchange: {preferences.get('default_exchange')}",
        f"- asset_min_display_krw: {float(preferences.get('asset_min_display_krw', 10000)):,.0f}원 이하 기타 합산",
        f"- rsi_interval: {format_rsi_interval(preferences.get('rsi_interval', 'day'))}",
        f"- rsi_buy_range: {preferences.get('rsi_buy_range')}",
        f"- rsi_sell_range: {preferences.get('rsi_sell_range')}",
        f"- rsi_order_count: {preferences.get('rsi_order_count')}",
        f"- rsi_budget_krw: {format_optional_krw(preferences.get('rsi_budget_krw'))}",
        f"- signal_alerts: {format_bool(preferences.get('signal_alerts'))}",
        f"- signal_rsi_threshold: {float(preferences.get('signal_rsi_threshold', 30)):g}",
        f"- max_order_krw: {format_optional_krw(preferences.get('max_order_krw'))}",
        ]),
        "",
        format_section("LLM 설정", [
        f"- Gemini: {'설정됨' if has_gemini_key(user) else '미설정'}",
        f"- llm_enabled: {format_bool(preferences.get('llm_enabled'))}",
        f"- llm_model: {preferences.get('llm_model', 'gemini-2.5-flash-lite')}",
        ]),
        "",
        format_section("보안 설정", [
        f"- USER_SECRET_KEY: {build_secret_security_status(user)}",
        ]),
    ]
    if user.get("is_admin"):
        active_interval = _format_seconds(preferences.get("poll_active_interval", 60))
        no_order_interval = _format_seconds(preferences.get("poll_no_order_interval", 300))
        signal_interval = _format_seconds(preferences.get("signal_analysis_interval", 300))
        current_interval = active_interval if order_manager.orders else no_order_interval
        order_count = len(order_manager.orders)
        current_reason = f"활성 오더 {order_count}건" if order_manager.orders else "오더 없음"
        sections.extend([
            "",
            format_section("폴링 설정 (관리자)", [
            f"- poll_active_interval: {active_interval}  (오더 있을 때)",
            f"- poll_no_order_interval: {no_order_interval}  (오더 없을 때 fallback)",
            f"- signal_analysis_interval: {signal_interval}",
            f"→ 현재: {current_reason} → {current_interval} 주기 적용 중",
            ]),
        ])
    return "\n".join(sections)

def build_diag_view(user):
    prefs = user.get("preferences", {})
    active_interval = _format_seconds(prefs.get("poll_active_interval", 60))
    no_order_interval = _format_seconds(prefs.get("poll_no_order_interval", 300))
    current_interval = active_interval if order_manager.orders else no_order_interval
    exchange_lines = []
    for exchange in ["upbit", "bithumb", "kis"]:
        keys = user.get("exchanges", {}).get(exchange, {})
        if exchange == "kis":
            is_set = bool(keys.get("app_key") and keys.get("app_secret") and keys.get("account_no"))
            env_name = "실전" if keys.get("env") == "real" else "모의"
            exchange_lines.append(f"- {exchange_display_name(exchange)}: {'설정됨' if is_set else '미설정'} / {env_name} / {format_api_validation_status(user, exchange)}")
        else:
            is_set = bool(keys.get("access_key") and keys.get("secret_key"))
            exchange_lines.append(f"- {exchange_display_name(exchange)}: {'설정됨' if is_set else '미설정'} / {format_api_validation_status(user, exchange)}")
    return "\n".join([
        "🧪 운영 진단",
        "",
        format_section("환경", [
            f"- TELEGRAM_BOT_TOKEN: {'설정됨' if BOT_TOKEN else '없음'}",
            f"- ADMIN_CHAT_ID: {'설정됨' if ADMIN_CHAT_ID else '없음'}",
            f"- USER_SECRET_KEY: {build_secret_security_status(user)}",
        ]),
        "",
        format_section("빌드", [
            f"- 버전: {VERSION}",
            f"- 빌드: {BUILD_DATE}",
            f"- 커밋: {GIT_SHA[:7] if GIT_SHA != 'unknown' else 'unknown'}",
        ]),
        "",
        format_section("LLM", [
            f"- Gemini: {'설정됨' if has_gemini_key(user) else '미설정'}",
            f"- llm_enabled: {format_bool(prefs.get('llm_enabled'))}",
            f"- llm_model: {prefs.get('llm_model', 'gemini-2.5-flash-lite')}",
        ]),
        "",
        format_section("거래소", exchange_lines),
        "",
        format_section("주문/폴링", [
            f"- 활성 주문: {len(order_manager.orders)}건",
            f"- 현재 주기: {current_interval}",
            f"- poll_active_interval: {active_interval}",
            f"- poll_no_order_interval: {no_order_interval}",
            f"- signal_analysis_interval: {_format_seconds(prefs.get('signal_analysis_interval', 300))}",
        ]),
    ])

def parse_config_value(key, raw_value):
    key = key.strip().lower()
    if key == "default_exchange":
        exchange = normalize_exchange(raw_value)
        if not exchange:
            raise ValueError("기본 거래소는 upbit, bithumb, kis, 업비트, 빗썸, 한투 중 하나여야 합니다.")
        return exchange
    if key == "asset_min_display_krw":
        amount = parse_number(raw_value)
        if amount < 0:
            raise ValueError("최소 표시 금액은 0 이상이어야 합니다.")
        return amount
    if key in ["rsi_buy_range", "rsi_sell_range"]:
        parse_rsi_range(raw_value)
        return str(raw_value)
    if key == "rsi_interval":
        return parse_rsi_interval(raw_value)
    if key == "rsi_order_count":
        count = int(raw_value)
        if count <= 0:
            raise ValueError("분할 주문 수는 1 이상이어야 합니다.")
        return count
    if key == "rsi_budget_krw":
        return parse_optional_krw(raw_value)
    if key == "signal_alerts":
        text = str(raw_value).strip().lower()
        if text in ["on", "true", "1", "yes", "y", "켜기"]:
            return True
        if text in ["off", "false", "0", "no", "n", "끄기"]:
            return False
        raise ValueError("signal_alerts 값은 on 또는 off여야 합니다.")
    if key == "llm_enabled":
        text = str(raw_value).strip().lower()
        if text in ["on", "true", "1", "yes", "y", "켜기"]:
            return True
        if text in ["off", "false", "0", "no", "n", "끄기"]:
            return False
        raise ValueError("llm_enabled 값은 on 또는 off여야 합니다.")
    if key == "llm_model":
        model = str(raw_value).strip()
        if not model.startswith("gemini-"):
            raise ValueError("llm_model은 gemini- 로 시작하는 모델명이어야 합니다.")
        return model
    if key == "signal_rsi_threshold":
        threshold = float(raw_value)
        if not 0 <= threshold <= 100:
            raise ValueError("RSI 기준은 0-100 사이여야 합니다.")
        return threshold
    if key == "max_order_krw":
        return parse_optional_krw(raw_value)
    if key in POLL_INTERVAL_KEYS:
        try:
            val = int(raw_value)
        except (ValueError, TypeError):
            raise ValueError("폴링 주기는 정수(초)로 입력해야 합니다.")
        if val < 10:
            raise ValueError("폴링 주기는 최소 10초 이상이어야 합니다.")
        return val
    raise ValueError("지원하지 않는 설정 항목입니다. `/config -h`로 항목 목록을 확인하세요.")

def interpolate_range(start, end, index, count):
    if count <= 1:
        return start
    return start + ((end - start) / (count - 1) * index)

def resolve_linked_rsi_target(linked_to):
    if linked_to is None:
        return None
    text = str(linked_to)
    if "-" in text:
        start, _ = parse_rsi_range(text)
        return start
    return float(text)

def _volume_unit(ticker):
    text = str(ticker or "").replace("KRW-", "")
    return "주" if text.isdigit() else text

def _format_preview_volume(ticker, volume):
    unit = _volume_unit(ticker)
    if unit == "주":
        return f"{int(volume)}주"
    return f"{volume:.4f} {unit}"

def build_grid_preview_lines(ticker, start_price, end_price, count, budget):
    per_order_budget = float(budget) / int(count)
    lines = []
    for i in range(int(count)):
        price = float(interpolate_range(float(start_price), float(end_price), i, int(count)))
        volume = per_order_budget / price
        lines.append(
            f"{i + 1}. {price:,.0f}원 / 약 {_format_preview_volume(ticker, volume)} / {per_order_budget:,.0f}원"
        )
    return lines

def build_rsi_preview_lines(ticker, rsi_prices, budget, total_count=None):
    if not rsi_prices:
        return []
    per_order_budget = float(budget) / int(total_count or len(rsi_prices))
    lines = []
    for i, (target_rsi, price) in enumerate(rsi_prices, start=1):
        price = float(price)
        volume = per_order_budget / price
        lines.append(
            f"{i}. RSI {float(target_rsi):g} → {price:,.0f}원 / 약 {_format_preview_volume(ticker, volume)} / {per_order_budget:,.0f}원"
        )
    return lines

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

async def build_rsigrid_confirm_summary(user_id, user, intent):
    exchange = intent.get("exchange") or user.get("preferences", {}).get("default_exchange", "upbit")
    _, ticker = parse_exchange_and_ticker([exchange, intent.get("ticker")] if intent.get("ticker") else [exchange], exchange)
    buy_range = intent.get("buy_rsi_range") or user["preferences"].get("rsi_buy_range", "25-30")
    sell_range = intent.get("sell_rsi_range") or user["preferences"].get("rsi_sell_range", "65-75")
    count = int(intent.get("count") or user["preferences"].get("rsi_order_count", 5))
    budget = float(intent.get("amount_krw") or user["preferences"].get("rsi_budget_krw") or 0)
    if not ticker or budget <= 0 or count <= 0:
        return None

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
    
    full_msg = "💰 통합 자산 현황\n\n"
    total_eval_krw = 0

    for ex in exchanges:
        if ex not in ["upbit", "bithumb", "kis"]: continue
        
        balances = await exchange_adapter.get_balances(user_id, ex)
        if balances is None:
            full_msg += f"❌ {exchange_display_name(ex)}: API 키가 설정되지 않았거나 오류 발생\n\n"
            continue
            
        if ex == "kis":
            full_msg += f"🏛️ {exchange_display_name(ex)} ({'실전' if balances.get('env') == 'real' else '모의'})\n"
            cash = float(balances.get("cash", 0))
            ex_eval = float(balances.get("total_eval", 0))
            full_msg += f"- 💵 예수금: {cash:,.0f}원\n"
            others_count = 0
            others_value = 0
            for stock in balances.get("stocks", []):
                value = float(stock.get("value", 0))
                if value > min_display_krw:
                    full_msg += f"- 📈 {stock.get('name') or stock.get('code')}: {stock.get('quantity', 0):,.0f}주 ({value:,.0f}원)\n"
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

        full_msg += f"🏛️ {ex.upper()}\n"
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
                    price_info = f" ({price:,.0f}원)" if price > 0 else ""
                    full_msg += f"- 🪙 {currency}: {qty:.4f}개{price_info}\n"
                else:
                    others_count += 1
                    others_value += value
        
        # 소액 자산 요약 표시
        if others_count > 0:
            full_msg += f"- 📦 기타 {others_count}개 종목: {others_value:,.0f}원\n"
        
        full_msg += f"   └ 거래소 평가액: {ex_eval:,.0f}원\n\n"
        total_eval_krw += ex_eval

    full_msg += f"💳 총 합계 자산: {total_eval_krw:,.0f}원"
    await status_msg.edit_text(full_msg)

@check_auth
async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "orders"): return
    user_id = str(update.effective_chat.id)
    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, _ = parse_exchange_and_ticker(context.args, default_exchange)
    
    orders = order_manager.get_user_orders(user_id, exchange)
    if not orders:
        await update.message.reply_text("⏳ 현재 봇이 추적 중인 미체결 주문이 없습니다.")
        return

    msg = "⏳ 현재 추적 중인 미체결 주문\n\n"
    for ord in orders:
        msg += f"📌 [{exchange_display_name(ord['exchange'])}] {ord['ticker']}\n"
        msg += f"   └ 가격: {ord['price']:,.0f}원 | 수량: {ord['volume']:.4f}\n"
    
    await update.message.reply_text(msg)

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
        await update.message.reply_text(build_config_view(user))
        return ConversationHandler.END

    if args and args[0].lower() == "set":
        if len(args) < 3:
            await update.message.reply_text("⚠️ 사용법: /config set [항목] [값]\n예: /config set rsi_budget_krw 100만")
            return ConversationHandler.END
        key = args[1].strip().lower()
        raw_value = " ".join(args[2:]).strip()
        if key in ADMIN_ONLY_KEYS and not user.get("is_admin"):
            await update.message.reply_text("❌ 폴링 설정은 관리자만 변경할 수 있습니다.")
            return ConversationHandler.END
        try:
            value = parse_config_value(key, raw_value)
            validate_config_update(user, key, value)
        except (ValueError, TypeError) as e:
            await update.message.reply_text(f"❌ 설정 저장 실패: {e}")
            return ConversationHandler.END
        prefs = user.get("preferences", {})
        if key == "poll_active_interval":
            no_order = prefs.get("poll_no_order_interval", 300)
            if value > no_order:
                await update.message.reply_text(f"❌ poll_active_interval({value}초)은 poll_no_order_interval({no_order}초)보다 클 수 없습니다.")
                return ConversationHandler.END
        if key == "poll_no_order_interval":
            active = prefs.get("poll_active_interval", 60)
            if value < active:
                await update.message.reply_text(f"❌ poll_no_order_interval({value}초)은 poll_active_interval({active}초)보다 작을 수 없습니다.")
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
    await update.message.reply_text("설정할 거래소를 선택하세요.", reply_markup=reply_markup)
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
    if exchange == "kis":
        await update.message.reply_text("⚠️ 한국투자증권은 /grid 자동전략을 지원하지 않습니다. /buy 한투 [종목코드] [가격] [수량]을 사용하세요.")
        return
    
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
    if exchange == "kis":
        await update.message.reply_text("⚠️ 한국투자증권은 /sgrid 자동전략을 지원하지 않습니다. /sell 한투 [종목코드] [가격] [수량]을 사용하세요.")
        return
    
    offset = 2 if is_exchange_token(args[0], exchange) else 1
    
    try:
        start_p, end_p = parse_number(args[offset]), parse_number(args[offset+1])
        count, total_vol = int(args[offset+2]), parse_number(args[offset+3])
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ 숫자 형식의 파라미터가 잘못되었습니다.")
        return

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
        f"- 총 수량: {total_vol:.4f}개\n\n"
        "위 내용으로 분할 매도를 진행할까요?"
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
        
        price_step = (e_p - s_p) / (ct - 1) if ct > 1 else 0
        success_count = 0

        for i in range(ct):
            target_price = s_p + (price_step * i)
            target_price = ExchangeAdapter.adjust_price_to_tick(target_price)
            
            if is_sell:
                volume = val / ct
                volume = round(volume, 4)
                res = await exchange_adapter.create_order(user_id, ex, tk, "ask", target_price, volume)
            else:
                volume = (val / ct) / target_price
                volume = round(volume, 4)
                res = await exchange_adapter.buy_limit_order(user_id, ex, tk, target_price, volume)

            if res and 'uuid' in res:
                order_manager.add_order(
                    user_id,
                    ex,
                    tk,
                    res['uuid'],
                    target_price,
                    volume,
                    side="ask" if is_sell else "bid",
                    strategy="sgrid" if is_sell else "grid",
                )
                success_count += 1
            
            await asyncio.sleep(0.2)

        await context.bot.send_message(
            chat_id=user_id, 
            text=f"✅ `{tk}` 거미줄 {action_name} 완료! ({success_count}/{ct}건 성공)\n백그라운드에서 체결을 감시합니다."
        )

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

    ticker_data = await exchange_adapter.get_ticker(exchange, ticker, user_id=user_id)
    if not ticker_data:
        await update.message.reply_text(f"❌ {exchange_display_name(exchange)}에서 {ticker} 정보를 찾을 수 없습니다.")
        return

    # 업비트/빗썸 공통 필드 매핑
    price = float(ticker_data.get('trade_price', 0))
    change_rate = float(ticker_data.get('change_rate', 0)) * 100
    change_price = float(ticker_data.get('change_price', 0))
    high = float(ticker_data.get('high_price', 0))
    low = float(ticker_data.get('low_price', 0))
    volume = float(ticker_data.get('acc_trade_price_24h', 0))

    change_emoji = "📈" if change_rate > 0 else "📉" if change_rate < 0 else "➖"
    
    msg = (
        f"📊 [{exchange_display_name(exchange)}] {ticker} 실시간 시세\n\n"
        f"현재가: {price:,.0f}원 {change_emoji}\n"
        f"전일대비: {change_rate:+.2f}% ({change_price:,.0f}원)\n"
        f"고가(24H): {high:,.0f}원\n"
        f"저가(24H): {low:,.0f}원\n"
        f"거래대금: {volume/100000000:,.1f}억원"
    )
    await update.message.reply_text(msg)

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
    msg = f"📜 [{exchange_display_name(exchange)}] 최근 체결 내역 (최근 5건)\n\n"
    for ord in history[:5]:
        side = "🔴 매수" if ord.get('side', '').lower() in ['bid', 'buy'] else "🔵 매도"
        tk = ord.get('market', ticker)
        price = float(ord.get('price', 0))
        vol = float(ord.get('volume', 0))
        date = ord.get('created_at', '').split('T')[0]

        msg += f"- {date} | {side} | {tk}\n"
        msg += f"  └ {price:,.0f}원 | {vol:.4f}개\n"

    await update.message.reply_text(msg)

def build_manual_order_confirm_message(exchange, ticker, side, price, volume, user):
    action = "매수" if side == "bid" else "매도"
    env_notice = ""
    if exchange == "kis":
        env = user.get("exchanges", {}).get("kis", {}).get("env", "paper")
        env_notice = f" ({'실전' if env == 'real' else '모의'})"
        volume_text = f"{float(volume):,.0f}주"
    else:
        volume_text = f"{float(volume):.8f}".rstrip("0").rstrip(".")
    return (
        f"{'📈' if side == 'bid' else '📉'} {exchange_display_name(exchange)} {action} 주문 확인{env_notice}\n\n"
        f"- 종목: {ticker}\n"
        f"- 가격: {float(price):,.0f}원\n"
        f"- 수량: {volume_text}\n"
        f"- 주문금액: {float(price) * float(volume):,.0f}원\n\n"
        "위 내용으로 주문을 전송할까요?"
    )

@check_auth
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "buy"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("⚠️ 사용법: /buy [거래소] [종목] [가격] [수량] (거래소 생략 시 업비트)")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)
    
    offset = 2 if is_exchange_token(args[0], exchange) else 1
    
    try:
        price = parse_number(args[offset])
        volume = parse_number(args[offset+1])
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ 가격과 수량은 숫자여야 합니다.")
        return

    ok, error_msg = validate_max_order(user, price * volume)
    if not ok:
        await update.message.reply_text(error_msg)
        return

    confirm_data = f"manualrun|{exchange}|bid|{ticker}|{price}|{volume}"
    keyboard = [[InlineKeyboardButton("✅ 매수 실행", callback_data=confirm_data),
                 InlineKeyboardButton("❌ 취소", callback_data="manual_cancel")]]
    await update.message.reply_text(
        build_manual_order_confirm_message(exchange, ticker, "bid", price, volume, user),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

@check_auth
async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "sell"): return
    user_id = str(update.effective_chat.id)
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("⚠️ 사용법: /sell [거래소] [종목] [가격] [수량] (거래소 생략 시 업비트)")
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = parse_exchange_and_ticker(args, default_exchange)
    
    offset = 2 if is_exchange_token(args[0], exchange) else 1
    
    try:
        price = parse_number(args[offset])
        volume = parse_number(args[offset+1])
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ 가격과 수량은 숫자여야 합니다.")
        return

    confirm_data = f"manualrun|{exchange}|ask|{ticker}|{price}|{volume}"
    keyboard = [[InlineKeyboardButton("✅ 매도 실행", callback_data=confirm_data),
                 InlineKeyboardButton("❌ 취소", callback_data="manual_cancel")]]
    await update.message.reply_text(
        build_manual_order_confirm_message(exchange, ticker, "ask", price, volume, user),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def manual_order_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "manual_cancel":
        await query.edit_message_text("❌ 주문이 취소되었습니다.")
        return

    _, exchange, side, ticker, price, volume = query.data.split("|")
    user_id = str(query.from_user.id)
    user = user_manager.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 주문을 중단합니다.")
        return

    price = float(price)
    volume = float(volume)
    if side == "bid":
        ok, error_msg = validate_max_order(user, price * volume)
        if not ok:
            await query.edit_message_text(error_msg)
            return

    env_notice = ""
    if exchange == "kis":
        env = user.get("exchanges", {}).get("kis", {}).get("env", "paper")
        env_notice = f" ({'실전' if env == 'real' else '모의'})"
    action = "매수" if side == "bid" else "매도"
    await query.edit_message_text(f"🚀 {exchange_display_name(exchange)} {ticker} {action} 주문 전송 중{env_notice}...")

    res = await exchange_adapter.create_order(user_id, exchange, ticker, side, price, volume)
    if res and "uuid" in res:
        order_manager.add_order(user_id, exchange, ticker, res["uuid"], price, volume, side=side, strategy="manual")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ {exchange_display_name(exchange)} {ticker} {action} 주문 완료{env_notice}!\n주문ID: {res['uuid']}",
        )
    else:
        await context.bot.send_message(chat_id=user_id, text=f"❌ 주문 실패: {res}")

# --- 주문 동기화 및 자동 대응 엔진 ---
async def sync_orders(application):
    """현재 추적 중인 주문들의 상태를 거래소와 동기화하고 자동 대응 수행"""
    all_orders = list(order_manager.orders)
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
                        order_manager.add_order(user_id, exchange, ticker, s_res['uuid'], sell_price, sell_volume, 
                                             side="ask", strategy="rsitrade_sell", target_rsi=target_rsi)
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
            order_manager.remove_order(ord['uuid'])
        elif state != ord.get("status"):
            order_manager.update_order_status(ord['uuid'], state)
        
        await asyncio.sleep(0.2)

@check_auth
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "status"): return
    user_id = str(update.effective_chat.id)
    orders = order_manager.get_user_orders(user_id)
    
    if not orders:
        await update.message.reply_text("📊 현재 가동 중인 트레이딩 전략이 없습니다.")
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
        
        msg += f"🏛️ {ex.upper()}\n"
        
        # 전략별 그룹화 (종목별)
        tickers = sorted(list(set([o['ticker'] for o in ex_orders])))
        for tk in tickers:
            tk_orders = [o for o in ex_orders if o['ticker'] == tk]
            # 진행률 계산
            total = len(tk_orders)
            filled = len([o for o in tk_orders if o['status'] == 'done']) # 실제로는 done이면 삭제되므로 현재 추적 중인 개수 위주
            
            # rsitrade와 일반 grid 구분
            is_rsi = any(o['strategy'].startswith('rsitrade') for o in tk_orders)
            strategy_name = "RSI 순환 매매" if is_rsi else "거미줄 분할 매매"
            
            prog_total = total # 현재 추적 중인 주문 수
            prog_bar = "🔵" * filled + "⚪" * (prog_total - filled)
            
            msg += f"• {tk} {strategy_name}\n"
            msg += f"  └ 상태: {prog_bar} ({prog_total}건 추적 중)\n"
            
            # 상세 주문 (최대 3건)
            for i, o in enumerate(tk_orders[:3]):
                side_str = "매수" if o['side'] == 'bid' else "매도"
                target = f"RSI {o['target_rsi']}" if o['target_rsi'] else f"{o['price']:,.0f}원"
                state_text = status_names.get(o.get("status"), o.get("status", "대기"))
                msg += f"    - {i+1}. {side_str} {state_text}: {target}\n"
            if len(tk_orders) > 3: msg += "    - ... 그 외 생략\n"
        msg += "\n"

    msg += "ℹ️ 체결 및 외부 취소 시 실시간 알림이 전송됩니다."
    await update.message.reply_text(msg)

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
        sell_rsi_range = args[offset+1] if len(args) > offset + 1 else preferences.get("rsi_sell_range", "65-75")
        count = int(args[offset+2]) if len(args) > offset + 2 else int(preferences.get("rsi_order_count", 5))
        budget = parse_number(args[offset+3]) if len(args) > offset + 3 else preferences.get("rsi_budget_krw")
        if budget is None:
            await update.message.reply_text(
                "⚠️ RSI 전략 예산이 필요합니다. 명령어에 예산을 입력하거나 /config set rsi_budget_krw 100만으로 기본 예산을 저장하세요."
            )
            return
        budget = float(budget)
        
        b_start, b_end = parse_rsi_range(buy_rsi_range)
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
    confirm_data = f"rsitrun|{exchange}|{ticker}|{buy_rsi_range}|{sell_rsi_range}|{count}|{budget}"
    keyboard = [[InlineKeyboardButton("✅ 전략 가동 시작", callback_data=confirm_data),
                 InlineKeyboardButton("❌ 취소", callback_data="grid_cancel")]]
    
    preview_text = "\n".join(build_rsi_preview_lines(ticker, buy_prices, budget, count))
    summary = (
        f"🤖 RSI 순환 매매 전략 확인\n\n"
        f"전략 설정\n"
        f"- 거래소: {exchange.upper()}\n"
        f"- 종목: {ticker}\n"
        f"- 매집(RSI): {buy_rsi_range} ({buy_prices[0][1]:,.0f} ~ {buy_prices[-1][1]:,.0f}원)\n"
        f"- 익절(RSI): {sell_rsi_range} 목표\n"
        f"- 분할: {count}회 | 총예산: {budget:,.0f}원\n\n"
        "체결 시 자동으로 익절 주문이 예약됩니다. 시작할까요?"
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
        await query.edit_message_text("⚠️ 한국투자증권 RSI는 일봉만 지원합니다. /config set rsi_interval day 후 다시 시도하세요.")
        return
    ok, error_msg = validate_max_order(user, bg / ct)
    if not ok:
        await query.edit_message_text(error_msg)
        return
    
    await query.edit_message_text(f"🚀 {tk} RSI 순환 매매를 시작합니다. 매수 주문 전송 중...")
    
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
        
        res = await exchange_adapter.create_order(user_id, ex, tk, "bid", price, volume)
        if res and 'uuid' in res:
            # linked_to에 매도 RSI 범위를 저장하여 체결 시 참고
            order_manager.add_order(user_id, ex, tk, res['uuid'], price, volume, 
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

# --- 백그라운드 루프 엔진 ---
def _get_admin_prefs() -> dict:
    for user in user_manager.users.values():
        if user.get("is_admin"):
            return {**UserManager.DEFAULT_PREFERENCES, **user.get("preferences", {})}
    return dict(UserManager.DEFAULT_PREFERENCES)

def build_account_summary(user_id, user):
    prefs = user.get("preferences", {})
    role = "관리자" if user.get("is_admin") else "일반 사용자"
    active = "활성" if user.get("is_active") else "승인 대기"
    llm = "on" if prefs.get("llm_enabled") else "off"
    default_exchange = prefs.get("default_exchange", "upbit")
    secret_status = "\n보안 키: 복호화 오류" if user.get("_secret_error") else ""
    return (
        "👤 내 계정\n\n"
        f"ID: {user_id}\n"
        f"권한: {role}\n"
        f"상태: {active}\n"
        f"기본 거래소: {default_exchange}\n"
        f"자연어: {llm}"
        f"{secret_status}"
    )

async def _interruptible_sleep(seconds: float):
    try:
        await asyncio.wait_for(_order_wake_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass

async def order_sync_loop(application):
    print("📦 오더 동기화 루프 가동")
    while True:
        _order_wake_event.clear()
        try:
            prefs = _get_admin_prefs()
            await sync_orders(application)
            interval = prefs["poll_active_interval"] if order_manager.orders \
                       else prefs["poll_no_order_interval"]
            await _interruptible_sleep(interval)
        except Exception as e:
            print(f"⚠️ 오더 동기화 루프 에러: {e}")
            await _interruptible_sleep(60)

async def signal_analysis_loop(application):
    print("📡 시그널 분석 루프 가동")
    await asyncio.sleep(5)
    while True:
        try:
            prefs = _get_admin_prefs()
            await signal_engine.analyze_watchlist(application)
            await asyncio.sleep(prefs["signal_analysis_interval"])
        except Exception as e:
            print(f"⚠️ 시그널 분석 루프 에러: {e}")
            await asyncio.sleep(300)

# --- 자동 복구 및 초기화 로직 ---
async def startup_recovery(application):
    """봇 시작 시 미완료된 전략 주문들을 점검하고 복구"""
    print("🛠️ 시스템 자동 복구 프로세스 가동...")
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
        print(f"✅ {recovered_count}건의 전략 주문이 복구 프로세스에 편입되었습니다.")

async def post_init(application):
    """봇 초기화 후 백그라운드 태스크 실행"""
    global _order_wake_event
    _order_wake_event = asyncio.Event()
    order_manager.on_order_added = lambda: _order_wake_event.set()
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
        print(f"⚠️ Telegram command menu update failed: {e}")
    await startup_recovery(application)
    asyncio.create_task(order_sync_loop(application))
    asyncio.create_task(signal_analysis_loop(application))

async def post_shutdown(application):
    """봇 종료 시 외부 연결을 정리합니다."""
    await exchange_adapter.close()

# --- 디버그용 글로벌 메시지 핸들러 ---
async def global_debug_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        print(f"📡 [GLOBAL DEBUG] 메시지 수신 from={update.effective_user.id}, length={len(update.message.text)}")
    return

def build_help_message(user):
    admin_lines = ["- /nlstats: 자연어 전처리 후보 통계 (관리자 전용)", "- /diag: 운영 진단 (관리자 전용)"] if user.get("is_admin") else []
    sections = [
        f"📖 {BOT_DISPLAY_NAME} 사용 설명서",
        "상세 가이드: /[명령어] -h  예: /rsitrade -h",
        "",
        format_section("기본 및 설정", [
            "- /start: 시스템 접속 및 메뉴 확인",
            "- /status: 가동 중인 트레이딩 전략 대시보드",
            "- /config: 거래소, LLM API 설정",
            "- /info: 봇 버전 및 빌드 정보 확인",
            "- /whomai: 내 계정 권한과 상태 확인 (/me 가능)",
            *admin_lines,
            "- /help: 명령어 도움말 확인",
        ]),
        "",
        format_section("자산 및 시세 조회", [
            "- /asset: 통합 자산 및 소액 자산 요약 조회",
            "- /price [종목]: 실시간 시세 및 변동률 (단축: /p)",
            "- /history [종목]: 최근 체결 내역 확인 (5건)",
        ]),
        "",
        format_section("자동 거래 및 순환 매매", [
            "- /rsitrade [종목] [매수RSI] [매도RSI] [횟수] [예산]",
            "  예: /rsitrade BTC 25-30 65-75 5 200만",
            "- /grid [종목] [시작가] [종료가] [횟수] [예산]: 분할 매수",
            "- /sgrid [종목] [시작가] [종료가] [횟수] [수량]: 분할 매도",
            "- /orders: 미체결 주문 및 추적 목록",
            "- /cancel [종목]: 해당 종목 주문 일괄 취소",
        ]),
        "",
        format_section("시그널 감시", [
            "- /watch [종목]: RSI 매수 시그널 실시간 감시",
            "- /unwatch [종목]: 감시 목록에서 제거",
        ]),
        "",
        "주의: 모든 주문은 거래소 앱과 실시간 동기화됩니다.",
    ]
    return "\n".join(sections)

@check_auth
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    await update.message.reply_text(build_help_message(user))

@check_auth
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "info"): return
    short_sha = GIT_SHA[:7] if GIT_SHA != "unknown" else "unknown"
    msg = (
        f"ℹ️ {BOT_DISPLAY_NAME} 빌드 정보\n\n"
        f"- 버전: {VERSION}\n"
        f"- 빌드: {BUILD_DATE}\n"
        f"- 커밋: {short_sha}"
    )
    await update.message.reply_text(msg)

@check_auth
async def diag_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if not user.get("is_admin"):
        await update.message.reply_text("운영 진단은 관리자만 조회할 수 있습니다.")
        return
    await update.message.reply_text(build_diag_view(user))

@check_auth
async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    user_id = str(update.effective_chat.id)
    await update.message.reply_text(build_account_summary(user_id, user))

def recommend_nl_preprocess_action(text_norm):
    text = str(text_norm or "").lower()
    compact = re.sub(r"\s+", "", text)
    if any(hint in compact for hint in ["주문대기", "예약주문", "추적중", "전략주문"]):
        return "status"
    if any(hint in compact for hint in ["미체결", "오픈오더", "openorder"]):
        return "orders"
    if any(hint in compact for hint in ["잔고", "자산", "계좌현황"]):
        return "asset"
    if any(hint in compact for hint in ["시세", "가격", "현재가"]):
        return "price"
    if any(hint in compact for hint in ["설정", "api등록", "gemini", "llm"]):
        return "config_view"
    if any(hint in compact for hint in ["체결내역", "거래내역", "최근체결"]):
        return "history"
    return None

@check_auth
async def nlstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if not user.get("is_admin"):
        await update.message.reply_text("자연어 로그 통계는 관리자만 조회할 수 있습니다.")
        return
    args = [str(arg).lower() for arg in context.args]
    if args[:1] == ["export"]:
        try:
            limit = int(args[1]) if len(args) > 1 else 20
        except ValueError:
            limit = 20
        rows = read_recent_natural_language_logs(limit=limit)
        if not rows:
            await update.message.reply_text("내보낼 자연어 로그가 없습니다.")
            return
        lines = [f"최근 익명 자연어 로그 {len(rows)}건"]
        for row in rows:
            lines.append(f"- {row.get('text_norm')} / LLM:{row.get('llm_action')} / Final:{row.get('final_action')}")
        await update.message.reply_text("\n".join(lines))
        return
    if args[:1] == ["hits"]:
        hits = read_preprocess_hit_stats()
        if not hits:
            await update.message.reply_text("아직 자연어 전처리 hit 통계가 없습니다.")
            return
        lines = ["자연어 전처리 hit 통계"]
        for action, count in sorted(hits.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {action}: {count}")
        await update.message.reply_text("\n".join(lines))
        return
    if args[:1] == ["clear"]:
        if args[1:2] != ["confirm"]:
            await update.message.reply_text("자연어 로그와 hit 통계를 초기화하려면 /nlstats clear confirm을 입력하세요.")
            return
        clear_natural_language_logs()
        await update.message.reply_text("자연어 로그와 hit 통계를 초기화했습니다.")
        return

    rows = read_natural_language_log_stats()
    hits = read_preprocess_hit_stats()
    if not rows and not hits:
        await update.message.reply_text("아직 자연어 통계가 없습니다.")
        return

    lines = ["자연어 전처리 후보 상위 패턴"]
    if rows:
        for i, row in enumerate(rows, start=1):
            llm_actions = ", ".join(f"{k}:{v}" for k, v in row["llm_actions"].items())
            final_actions = ", ".join(f"{k}:{v}" for k, v in row["final_actions"].items())
            lines.append(
                f"{i}. {row['text_norm']} ({row['count']}회)\n"
                f"   LLM: {llm_actions} / Final: {final_actions}"
            )
    else:
        lines.append("- 미처리 패턴 없음")
    if hits:
        hit_text = ", ".join(f"{action}:{count}" for action, count in sorted(hits.items()))
        lines.append(f"\n전처리 hit: {hit_text}")
    recommendations = []
    for row in rows[:5]:
        action = recommend_nl_preprocess_action(row.get("text_norm"))
        if action:
            recommendations.append(f"- {row.get('text_norm')} → {action}")
    if recommendations:
        lines.append("\n추천 전처리 후보")
        lines.extend(recommendations)
    await update.message.reply_text("\n".join(lines))

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
    if action == "rsitrade":
        status_msg = await update.message.reply_text(f"🔍 RSI 가격 분석 중...")
        confirm_text = await build_rsigrid_confirm_summary(str(update.effective_chat.id), user, intent)
        if not confirm_text:
            await status_msg.edit_text("❌ RSI 가격 역산에 실패했습니다. 데이터를 불러올 수 없습니다.")
            return

    token = str(len(_pending_nl_intents) + 1)
    _pending_nl_intents[token] = {"user_id": str(update.effective_chat.id), "intent": intent}
    keyboard = [[InlineKeyboardButton("✅ 실행", callback_data=f"nlrun|{token}"),
                 InlineKeyboardButton("❌ 취소", callback_data=f"nlcancel|{token}")]]
    if action == "rsitrade":
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
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN 누락")
        return

    # post_init을 통해 백그라운드 태스크를 봇 생명주기에 안전하게 편입시킵니다.
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

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
    application.add_handler(CommandHandler("nlstats", nlstats_command))
    application.add_handler(CommandHandler("diag", diag_command))
    application.add_handler(CommandHandler("asset", asset_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("p", price_command))
    application.add_handler(CommandHandler("history", history_command))
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
    application.add_handler(CallbackQueryHandler(approve_callback, pattern="^approve_"))
    application.add_handler(CallbackQueryHandler(grid_quick_callback, pattern="^grid_quick_"))
    application.add_handler(CallbackQueryHandler(grid_confirm_callback, pattern="^(gridrun|sgridrun|grid_cancel)"))
    application.add_handler(CallbackQueryHandler(rsitrade_confirm_callback, pattern="^rsitrun"))
    application.add_handler(CallbackQueryHandler(manual_order_confirm_callback, pattern="^(manualrun|manual_cancel)"))
    application.add_handler(CallbackQueryHandler(natural_language_confirm_callback, pattern="^nl(run|cancel)\\|"))
    
    # [중요] 알 수 없는 명령어 처리 (가장 마지막에 등록)
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_language_command))

    print(f"🚀 {BOT_DISPLAY_NAME} 가동 중...")
    
    # 동기식으로 실행 (자체 이벤트 루프를 안전하게 생성합니다)
    application.run_polling()
    
if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
