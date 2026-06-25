import html as _html
from collections import defaultdict

from core.parsers import (
    exchange_display_name,
    has_gemini_key,
    interpolate_range,
    _format_preview_volume,
    POLL_INTERVAL_KEYS,
    parse_rsi_interval,
    _format_seconds,
    is_us_stock_ticker,
)
from core.exchanges.kis import KisExchange
from core.secret_crypto import can_decrypt_secrets, has_secret_key
from core.stock_resolver import kr_stock_display

_kis_exchange = KisExchange(None)

BOT_DISPLAY_NAME = "TTBot"


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _b(s):
    return f"<b>{_html.escape(str(s))}</b>"


def _i(s):
    return f"<i>{_html.escape(str(s))}</i>"


def _code(s):
    return f"<code>{_html.escape(str(s))}</code>"


# ── 명령어별 상세 도움말 ────────────────────────────────────────────────────────

CMD_HELP = {
    "start": (
        f"🎁 <b>/start 상세 가이드</b>\n\n"
        "<b>기능:</b> 봇을 시작하고 시스템에 등록을 요청하거나 메뉴를 불러옵니다.\n"
        "<b>사용법:</b> <code>/start</code>만 입력\n\n"
        "<b>안내:</b>\n"
        "• 처음 사용 시 관리자의 승인이 필요합니다.\n"
        "• 승인 후에는 언제든지 <code>/start</code>로 주요 메뉴를 다시 볼 수 있습니다."
    ),
    "config": (
        "⚙️ <b>/config 상세 가이드</b>\n\n"
        "<b>기능:</b> 거래소 API 키와 사용자 기본 설정을 관리합니다.\n\n"
        "<b>API 키 설정:</b> <code>/config</code> 입력 후 버튼 클릭\n"
        "1. 거래소 선택 (Upbit, Bithumb, 한국투자증권, 토스증권, Gemini)\n"
        "2. 거래소별 Key 입력 (메시지 삭제됨)\n"
        "3. 한국투자증권은 계좌번호, 상품코드, 모의/실전 환경까지 입력\n"
        "4. 토스증권은 Client ID → Client Secret 순서로 입력 (account_seq 자동 조회)\n"
        "5. 자동 유효성 검증 수행\n\n"
        "<b>설정 조회:</b> <code>/config -v</code>\n"
        "API 키 값은 표시하지 않고 설정 여부만 보여줍니다.\n\n"
        "<b>설정 변경:</b> <code>/config set [항목] [값]</code>\n"
        "• <code>default_exchange</code>: upbit, bithumb, kis, toss, 업비트, 빗썸, 한투, 토스증권\n"
        "• <code>asset_min_display_krw</code>: <code>/asset</code> 개별 표시 최소 평가액\n"
        "• <code>rsi_buy_range</code>: 예: 25-30\n"
        "• <code>rsi_sell_range</code>: 예: 65-75\n"
        "• <code>rsi_order_count</code>: 예: 5\n"
        "• <code>rsi_budget_krw</code>: 예: 100만 또는 off\n"
        "• <code>rsi_interval</code>: day 또는 1/3/5/10/15/30/60/240\n"
        "• <code>signal_alerts</code>: on/off\n"
        "• <code>signal_rsi_threshold</code>: 예: 30\n"
        "• <code>max_order_krw</code>: 예: 50만 또는 off\n"
        "• <code>max_open_exposure_krw</code>: 미체결 총 노출 한도, 예: 500만 또는 off\n"
        "• <code>llm_enabled</code>: on/off\n"
        "• <code>llm_model</code>: 예: gemini-2.5-flash-lite\n\n"
        "<b>폴링 설정 (관리자 전용):</b>\n"
        "• <code>poll_active_interval</code>: 오더 있을 때 주기 (초, 기본 60)\n"
        "• <code>poll_no_order_interval</code>: 오더 없을 때 fallback 주기 (초, 기본 300)\n"
        "• <code>signal_analysis_interval</code>: 시그널 분석 주기 (초, 기본 300)\n\n"
        "<b>예시:</b>\n"
        "<code>/config set asset_min_display_krw 10000</code>\n"
        "<code>/config set rsi_budget_krw 100만</code>\n"
        "<code>/config set rsi_interval day</code>\n"
        "<code>/config set llm_enabled on</code>\n"
        "<code>/config set max_order_krw 50만</code>\n"
        "<code>/config set poll_active_interval 30</code>\n\n"
        "⚠️ 보안을 위해 입력한 키 메시지는 즉시 자동 삭제됩니다."
    ),
    "asset": (
        "💰 <b>/asset 상세 가이드</b>\n\n"
        "<b>기능:</b> 내 거래소 잔고와 총 평가액을 조회합니다.\n"
        "<b>구문:</b> <code>/asset [거래소]</code>\n\n"
        "<b>옵션:</b>\n"
        "• <code>거래소</code>: 업비트, 빗썸, 한투, 토스증권 (생략 시 전체 조회)\n\n"
        "<b>예시:</b>\n"
        "1. <code>/asset</code> (모든 거래소 조회)\n"
        "2. <code>/asset 빗썸</code> (빗썸 잔고만 조회)\n"
        "3. <code>/asset 토스증권</code> (토스증권 잔고만 조회)\n"
        "⚠️ 설정한 최소 표시 금액 이하의 소액 자산은 '기타'로 합산 표시됩니다."
    ),
    "price": (
        "📊 <b>/price 상세 가이드</b>\n\n"
        "<b>기능:</b> 특정 종목의 실시간 시세를 조회합니다.\n"
        "<b>구문:</b> <code>/price [거래소] [종목]</code>\n\n"
        "<b>옵션:</b>\n"
        "• <code>거래소</code>: 업비트, 빗썸, 한투, 토스증권 (생략 시 기본 거래소 우선)\n"
        "• <code>종목</code>: 업비트/빗썸은 BTC, ETH 등 (KRW- 자동 보완), 한국투자증권·토스증권은 005930 같은 국내주식 종목코드\n\n"
        "<b>예시:</b>\n"
        "1. <code>/p BTC</code> (업비트 비트코인 시세)\n"
        "2. <code>/price 빗썸 ETH</code> (빗썸 이더리움 시세)\n"
        "3. <code>/p KRW-XRP</code> (KRW- 포함 직접 입력도 가능)\n"
        "4. <code>/price 한투 005930</code> (한국투자증권 삼성전자 시세)\n"
        "5. <code>/price 토스증권 005930</code> (토스증권 삼성전자 시세)\n"
        "6. <code>/price 토스증권 AAPL</code> (토스증권 해외주식 애플 시세, USD 표시)\n\n"
        "🌎 토스증권은 해외(미국)주식도 지원합니다. 종목코드 대신 AAPL, TSLA 같은 티커를 입력하세요."
    ),
    "indicators": (
        "📈 <b>/indicators 상세 가이드</b>\n\n"
        "<b>기능:</b> RSI, MACD, 볼린저밴드, 스토캐스틱을 한 번에 조회합니다.\n"
        "<b>구문:</b> <code>/indicators [거래소] [종목] [봉기준]</code>\n\n"
        "<b>옵션:</b>\n"
        "• <code>거래소</code>: 업비트, 빗썸, 한투, 토스증권 (생략 시 기본 거래소)\n"
        "• <code>종목</code>: BTC, ETH, 005930 등\n"
        "• <code>봉기준</code>: day(일봉, 기본값), 60, 240 등 분봉 (한투·토스증권은 일봉만 지원)\n\n"
        "<b>예시:</b>\n"
        "1. <code>/indicators BTC</code> (업비트 비트코인 일봉 지표)\n"
        "2. <code>/ind BTC 60</code> (업비트 비트코인 60분봉 지표)\n"
        "3. <code>/indicators 빗썸 ETH</code> (빗썸 이더리움 지표)\n"
        "4. <code>/indicators 토스증권 005930</code> (토스증권 삼성전자 일봉 지표)"
    ),
    "history": (
        "📜 <b>/history 상세 가이드</b>\n\n"
        "<b>기능:</b> 나의 최근 체결(완료)된 주문 내역을 보여줍니다.\n"
        "<b>구문:</b> <code>/history [거래소] [종목]</code>\n\n"
        "<b>옵션:</b>\n"
        "• <code>거래소</code>: 업비트, 빗썸, 한투, 토스증권\n"
        "• <code>종목</code>: 특정 종목 내역만 필터링 (생략 시 전체)\n\n"
        "<b>예시:</b>\n"
        "1. <code>/history</code> (업비트 전체 최근 내역)\n"
        "2. <code>/history 빗썸</code> (빗썸 전체 최근 내역)\n"
        "3. <code>/history BTC</code> (업비트 비트코인 거래 내역)\n"
        "4. <code>/history 토스증권 005930</code> (토스증권 삼성전자 내역)"
    ),
    "buy": (
        "🛍️ <b>/buy 상세 가이드 (단일 매수)</b>\n\n"
        "<b>기능:</b> 지정한 거래소에 단일 매수 주문을 즉시 전송합니다.\n"
        "<b>구문:</b> <code>/buy [거래소] [종목] [가격] [수량]</code>\n\n"
        "<b>예시:</b>\n"
        "<code>/buy 빗썸 BTC 95000000 0.1</code> (빗썸에서 0.1 BTC를 9500만원에 매수)\n"
        "<code>/buy 한투 005930 70000 1</code> (한국투자증권에서 삼성전자 1주 매수 확인)\n"
        "<code>/buy 토스증권 005930 70000 1</code> (토스증권에서 삼성전자 1주 매수 확인)\n"
        "<code>/buy 토스증권 AAPL 185.5 10</code> (토스증권 해외주식 애플 10주 매수, USD)\n\n"
        "🌎 토스증권은 AAPL, TSLA 등 해외(미국)주식 티커 입력 시 USD로 자동 처리됩니다 (한투는 국내전용).\n"
        "⚠️ 한국투자증권·토스증권 주문은 확인 버튼을 거친 뒤 전송됩니다."
    ),
    "sell": (
        "🛍️ <b>/sell 상세 가이드 (단일 매도)</b>\n\n"
        "<b>기능:</b> 지정한 거래소에 단일 매도 주문을 즉시 전송합니다.\n"
        "<b>구문:</b> <code>/sell [거래소] [종목] [가격] [수량]</code>\n\n"
        "<b>예시:</b>\n"
        "<code>/sell BTC 120000000 0.5</code> (업비트에서 0.5 BTC를 1.2억원에 매도)\n"
        "<code>/sell 토스증권 005930 72000 1</code> (토스증권에서 삼성전자 1주 매도)\n"
        "<code>/sell 토스증권 AAPL 190 10</code> (토스증권 해외주식 애플 10주 매도, USD)\n\n"
        "⚠️ 보유 수량이 주문 수량보다 많아야 합니다."
    ),
    "grid": (
        "🕸️ <b>/grid 상세 가이드 (거미줄 분할 매수)</b>\n\n"
        "<b>기능:</b> 지정가 범위 내에서 예산을 분할하여 여러 개의 매수 주문을 겁니다.\n"
        "<b>구문:</b> <code>/grid [거래소] [종목] [시작가] [종료가] [횟수] [총예산]</code>\n\n"
        "<b>예시:</b>\n"
        "<code>/grid BTC 1억 9천 10 100만</code> (1억~9천 사이 10번 분할 매수)\n"
        "<code>/grid 빗썸 ETH 400만 350만 5 50만</code> (빗썸 이더리움 5분할 매수)\n"
        "<code>/grid 한투 005930 71000 69000 5 100만</code> (한국투자증권 삼성전자 5분할 매수)\n"
        "<code>/grid 토스증권 005930 71000 69000 5 100만</code> (토스증권 삼성전자 5분할 매수)\n"
        "<code>/grid 토스증권 AAPL 190 180 5 1000</code> (토스증권 해외주식 애플 190~180달러 5분할 매수, 총예산 1000달러)\n\n"
        "<b>파라미터:</b>\n"
        "• 종목: 업비트/빗썸은 BTC, ETH 등 KRW- 생략 가능 (자동 보완), 한투/토스증권은 005930 같은 종목코드, 토스증권 해외주식은 AAPL 같은 티커\n"
        "• 횟수: 몇 번에 나눠서 주문할지 지정\n"
        "• 총예산: 전체 주문에 투입할 금액 (국내는 원화(KRW), 토스증권 해외주식은 달러(USD))"
    ),
    "sgrid": (
        "🕸️ <b>/sgrid 상세 가이드 (거미줄 분할 매도)</b>\n\n"
        "<b>기능:</b> 지정가 범위 내에서 보유 수량을 분할하여 여러 개의 매도 주문을 겁니다.\n"
        "<b>구문:</b> <code>/sgrid [거래소] [종목] [시작가] [종료가] [횟수] [총수량]</code>\n\n"
        "<b>예시:</b>\n"
        "<code>/sgrid BTC 1.1억 1.2억 5 0.1</code> (비트코인 0.1개 5분할 매도)\n"
        "<code>/sgrid 빗썸 ETH 400만 450만 5 0.5</code> (빗썸 이더리움 0.5개 분할 매도)\n"
        "<code>/sgrid 한투 005930 71000 73000 5 5</code> (한국투자증권 삼성전자 5주 5분할 매도)\n"
        "<code>/sgrid 토스증권 005930 71000 73000 5 5</code> (토스증권 삼성전자 5주 5분할 매도)\n"
        "<code>/sgrid 토스증권 AAPL 190 200 5 10</code> (토스증권 해외주식 애플 10주 5분할 매도, USD)\n\n"
        "<b>파라미터:</b>\n"
        "• 종목: 업비트/빗썸은 BTC, ETH 등 KRW- 생략 가능 (자동 보완), 한투/토스증권은 005930 같은 종목코드, 토스증권 해외주식은 AAPL 같은 티커\n"
        "• 횟수: 몇 번에 나눠서 팔지 지정\n"
        "• 총수량: 전체 매도할 코인 개수 또는 주식 수량"
    ),
    "orders": (
        "⏳ <b>/orders 상세 가이드</b>\n\n"
        "<b>기능:</b> 현재 거래소에 걸려있는 미체결 주문 목록을 확인합니다.\n"
        "<b>구문:</b> <code>/orders [거래소]</code>\n\n"
        "<b>옵션:</b>\n"
        "• <code>거래소</code>: 업비트, 빗썸, 한투, 토스증권 (생략 시 기본 거래소)\n\n"
        "<b>안내:</b>\n"
        "봇을 통해 생성한 주문뿐만 아니라 직접 거래소에서 건 미체결 주문도 모두 조회됩니다."
    ),
    "cancel": (
        "🛑 <b>/cancel 상세 가이드</b>\n\n"
        "<b>기능:</b> 특정 종목의 모든 미체결 주문을 일괄 취소합니다.\n"
        "<b>구문:</b> <code>/cancel [거래소] [종목]</code>\n\n"
        "<b>예시:</b>\n"
        "1. <code>/cancel BTC</code> (업비트 비트코인 주문 취소)\n"
        "2. <code>/cancel 빗썸 SOL</code> (빗썸 솔라나 주문 취소)\n"
        "3. <code>/cancel 토스증권 005930</code> (토스증권 삼성전자 주문 취소)\n\n"
        "<b>안내:</b> 실행 전 취소 대상 주문 목록과 확인 버튼이 표시됩니다."
    ),
    "cancelno": (
        "🔢 <b>/cancelno 상세 가이드</b>\n\n"
        "<b>기능:</b> 배치 번호(#N)로 전략 주문 묶음을 일괄 취소합니다.\n"
        "<b>구문:</b> <code>/cancelno [배치번호]</code>\n\n"
        "<b>예시:</b>\n"
        "1. <code>/cancelno 1</code> — #1 배치 주문 전체 취소\n"
        "2. <code>/cancelno 3</code> — #3 배치 주문 전체 취소\n\n"
        "<b>배치 번호 확인:</b> <code>/status</code> 또는 <code>/orders</code>에서 [#N]으로 표시됩니다.\n"
        "<b>안내:</b> 실행 전 취소 대상 주문 목록과 확인 버튼이 표시됩니다."
    ),
    "watch": (
        "🔔 <b>/watch 상세 가이드</b>\n\n"
        "<b>기능:</b> 특정 종목의 RSI 지표를 실시간 감시하여 매수 시그널을 알립니다.\n"
        "<b>구문:</b> <code>/watch [거래소] [종목]</code>\n\n"
        "<b>예시:</b>\n"
        "1. <code>/watch BTC</code> (업비트 비트코인 감시 시작)\n"
        "2. <code>/watch 빗썸 SOL</code> (빗썸 솔라나 감시 시작)\n"
        "3. <code>/watch 토스증권 005930</code> (토스증권 삼성전자 일봉 RSI 감시)"
    ),
    "unwatch": (
        "🔕 <b>/unwatch 상세 가이드</b>\n\n"
        "<b>기능:</b> RSI 시그널 감시 목록에서 특정 종목을 제거합니다.\n"
        "<b>구문:</b> <code>/unwatch [거래소] [종목]</code>\n\n"
        "<b>예시:</b>\n"
        "<code>/unwatch BTC</code> (비트코인 감시 종료)\n"
        "<code>/unwatch 토스증권 005930</code> (토스증권 삼성전자 감시 종료)"
    ),
    "rsitrade": (
        "🤖 <b>/rsitrade 상세 가이드</b>\n\n"
        "<b>기능:</b> RSI 목표 구간을 기준으로 분할 매수하고, 체결 시 RSI 매도 목표 주문을 예약합니다.\n"
        "<b>구문:</b> <code>/rsitrade [거래소] [종목] [매수RSI] [매도RSI] [횟수] [예산]</code>\n\n"
        "<b>기본값:</b> 종목만 입력하면 <code>/config</code>에 저장된 매수RSI, 매도RSI, 횟수, 예산을 사용합니다.\n"
        "<b>매수만:</b> 매도RSI 자리에 <code>-</code>를 입력하면 자동 매도 예약 없이 매수만 진행합니다.\n"
        "<b>DCA 가중:</b> <code>-dca</code> 옵션을 추가하면 낮은 RSI(더 좋은 매수 타이밍)에 예산을 집중합니다 (<code>-max</code> 동일).\n\n"
        "<b>예시:</b>\n"
        "1. <code>/rsitrade BTC</code>\n"
        "2. <code>/rsitrade 빗썸 BTC</code>\n"
        "3. <code>/rsitrade BTC 20-30 60-75 7 200만</code>\n"
        "4. <code>/rsitrade BTC 20-30 - 5 100만</code>  (매수만)\n"
        "5. <code>/rsitrade -dca 빗썸 BTC 20-30 60-70 5 100만</code>  (DCA 가중)\n"
        "6. <code>/rsitrade 토스증권 005930 20-30 60-75 5 100만</code>  (토스증권 일봉)"
    ),
    "gridrsi": (
        "🤖 <b>/gridrsi 상세 가이드</b>\n\n"
        "<b>기능:</b> RSI 목표 구간으로 분할 매수합니다 (<code>/rsitrade</code>의 alias). 매도RSI 지정 시 체결 후 자동 익절 예약.\n"
        "<b>구문:</b> <code>/gridrsi [거래소] [종목] [매수RSI] [매도RSI] [횟수] [예산]</code>\n\n"
        "<b>예시:</b>\n"
        "1. <code>/gridrsi BTC 25-30 65-75 5 100만</code>\n"
        "2. <code>/gridrsi ETH 20-30 - 5 100만</code>  (매도 없이 매수만)\n"
        "3. <code>/gridrsi 토스증권 005930 25-30 65-75 5 100만</code> (토스증권 삼성전자)"
    ),
    "sgridrsi": (
        "💰 <b>/sgridrsi 상세 가이드</b>\n\n"
        "<b>기능:</b> 보유 코인을 RSI 목표 구간에서 분할 매도합니다. 매수 없이 직접 매도 주문만 생성합니다.\n"
        "<b>구문:</b> <code>/sgridrsi [거래소] [종목] [RSI구간] [횟수] [예산]</code>\n\n"
        "<b>예시:</b>\n"
        "1. <code>/sgridrsi ETH 80-90 10 100만</code>\n"
        "2. <code>/sgridrsi 빗썸 ETH 80-90 10 100만</code>\n"
        "3. <code>/sgridrsi 토스증권 005930 80-90 10 100만</code> (토스증권 삼성전자)"
    ),
    "info": (
        "ℹ️ <b>/info 상세 가이드</b>\n\n"
        "<b>기능:</b> 현재 실행 중인 봇의 버전 및 빌드 정보를 표시합니다.\n"
        "<b>사용법:</b> <code>/info</code>만 입력"
    ),
}


# ── 기본 포맷 유틸 ─────────────────────────────────────────────────────────────

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
    return "\n".join([f"<b>{title}</b>", *body])


def format_rsi_interval(value):
    value = parse_rsi_interval(value)
    if value == "day":
        return "day (일봉)"
    return f"{value}분봉"


def format_config_value(key, value):
    if isinstance(value, bool):
        return format_bool(value)
    if key == "rsi_interval":
        return format_rsi_interval(value)
    if key in ["rsi_budget_krw", "max_order_krw", "max_open_exposure_krw"]:
        return format_optional_krw(value)
    if key == "asset_min_display_krw":
        return f"{float(value):,.0f}원"
    if key in POLL_INTERVAL_KEYS:
        return _format_seconds(value)
    return value


def format_safety_status(user):
    prefs = user.get("preferences", {})
    max_order = prefs.get("max_order_krw")
    kis_env = user.get("exchanges", {}).get("kis", {}).get("env", "paper")
    configured = []
    for exchange in ["upbit", "bithumb", "kis", "toss"]:
        keys = user.get("exchanges", {}).get(exchange, {})
        if exchange == "kis":
            is_set = bool(keys.get("app_key") and keys.get("app_secret") and keys.get("account_no"))
        elif exchange == "toss":
            is_set = bool(keys.get("client_id") and keys.get("client_secret"))
        else:
            is_set = bool(keys.get("access_key") and keys.get("secret_key"))
        if is_set:
            configured.append(exchange_display_name(exchange))
    max_exposure = prefs.get("max_open_exposure_krw")
    return [
        "- 수동 주문: 확인 버튼 필요",
        f"- max_order_krw: {format_optional_krw(max_order)}"
        + (" (권장: /config set max_order_krw 50만)" if max_order is None else ""),
        f"- max_open_exposure_krw: {format_optional_krw(max_exposure)}",
        f"- KIS 환경: {_kis_exchange.env_label({'env': kis_env})}"
        + (" (실전 거래 주의)" if kis_env == "real" else ""),
        f"- API 키 설정 거래소: {', '.join(configured) if configured else '없음'}",
    ]


def format_api_validation_status(user, exchange):
    validation = user.get("api_validation", {}).get(exchange)
    if not validation:
        return "검증 이력 없음"
    status = "마지막 검증 성공" if validation.get("ok") else "마지막 검증 실패"
    checked_at = str(validation.get("checked_at") or "").split("+")[0].replace("T", " ")
    return f"{status} {checked_at}".strip()


def build_secret_security_status(user):
    if not has_secret_key():
        return "없음"
    if not can_decrypt_secrets():
        return "형식 오류"
    if user.get("_secret_error"):
        return "복호화 오류"
    return "정상"


# ── 메시지 빌더 ────────────────────────────────────────────────────────────────

def build_start_menu_message(user, bot_name=BOT_DISPLAY_NAME):
    username = _html.escape(user.get("username", "사용자"))
    return (
        f"🤖 <b>{bot_name} 시스템 접속 완료</b>\n\n"
        f"어서오세요, <b>{username}</b>님.\n\n"
        "<b>💼 자산 조회</b>\n"
        "/asset · /price · /history\n\n"
        "<b>📈 자동 매매</b>\n"
        "/status · /orders · /rsitrade · /grid · /sgrid\n\n"
        "<b>🔔 시그널 감시</b>\n"
        "/watch · /unwatch\n\n"
        "<b>⚙️ 설정 및 도움말</b>\n"
        "/config · /help"
    )


def build_help_message(user, bot_name=BOT_DISPLAY_NAME):
    admin_lines = [
        f"<code>/halt</code> — 글로벌 거래 중지 (관리자 전용)",
        f"<code>/resume</code> — 글로벌 거래 재개 (관리자 전용)",
        f"<code>/resetuser</code> [유저ID] — 유저 주문/실적 완전 초기화 (관리자 전용)",
        f"<code>/nlstats</code> — 자연어 전처리 후보 통계 (관리자 전용)",
        f"<code>/dbsync</code> — 주문 DB 수동 동기화 (관리자 전용)",
    ] if user.get("is_admin") else []

    system_lines = [
        f"<code>/start</code> — 시스템 접속 및 메뉴 확인",
        f"<code>/status</code> — 가동 중인 트레이딩 전략 대시보드",
        f"<code>/config</code> — 거래소, LLM API 설정",
        f"<code>/info</code> — 봇 버전 및 빌드 정보 확인",
        f"<code>/whoami</code> — 내 계정 권한과 상태 확인",
        *admin_lines,
        f"<code>/help</code> — 명령어 도움말 확인",
    ]
    sections = [
        f"📖 <b>{bot_name} 사용 설명서</b>",
        f"상세 가이드: <code>/[명령어] -h</code>  예: <code>/rsitrade -h</code>",
        "",
        format_section("⚙️ 시스템", system_lines),
        "",
        format_section("💼 자산 및 시세 조회", [
            f"<code>/asset</code> — 통합 자산 및 소액 자산 요약 조회",
            f"<code>/price</code> [종목] — 실시간 시세 및 변동률 <i>(/p 단축)</i>",
            f"<code>/history</code> [종목] — 최근 체결 내역 확인 (5건)",
        ]),
        "",
        format_section("📈 자동 거래 및 순환 매매", [
            f"<code>/rsitrade</code> [종목] [매수RSI] [매도RSI] [횟수] [예산] — RSI 분할 매수+자동매도",
            f"<code>/sgridrsi</code> [종목] [RSI구간] [횟수] [예산] — RSI 분할 매도 (보유 코인 직접 매도)",
            f"<code>/grid</code> [종목] [시작가] [종료가] [횟수] [예산] — 가격 분할 매수",
            f"<code>/sgrid</code> [종목] [시작가] [종료가] [횟수] [수량] — 가격 분할 매도",
            f"<code>/buy</code> / <code>/sell</code> [종목] [가격] [수량] — 단일 지정가 주문",
            f"<code>/orders</code> — 미체결 주문 및 추적 목록",
            f"<code>/cancel</code> [종목] — 해당 종목 주문 일괄 취소",
        ]),
        "",
        format_section("🔔 시그널 감시", [
            f"<code>/watch</code> [종목] — RSI 매수 시그널 실시간 감시",
            f"<code>/unwatch</code> [종목] — 감시 목록에서 제거",
        ]),
        "",
        "⚠️ 모든 주문은 거래소 앱과 실시간 동기화됩니다.",
    ]
    return "\n".join(sections)


def build_config_view(user, active_order_count=0):
    preferences = user["preferences"]
    api_lines = []
    for exchange in ["upbit", "bithumb", "kis", "toss"]:
        keys = user.get("exchanges", {}).get(exchange, {})
        status_text = format_api_validation_status(user, exchange)
        status_text = status_text.replace("마지막 검증 ", "").replace("2026-", "")
        if exchange == "kis":
            is_set = bool(keys.get("app_key") and keys.get("app_secret") and keys.get("account_no"))
            account = keys.get("account_no", "")
            masked_account = f"{account[:2]}****{account[-2:]}" if len(account) >= 4 else "미설정"
            env_name = _kis_exchange.env_label(keys)
            api_lines.append(
                f"🏛️ <b>{exchange_display_name(exchange)}</b> ({env_name})\n"
                f"  ├ 계좌: {masked_account} ({'설정됨' if is_set else '미설정'})\n"
                f"  └ 상태: {status_text}\n"
            )
        elif exchange == "toss":
            is_set = bool(keys.get("client_id") and keys.get("client_secret"))
            account_seq = keys.get("account_seq")
            seq_text = str(account_seq) if account_seq is not None else "미조회"
            api_lines.append(
                f"🏛️ <b>{exchange_display_name(exchange)}</b>\n"
                f"  ├ 키: {'설정됨' if is_set else '미설정'} / account_seq: {seq_text}\n"
                f"  └ 상태: {status_text}\n"
            )
        else:
            is_set = bool(keys.get("access_key") and keys.get("secret_key"))
            api_lines.append(
                f"🏛️ <b>{exchange_display_name(exchange)}</b>\n"
                f"  ├ 키: {'설정됨' if is_set else '미설정'}\n"
                f"  └ 상태: {status_text}\n"
            )

    sections = [
        "⚙️ <b>현재 사용자 설정</b>",
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
            f"- max_open_exposure_krw: {format_optional_krw(preferences.get('max_open_exposure_krw'))}",
            "- stop_loss_pct: " + ("없음 (손절 비활성)" if preferences.get('stop_loss_pct') is None else f"{preferences.get('stop_loss_pct'):g}%"),
            f"- signal_bb_alert: {format_bool(preferences.get('signal_bb_alert'))}",
            "- quiet_hours: " + (
                f"{preferences.get('quiet_hours_start')} – {preferences.get('quiet_hours_end')}"
                if preferences.get('quiet_hours_start') and preferences.get('quiet_hours_end')
                else "비활성"
            ),
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
        "",
        format_section("거래 안전 상태", format_safety_status(user)),
    ]
    if user.get("is_admin"):
        active_interval = _format_seconds(preferences.get("poll_active_interval", 60))
        no_order_interval = _format_seconds(preferences.get("poll_no_order_interval", 300))
        signal_interval = _format_seconds(preferences.get("signal_analysis_interval", 300))
        current_interval = active_interval if active_order_count > 0 else no_order_interval
        current_reason = f"활성 오더 {active_order_count}건" if active_order_count > 0 else "오더 없음"
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


def _format_metrics_section(snap: dict) -> list:
    lines = []
    for ex, s in sorted(snap.get("orders", {}).items()):
        rate = f"{s['success_rate']}%" if s["success_rate"] is not None else "n/a"
        lines.append(f"- 주문 [{ex}]: 성공 {s['ok']} / 실패 {s['fail']} (성공률 {rate})")
    for ex, lat in sorted(snap.get("latencies", {}).items()):
        lines.append(f"- 레이턴시 [{ex}]: p50={lat['p50']:.0f}ms / p95={lat['p95']:.0f}ms ({lat['count']}회)")
    import time as _time
    now = _time.time()
    poll_ts = snap.get("poll_last_ok")
    sig_ts = snap.get("signal_last_ok")
    lines.append(f"- 주문 동기화: {f'{int((now-poll_ts)//60)}분 전' if poll_ts else '미측정'}")
    lines.append(f"- 신호 분석: {f'{int((now-sig_ts)//60)}분 전' if sig_ts else '미측정'}")
    return lines or ["- 메트릭 수집 없음"]


def build_diag_view(user, env_info=None, recent_events=None, metrics_snapshot=None):
    if env_info is None:
        env_info = {}
    prefs = user.get("preferences", {})
    active_interval = _format_seconds(prefs.get("poll_active_interval", 60))
    no_order_interval = _format_seconds(prefs.get("poll_no_order_interval", 300))
    order_count = env_info.get("order_count", 0)
    current_interval = active_interval if order_count > 0 else no_order_interval

    exchange_lines = []
    for exchange in ["upbit", "bithumb", "kis", "toss"]:
        keys = user.get("exchanges", {}).get(exchange, {})
        if exchange == "kis":
            is_set = bool(keys.get("app_key") and keys.get("app_secret") and keys.get("account_no"))
            env_name = _kis_exchange.env_label(keys)
            exchange_lines.append(
                f"- {exchange_display_name(exchange)}: {'설정됨' if is_set else '미설정'}"
                f" / {env_name} / {format_api_validation_status(user, exchange)}"
            )
        elif exchange == "toss":
            is_set = bool(keys.get("client_id") and keys.get("client_secret"))
            exchange_lines.append(
                f"- {exchange_display_name(exchange)}: {'설정됨' if is_set else '미설정'}"
                f" / {format_api_validation_status(user, exchange)}"
            )
        else:
            is_set = bool(keys.get("access_key") and keys.get("secret_key"))
            exchange_lines.append(
                f"- {exchange_display_name(exchange)}: {'설정됨' if is_set else '미설정'}"
                f" / {format_api_validation_status(user, exchange)}"
            )

    if recent_events is None:
        recent_events = []
    event_lines = [
        f"- {row.get('ts')} / {row.get('level')} / {row.get('source')}: {row.get('message')}"
        for row in recent_events
    ] or ["- 최근 warning/error 없음"]

    git_sha = env_info.get("git_sha", "unknown")
    return "\n".join([
        "🧪 <b>운영 진단</b>",
        "",
        format_section("환경", [
            f"- TELEGRAM_BOT_TOKEN: {'설정됨' if env_info.get('bot_token_set') else '없음'}",
            f"- ADMIN_CHAT_ID: {'설정됨' if env_info.get('admin_chat_id_set') else '없음'}",
            f"- USER_SECRET_KEY: {build_secret_security_status(user)}",
        ]),
        "",
        format_section("빌드", [
            f"- 버전: {env_info.get('version', 'unknown')}",
            f"- 빌드: {env_info.get('build_date', 'unknown')}",
            f"- 커밋: {git_sha}",
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
            f"- 활성 주문: {order_count}건",
            f"- 현재 주기: {current_interval}",
            f"- poll_active_interval: {active_interval}",
            f"- poll_no_order_interval: {no_order_interval}",
            f"- signal_analysis_interval: {_format_seconds(prefs.get('signal_analysis_interval', 300))}",
        ]),
        "",
        format_section("거래 안전 상태", format_safety_status(user)),
        "",
        format_section("최근 오류", event_lines),
        "",
        format_section("메트릭", _format_metrics_section(metrics_snapshot or {})),
    ])


def build_account_summary(user_id, user):
    prefs = user.get("preferences", {})
    role = "관리자" if user.get("is_admin") else "일반 사용자"
    active = "활성" if user.get("is_active") else "승인 대기"
    llm = "on" if prefs.get("llm_enabled") else "off"
    default_exchange = prefs.get("default_exchange", "upbit")
    secret_status = "\n보안 키: 복호화 오류" if user.get("_secret_error") else ""
    return (
        "👤 <b>내 계정</b>\n\n"
        f"ID: {_html.escape(str(user_id))}\n"
        f"권한: {role}\n"
        f"상태: {active}\n"
        f"기본 거래소: {default_exchange}\n"
        f"자연어: {llm}"
        f"{secret_status}"
    )


def build_manual_order_confirm_message(exchange, ticker, side, price, volume, user, ord_type="limit"):
    action = "매수" if side == "bid" else "매도"
    is_market = ord_type == "market"
    is_us = is_us_stock_ticker(exchange, ticker)
    env_notice = ""
    if exchange == "kis" or (exchange == "toss" and not is_us):
        if exchange == "kis":
            env_notice = f" ({_kis_exchange.env_label(user.get('exchanges', {}).get('kis', {}))})"
        volume_text = f"{float(volume):,.0f}주"
    elif is_us:
        volume_text = f"{float(volume):,.0f}주"
    else:
        volume_text = f"{float(volume):.8f}".rstrip("0").rstrip(".")
    if is_us:
        price_text = "시장가" if is_market else f"${float(price):,.2f}"
        amount_line = "" if is_market else f"- 주문금액: ${float(price) * float(volume):,.2f}\n"
    else:
        price_text = "시장가" if is_market else f"{float(price):,.0f}원"
        amount_line = "" if is_market else f"- 주문금액: {float(price) * float(volume):,.0f}원\n"
    return (
        f"{'📈' if side == 'bid' else '📉'} <b>{exchange_display_name(exchange)} {action} 주문 확인</b>{env_notice}\n\n"
        f"- 종목: {ticker}\n"
        f"- 가격: {price_text}\n"
        f"- 수량: {volume_text}\n"
        f"{amount_line}\n"
        "위 내용으로 주문을 전송할까요?"
    )


_ORDER_STATUS_NAMES = {"wait": "대기", "partial": "부분체결", "pending_reorder": "재주문대기", "market_closed": "장외대기", "reserved": "예약"}


def build_cancel_confirm_message(orders, title):
    lines = [f"🛑 <b>{title} 주문 취소 확인</b>\n", f"다음 {len(orders)}건의 주문을 취소할까요?\n"]
    for ord in orders:
        side_str = "매수" if ord["side"] == "bid" else "매도"
        status_str = _ORDER_STATUS_NAMES.get(ord.get("status"), "")
        status_tag = f" — {status_str}" if status_str else ""
        group_tag = f" [#{ord['group_no']}]" if ord.get("group_no") else ""
        lines.append(f"📌 [{exchange_display_name(ord['exchange'])}] {kr_stock_display(ord['exchange'], ord['ticker'])}{group_tag}")
        if is_us_stock_ticker(ord['exchange'], ord['ticker']):
            lines.append(f"   └ ${ord['price']:,.2f} ({side_str}, {ord['volume']:.0f}주){status_tag}")
        else:
            lines.append(f"   └ {ord['price']:,.0f}원 ({side_str}, {ord['volume']:.4f}개){status_tag}")
    return "\n".join(lines)


def build_grid_preview_lines(ticker, start_price, end_price, count, budget, is_usd=False):
    per_order_budget = float(budget) / int(count)
    lines = []
    for i in range(int(count)):
        price = float(interpolate_range(float(start_price), float(end_price), i, int(count)))
        volume = per_order_budget / price
        if is_usd:
            lines.append(f"{i + 1}. ${price:,.2f} / 약 {int(volume)}주 / ${per_order_budget:,.2f}")
        else:
            lines.append(
                f"{i + 1}. {price:,.0f}원 / 약 {_format_preview_volume(ticker, volume)} / {per_order_budget:,.0f}원"
            )
    return lines


def build_rsi_preview_lines(ticker, rsi_prices, budget, total_count=None, per_order_budgets=None, is_usd=False):
    if not rsi_prices:
        return []
    default_per_order = float(budget) / int(total_count or len(rsi_prices))
    lines = []
    for i, (target_rsi, price) in enumerate(rsi_prices, start=1):
        price = float(price)
        order_budget = float(per_order_budgets[i - 1]) if per_order_budgets else default_per_order
        volume = order_budget / price
        if is_usd:
            lines.append(f"{i}. RSI {float(target_rsi):g} → ${price:,.2f} / 약 {int(volume)}주 / ${order_budget:,.2f}")
        else:
            lines.append(
                f"{i}. RSI {float(target_rsi):g} → {price:,.0f}원 / 약 {_format_preview_volume(ticker, volume)} / {order_budget:,.0f}원"
            )
    return lines


def build_report_view(trades: list, period: str = "all") -> str:
    """체결 기록 기반 수익률 리포트 메시지 생성."""
    period_label = {"today": "오늘", "week": "최근 7일", "month": "최근 30일"}.get(period, "전체")

    by_key: dict = defaultdict(lambda: {"bid_krw": 0.0, "ask_krw": 0.0, "bid_count": 0, "ask_count": 0})
    for t in trades:
        key = (t.get("exchange", ""), t.get("ticker", ""))
        val = float(t.get("price", 0)) * float(t.get("volume", 0))
        side = t.get("side", "bid")
        by_key[key][f"{side}_krw"] += val
        by_key[key][f"{side}_count"] += 1

    # USD(토스 해외주식)와 KRW는 통화가 달라 합산할 수 없으므로 합계를 분리한다.
    total_bid_krw = sum(v["bid_krw"] for k, v in by_key.items() if not is_us_stock_ticker(k[0], k[1]))
    total_ask_krw = sum(v["ask_krw"] for k, v in by_key.items() if not is_us_stock_ticker(k[0], k[1]))
    total_bid_usd = sum(v["bid_krw"] for k, v in by_key.items() if is_us_stock_ticker(k[0], k[1]))
    total_ask_usd = sum(v["ask_krw"] for k, v in by_key.items() if is_us_stock_ticker(k[0], k[1]))
    net_krw = total_ask_krw - total_bid_krw
    net_usd = total_ask_usd - total_bid_usd

    lines = [f"📊 <b>수익률 리포트 ({period_label})</b>", ""]
    for (exchange, ticker), stats in sorted(by_key.items()):
        pnl = stats["ask_krw"] - stats["bid_krw"]
        sign = "+" if pnl >= 0 else ""
        ex_label = exchange_display_name(exchange) if exchange else exchange.upper()
        is_usd = is_us_stock_ticker(exchange, ticker)
        unit = "$" if is_usd else ""
        suffix = "" if is_usd else "원"
        lines.append(f"<b>[{ex_label}] {kr_stock_display(exchange, ticker)}</b>")
        if stats["bid_count"]:
            lines.append(f"  매수 {stats['bid_count']}건 / {unit}{stats['bid_krw']:,.2f}{suffix}" if is_usd else f"  매수 {stats['bid_count']}건 / {stats['bid_krw']:,.0f}원")
        if stats["ask_count"]:
            lines.append(f"  매도 {stats['ask_count']}건 / {unit}{stats['ask_krw']:,.2f}{suffix}" if is_usd else f"  매도 {stats['ask_count']}건 / {stats['ask_krw']:,.0f}원")
        if stats["bid_count"] and stats["ask_count"]:
            lines.append(f"  손익(추정): {sign}{unit}{pnl:,.2f}{suffix}" if is_usd else f"  손익(추정): {sign}{pnl:,.0f}원")
        lines.append("")

    net_sign_krw = "+" if net_krw >= 0 else ""
    lines.append(f"💰 합계(KRW): 매수 {total_bid_krw:,.0f}원 / 매도 {total_ask_krw:,.0f}원")
    lines.append(f"📈 총 손익(추정, KRW): {net_sign_krw}{net_krw:,.0f}원")
    if total_bid_usd or total_ask_usd:
        net_sign_usd = "+" if net_usd >= 0 else ""
        lines.append(f"💰 합계(USD, 토스 해외주식): 매수 ${total_bid_usd:,.2f} / 매도 ${total_ask_usd:,.2f}")
        lines.append(f"📈 총 손익(추정, USD): {net_sign_usd}${net_usd:,.2f}")
    lines.append("")
    lines.append("⚠️ 손익은 가격×수량 기준 추정치입니다. 수수료 미반영.")
    lines.append("")
    lines.append("📊 더 상세한 내역과 리포트는 [웹 대시보드]에서 확인하실 수 있습니다.")
    return "\n".join(lines)
