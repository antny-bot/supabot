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
    "status": (
        "📊 <b>/status 상세 가이드</b>\n\n"
        "<b>기능:</b> 가동 중인 거미줄/RSI 전략 주문을 거래소·종목·배치별로 묶어 진행 상황을 보여주는 통합 대시보드입니다.\n"
        "<b>구문:</b> <code>/status</code>\n\n"
        "<b>안내:</b>\n"
        "거래소 실제 미체결 주문 원장은 <code>/orders</code>에서 확인하세요.\n"
        "🔘 그룹당 상위 3건만 기본 표시되며, 생략된 항목이 있으면 인라인 버튼으로 전체를 펼쳐볼 수 있습니다."
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
        "⚠️ 설정한 최소 표시 금액 이하의 소액 자산은 '기타'로 합산 표시됩니다.\n"
        "🔘 거래소별 상위 5개 종목만 기본 표시되며, '기타' 종목이 있으면 인라인 버튼으로 거래소별로 펼쳐볼 수 있습니다."
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
        "4. <code>/history 토스증권 005930</code> (토스증권 삼성전자 내역)\n\n"
        "🔘 5건씩 표시되며, ◀️ 이전 / ▶️ 다음 버튼으로 나머지 내역을 더 볼 수 있습니다."
    ),
    "report": (
        "📊 <b>/report 상세 가이드</b>\n\n"
        "<b>기능:</b> 기간별 실현 손익과 종목별 매수/매도 체결을 요약한 리포트를 보여줍니다.\n"
        "<b>구문:</b> <code>/report [today|week|month|all]</code>\n\n"
        "<b>옵션:</b>\n"
        "• 기간 생략 시 <code>all</code>(전체) 기준\n\n"
        "<b>안내:</b>\n"
        "⚠️ 손익은 가격×수량 기준 추정치이며 수수료는 반영되지 않습니다.\n"
        "🔘 종목 10개씩 표시되며, ◀️ 이전 / ▶️ 다음 버튼으로 더 볼 수 있습니다. 합계는 페이지와 무관하게 항상 전체 거래 기준으로 표시됩니다."
    ),
    "buy": (
        "🛍️ <b>/buy 상세 가이드 (단일 매수)</b>\n\n"
        "<b>기능:</b> 지정한 거래소에 단일 매수 주문을 즉시 전송합니다.\n"
        "<b>구문:</b> <code>/buy [거래소] [종목] [가격|market] [수량] [유지]</code>\n\n"
        "<b>예시:</b>\n"
        "<code>/buy 빗썸 BTC 95000000 0.1</code> (빗썸에서 0.1 BTC를 9500만원에 매수)\n"
        "<code>/buy 한투 005930 70000 1</code> (한국투자증권에서 삼성전자 1주 매수 확인)\n"
        "<code>/buy 토스증권 005930 70000 1</code> (토스증권에서 삼성전자 1주 매수 확인)\n"
        "<code>/buy 토스증권 AAPL 185.5 10</code> (토스증권 해외주식 애플 10주 매수, USD)\n"
        "<code>/buy 토스증권 005930 70000 10 유지</code> (장마감으로 미체결 취소 시 다음 정규장에 자동 재주문)\n\n"
        "🌎 토스증권은 AAPL, TSLA 등 해외(미국)주식 티커 입력 시 USD로 자동 처리됩니다 (한투는 국내전용).\n"
        "🔁 끝에 <code>유지</code>(또는 <code>--keep</code>)를 붙이면 한투·토스 주문이 장마감으로 취소돼도 다음 정규장에 잔량을 자동 재주문합니다(기본값: 끔).\n"
        "⚠️ 한국투자증권·토스증권 주문은 확인 버튼을 거친 뒤 전송됩니다."
    ),
    "sell": (
        "🛍️ <b>/sell 상세 가이드 (단일 매도)</b>\n\n"
        "<b>기능:</b> 지정한 거래소에 단일 매도 주문을 즉시 전송합니다.\n"
        "<b>구문:</b> <code>/sell [거래소] [종목] [가격|market] [수량] [유지]</code>\n\n"
        "<b>예시:</b>\n"
        "<code>/sell BTC 120000000 0.5</code> (업비트에서 0.5 BTC를 1.2억원에 매도)\n"
        "<code>/sell 토스증권 005930 72000 1</code> (토스증권에서 삼성전자 1주 매도)\n"
        "<code>/sell 토스증권 AAPL 190 10</code> (토스증권 해외주식 애플 10주 매도, USD)\n"
        "<code>/sell 토스증권 005930 72000 1 유지</code> (장마감으로 미체결 취소 시 다음 정규장에 자동 재주문)\n\n"
        "🔁 끝에 <code>유지</code>(또는 <code>--keep</code>)를 붙이면 한투·토스 주문이 장마감으로 취소돼도 다음 정규장에 잔량을 자동 재주문합니다(기본값: 끔).\n"
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
        "봇을 통해 생성한 주문뿐만 아니라 직접 거래소에서 건 미체결 주문도 모두 조회됩니다.\n"
        "🔘 거미줄/RSI 같은 배치(batch) 주문은 기본적으로 그룹 단위 요약(건수/상태)으로 표시되며, 인라인 버튼으로 그룹을 풀어 개별 주문을 모두 펼쳐볼 수 있습니다."
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
            f"<code>/history</code> [종목] — 최근 체결 내역 확인 (5건씩 페이지네이션)",
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


def build_manual_order_confirm_message(exchange, ticker, side, price, volume, user, ord_type="limit", auto_reorder=False):
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
    reorder_line = "🔁 장마감 시 자동 재주문: 켜짐 (다음 정규장에 잔량 재제출)\n" if auto_reorder else ""
    return (
        f"{'📈' if side == 'bid' else '📉'} <b>{exchange_display_name(exchange)} {action} 주문 확인</b>{env_notice}\n\n"
        f"- 종목: {ticker}\n"
        f"- 가격: {price_text}\n"
        f"- 수량: {volume_text}\n"
        f"{amount_line}"
        f"{reorder_line}\n"
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


REPORT_PAGE_SIZE = 10  # /report 페이지네이션 — 페이지당 종목 그룹 수


def aggregate_trades(trades: list):
    """체결 기록을 (exchange,ticker)별로 집계하고 통화별 합계를 계산한다.

    반환: (by_key, totals) — by_key는 정렬 전 dict, totals는 KRW/USD 합산치.
    /report 페이지네이션에서 재집계 없이 페이지만 다시 그릴 때 재사용한다.
    """
    by_key: dict = defaultdict(lambda: {"bid_krw": 0.0, "ask_krw": 0.0, "bid_count": 0, "ask_count": 0})
    for t in trades:
        key = (t.get("exchange", ""), t.get("ticker", ""))
        val = float(t.get("price", 0)) * float(t.get("volume", 0))
        side = t.get("side", "bid")
        by_key[key][f"{side}_krw"] += val
        by_key[key][f"{side}_count"] += 1

    # USD(토스 해외주식)와 KRW는 통화가 달라 합산할 수 없으므로 합계를 분리한다.
    totals = {
        "bid_krw": sum(v["bid_krw"] for k, v in by_key.items() if not is_us_stock_ticker(k[0], k[1])),
        "ask_krw": sum(v["ask_krw"] for k, v in by_key.items() if not is_us_stock_ticker(k[0], k[1])),
        "bid_usd": sum(v["bid_krw"] for k, v in by_key.items() if is_us_stock_ticker(k[0], k[1])),
        "ask_usd": sum(v["ask_krw"] for k, v in by_key.items() if is_us_stock_ticker(k[0], k[1])),
    }
    return by_key, totals


def render_report_ticker_lines(by_key_items) -> list:
    """종목별(거래소,티커) 매수/매도/손익 라인을 만든다. 페이지 슬라이스에 적용 가능."""
    lines = []
    for (exchange, ticker), stats in by_key_items:
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
    return lines


def render_report_totals_lines(totals: dict) -> list:
    """전체 거래 기준 합계 라인 — 페이지와 무관하게 항상 동일하게 표시."""
    net_krw = totals["ask_krw"] - totals["bid_krw"]
    net_usd = totals["ask_usd"] - totals["bid_usd"]
    net_sign_krw = "+" if net_krw >= 0 else ""
    lines = [
        f"💰 합계(KRW): 매수 {totals['bid_krw']:,.0f}원 / 매도 {totals['ask_krw']:,.0f}원",
        f"📈 총 손익(추정, KRW): {net_sign_krw}{net_krw:,.0f}원",
    ]
    if totals["bid_usd"] or totals["ask_usd"]:
        net_sign_usd = "+" if net_usd >= 0 else ""
        lines.append(f"💰 합계(USD, 토스 해외주식): 매수 ${totals['bid_usd']:,.2f} / 매도 ${totals['ask_usd']:,.2f}")
        lines.append(f"📈 총 손익(추정, USD): {net_sign_usd}${net_usd:,.2f}")
    return lines


def build_report_view(trades: list, period: str = "all") -> str:
    """체결 기록 기반 수익률 리포트 메시지 생성 (전체, 페이지네이션 없음)."""
    period_label = {"today": "오늘", "week": "최근 7일", "month": "최근 30일"}.get(period, "전체")
    by_key, totals = aggregate_trades(trades)

    lines = [f"📊 <b>수익률 리포트 ({period_label})</b>", ""]
    lines.extend(render_report_ticker_lines(sorted(by_key.items())))
    lines.extend(render_report_totals_lines(totals))
    lines.append("")
    lines.append("⚠️ 손익은 가격×수량 기준 추정치입니다. 수수료 미반영.")
    lines.append("")
    lines.append("📊 더 상세한 내역과 리포트는 [웹 대시보드]에서 확인하실 수 있습니다.")
    return "\n".join(lines)


def build_report_view_page(trades: list, period: str = "all", page: int = 0, page_size: int = REPORT_PAGE_SIZE):
    """/report 페이지네이션용 — 종목 그룹을 page_size개씩 잘라 보여주고 합계는 항상 전체 기준.

    반환: (text, page, total_pages)
    """
    period_label = {"today": "오늘", "week": "최근 7일", "month": "최근 30일"}.get(period, "전체")
    by_key, totals = aggregate_trades(trades)
    items = sorted(by_key.items())
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    page_items = items[page * page_size: (page + 1) * page_size]

    lines = [f"📊 <b>수익률 리포트 ({period_label})</b>"]
    if total_pages > 1:
        lines.append(f"📄 {page + 1}/{total_pages} 페이지 (종목 {len(items)}개 중 {page * page_size + 1}-{page * page_size + len(page_items)}번째)")
    lines.append("")
    lines.extend(render_report_ticker_lines(page_items))
    lines.extend(render_report_totals_lines(totals))
    lines.append("")
    lines.append("⚠️ 손익은 가격×수량 기준 추정치입니다. 수수료 미반영.")
    lines.append("")
    lines.append("📊 더 상세한 내역과 리포트는 [웹 대시보드]에서 확인하실 수 있습니다.")
    return "\n".join(lines), page, total_pages



# ── 배치(#N) 및 시계열(Time-Series) 리포트 확장 ────────────────────────────────

_STRATEGY_LABELS = {
    "dca": "정기매매(DCA)",
    "grid": "거미줄매수",
    "sgrid": "거미줄매도",
    "rsitrade": "RSI순환매수",
    "rsitrade_sell": "RSI익절매도",
    "sgridrsi": "RSI분할매도",
    "stoploss": "손절매도",
    "manual": "수동주문",
}

CMD_HELP["dca"] = (
    "📅 <b>/dca, /sdca 상세 가이드 (정기 적립식 매수/매도)</b>\n\n"
    "<b>기능:</b> 단일 종목을 지정해 매일, 특정 요일(월수금 등), 매주 1회, 매월 1회 자동으로 매수 또는 매도합니다.\n"
    "등록된 정기 전략은 고유 <b>배치 번호(#N)</b>로 묶여 <code>/status</code>, <code>/dca</code>, <code>/report #N</code>에서 시계열로 추적됩니다.\n\n"
    "<b>구문:</b>\n"
    "• <code>/dca [매수|매도] [거래소] [종목] [주기] [금액|수량] [시각(선택)] [횟수(선택)]</code>\n"
    "• <code>/sdca [거래소] [종목] [주기] [금액|수량] [시각(선택)] [횟수(선택)]</code> (정기 매도 전용)\n"
    "• <code>/dca</code> 또는 <code>/dca list</code> — 활성 정기 전략 목록 및 계좌 예수금 상태 조회\n"
    "• <code>/dca stop [배치번호|ID]</code> — 특정 정기 전략 중지\n"
    "• <code>/dca clear</code> — 모든 정기 전략 일괄 중지\n\n"
    "<b>주기 표기법:</b>\n"
    "• 매일: <code>매일</code>, <code>daily</code>\n"
    "• 매주 1회: <code>매주월</code>, <code>매주금</code>, <code>매주</code>(기본 월요일)\n"
    "• 특정 요일: <code>월수금</code>, <code>화목</code>, <code>평일</code>, <code>주말</code>\n"
    "• 매월 1회: <code>매월15일</code>, <code>매월1일</code>, <code>매월</code>(기본 1일)\n\n"
    "<b>예시:</b>\n"
    "1. <code>/dca BTC 매일 5만</code> (업비트 비트코인 매일 09:05 5만원 매수)\n"
    "2. <code>/dca 한투 005930 매주월 1주 09:10</code> (한국투자증권 삼성전자 매주 월요일 09:10 1주 매수)\n"
    "3. <code>/dca ETH 월수금 3만 10:00 20회</code> (월·수·금 10:00 3만원 매수, 총 20회 후 종료)\n"
    "4. <code>/sdca BTC 매월25일 0.01개</code> (매월 25일 비트코인 0.01개 정기 매도)"
)
CMD_HELP["sdca"] = CMD_HELP["dca"]

CMD_HELP["report"] = (
    "📊 <b>/report 상세 가이드 (수익률 & 배치·종목 시계열 리포트)</b>\n\n"
    "<b>기능:</b> 기간별 실현 손익 요약뿐만 아니라, 특정 <b>배치(#N)</b> 또는 <b>종목</b>이 시간에 따라 어떻게 매수·매도되었는지 시계열(Time-Series)로 추적하고 계좌 예수금 가용 상태를 함께 점검합니다.\n\n"
    "<b>구문:</b>\n"
    "• <code>/report [today|week|month|all]</code> — 기간별 전체 종목·배치 요약 리포트\n"
    "• <code>/report #[배치번호] [기간]</code> — 해당 배치의 시계열 매수/매도 체결 내역 및 누적 평단·손익 추적\n"
    "• <code>/report [종목] [기간]</code> — 특정 종목의 시계열 매수/매도 체결 내역 조회\n"
    "• <code>/report #[배치번호] [종목]</code> — 배치 + 종목 동시 필터링 시계열 조회\n\n"
    "<b>예시:</b>\n"
    "1. <code>/report</code> (전체 요약 + 배치 목록 + 예수금 점검)\n"
    "2. <code>/report week</code> (최근 7일 리포트)\n"
    "3. <code>/report #1</code> (#1 배치 전략의 시계열 매수·매도 흐름 조회)\n"
    "4. <code>/report BTC</code> (비트코인 시계열 매수·매도 내역 조회)\n"
    "5. <code>/report 005930 month</code> (삼성전자 최근 30일 시계열 내역 조회)"
)


def aggregate_trades_by_batch(trades: list) -> list[tuple[int, dict]]:
    """group_no가 있는 체결 내역을 배치 번호별로 집계한다."""
    by_batch: dict[int, dict] = {}
    for t in trades:
        gno = t.get("group_no")
        if gno is None:
            continue
        try:
            gno_int = int(gno)
        except (TypeError, ValueError):
            continue
        entry = by_batch.setdefault(gno_int, {
            "group_no": gno_int,
            "exchange": t.get("exchange", ""),
            "tickers": set(),
            "strategies": set(),
            "bid_amt": 0.0,
            "ask_amt": 0.0,
            "bid_vol": 0.0,
            "ask_vol": 0.0,
            "bid_count": 0,
            "ask_count": 0,
            "first_ts": str(t.get("ts") or ""),
            "last_ts": str(t.get("ts") or ""),
        })
        tk = t.get("ticker", "")
        if tk:
            entry["tickers"].add(tk)
        st = t.get("strategy", "")
        if st:
            entry["strategies"].add(st)
        price = float(t.get("price", 0) or 0)
        vol = float(t.get("volume", 0) or 0)
        amt = price * vol
        if t.get("side") == "ask":
            entry["ask_amt"] += amt
            entry["ask_vol"] += vol
            entry["ask_count"] += 1
        else:
            entry["bid_amt"] += amt
            entry["bid_vol"] += vol
            entry["bid_count"] += 1
        ts_str = str(t.get("ts") or "")
        if ts_str:
            if not entry["first_ts"] or ts_str < entry["first_ts"]:
                entry["first_ts"] = ts_str
            if not entry["last_ts"] or ts_str > entry["last_ts"]:
                entry["last_ts"] = ts_str

    return sorted(by_batch.items(), key=lambda x: x[0])


def render_batch_summary_lines(trades: list, max_batches: int = 8) -> list[str]:
    """전체 리포트 내에 배치(#N)별 요약 라인을 생성한다."""
    batch_items = aggregate_trades_by_batch(trades)
    if not batch_items:
        return []
    lines = ["📦 <b>배치(#N)별 전략 체결 요약</b>"]
    shown = batch_items[-max_batches:]
    for gno, info in shown:
        ex = info["exchange"]
        ex_label = exchange_display_name(ex) if ex else ""
        tks = sorted(info["tickers"])
        tk_label = kr_stock_display(ex, tks[0]) if tks else "-"
        if len(tks) > 1:
            tk_label += f" 외 {len(tks) - 1}"
        is_usd = is_us_stock_ticker(ex, tks[0]) if tks else False
        strats = sorted(_STRATEGY_LABELS.get(s, s) for s in info["strategies"] if s)
        strat_str = "/".join(strats) if strats else "전략"
        if is_usd:
            b_str = f"매수 {info['bid_count']}건(${info['bid_amt']:,.2f})"
            a_str = f"매도 {info['ask_count']}건(${info['ask_amt']:,.2f})"
        else:
            b_str = f"매수 {info['bid_count']}건({info['bid_amt']:,.0f}원)"
            a_str = f"매도 {info['ask_count']}건({info['ask_amt']:,.0f}원)"
        lines.append(f"• <b>#{gno}</b> [{ex_label}] {tk_label} ({strat_str}): {b_str} · {a_str}")
    if len(batch_items) > max_batches:
        lines.append(f"  └ 외 {len(batch_items) - max_batches}개 배치 생략")
    lines.append("💡 시계열 상세 조회: <code>/report #[배치번호]</code> 또는 <code>/report [종목]</code>")
    return lines


def compute_timeseries_events(trades: list) -> tuple[list[dict], dict]:
    """체결 내역을 시간순(오름차순)으로 정렬하고 각 시점의 누적 보유수량, 평균매수가,
    건별 실현손익, 누적 실현손익을 계산해 반환한다.
    """
    sorted_trades = sorted(trades, key=lambda t: str(t.get("ts") or ""))
    # 종목별 포지션 상태 추적
    pos_by_key: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "holding_vol": 0.0,
        "avg_buy_price": 0.0,
        "cum_realized_pnl": 0.0,
    })

    events = []
    total_bid_krw = 0.0
    total_ask_krw = 0.0
    total_bid_usd = 0.0
    total_ask_usd = 0.0
    total_bid_count = 0
    total_ask_count = 0
    total_realized_pnl_krw = 0.0
    total_realized_pnl_usd = 0.0

    for idx, t in enumerate(sorted_trades, start=1):
        ex = t.get("exchange", "")
        tk = t.get("ticker", "")
        side = t.get("side", "bid")
        price = float(t.get("price", 0) or 0)
        vol = float(t.get("volume", 0) or 0)
        amt = price * vol
        is_usd = is_us_stock_ticker(ex, tk)
        pos = pos_by_key[(ex, tk)]

        trade_pnl = None
        if side == "bid":
            prev_cost = pos["holding_vol"] * pos["avg_buy_price"]
            new_vol = pos["holding_vol"] + vol
            pos["avg_buy_price"] = (prev_cost + amt) / new_vol if new_vol > 0 else price
            pos["holding_vol"] = new_vol
            total_bid_count += 1
            if is_usd:
                total_bid_usd += amt
            else:
                total_bid_krw += amt
        else:
            if pos["avg_buy_price"] > 0:
                trade_pnl = (price - pos["avg_buy_price"]) * vol
            else:
                trade_pnl = 0.0
            pos["cum_realized_pnl"] += trade_pnl
            pos["holding_vol"] = max(0.0, pos["holding_vol"] - vol)
            if pos["holding_vol"] <= 1e-12:
                pos["holding_vol"] = 0.0
            total_ask_count += 1
            if is_usd:
                total_ask_usd += amt
                total_realized_pnl_usd += trade_pnl
            else:
                total_ask_krw += amt
                total_realized_pnl_krw += trade_pnl

        events.append({
            "seq": idx,
            "ts": str(t.get("ts") or ""),
            "exchange": ex,
            "ticker": tk,
            "side": side,
            "price": price,
            "volume": vol,
            "amount": amt,
            "strategy": t.get("strategy", "manual"),
            "group_no": t.get("group_no"),
            "holding_vol": pos["holding_vol"],
            "avg_buy_price": pos["avg_buy_price"],
            "trade_pnl": trade_pnl,
            "cum_realized_pnl": pos["cum_realized_pnl"],
            "is_usd": is_usd,
        })

    summary = {
        "total_events": len(events),
        "bid_count": total_bid_count,
        "ask_count": total_ask_count,
        "bid_krw": total_bid_krw,
        "ask_krw": total_ask_krw,
        "bid_usd": total_bid_usd,
        "ask_usd": total_ask_usd,
        "realized_pnl_krw": total_realized_pnl_krw,
        "realized_pnl_usd": total_realized_pnl_usd,
        "net_cashflow_krw": total_ask_krw - total_bid_krw,
        "net_cashflow_usd": total_ask_usd - total_bid_usd,
    }
    return events, summary


def build_timeseries_report_view_page(
    trades: list,
    period: str = "all",
    group_no: int | None = None,
    ticker: str | None = None,
    page: int = 0,
    page_size: int = REPORT_PAGE_SIZE,
    dca_sched: dict | None = None,
    open_orders: list | None = None,
    cash_reports: list[dict] | None = None,
) -> tuple[str, int, int]:
    """배치(#N) 또는 종목(ticker) 필터링 시 매수·매도 체결 내역을 시계열(Time-Series)로 렌더링한다."""
    from core.dca_manager import format_dca_schedule, format_cash_health_section

    period_label = {"today": "오늘", "week": "최근 7일", "month": "최근 30일"}.get(period, "전체")
    filter_parts = []
    if group_no is not None:
        filter_parts.append(f"배치 #{group_no}")
    if ticker:
        filter_parts.append(f"종목 {ticker}")
    filter_title = " · ".join(filter_parts) if filter_parts else "전체"

    events, summary = compute_timeseries_events(trades)
    total_pages = max(1, (len(events) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    page_events = events[page * page_size: (page + 1) * page_size]

    lines = [f"📈 <b>시계열 매매 리포트 ({filter_title} | {period_label})</b>"]
    if total_pages > 1:
        lines.append(
            f"📄 {page + 1}/{total_pages} 페이지 (총 {len(events)}건 중 {page * page_size + 1}-{page * page_size + len(page_events)}번째)"
        )

    if dca_sched:
        side_str = "매수" if dca_sched.get("side") == "bid" else "매도"
        sched_str = format_dca_schedule(dca_sched)
        run_cnt = int(dca_sched.get("run_count") or 0)
        max_runs = dca_sched.get("max_runs")
        run_str = f"{run_cnt}/{max_runs}회" if max_runs else f"누적 {run_cnt}회"
        lines.append(
            f"🔄 <b>활성 정기전략:</b> [{exchange_display_name(dca_sched['exchange'])}] {dca_sched['ticker']} "
            f"정기 {side_str} ({sched_str}, {run_str})"
        )

    if open_orders:
        lines.append(f"⏳ <b>현재 미체결/대기 주문:</b> {len(open_orders)}건")

    lines.append("")
    if not page_events:
        lines.append("ℹ️ 아직 체결 완료된 내역이 없습니다.")
    else:
        lines.append("🕒 <b>시간순 체결 타임라인</b>")
        for ev in page_events:
            ts_short = ev["ts"][:16].replace("T", " ") if ev["ts"] else "-"
            side_badge = "🔴 매수" if ev["side"] == "bid" else "🔵 매도"
            ex_label = exchange_display_name(ev["exchange"]) if ev["exchange"] else ""
            tk_disp = kr_stock_display(ev["exchange"], ev["ticker"])
            g_tag = f" [<b>#{ev['group_no']}</b>]" if ev.get("group_no") else ""
            st_label = _STRATEGY_LABELS.get(ev["strategy"], ev["strategy"])
            is_usd = ev["is_usd"]
            is_stock = ev["exchange"] in ("kis", "toss")
            vol_str = f"{ev['volume']:,.0f}주" if is_stock else f"{ev['volume']:.4f}개"
            hold_str = f"{ev['holding_vol']:,.0f}주" if is_stock else f"{ev['holding_vol']:.4f}개"

            lines.append(
                f"<b>{ev['seq']}.</b> <code>{ts_short}</code> | {side_badge} | [{ex_label}] {tk_disp}{g_tag} ({st_label})"
            )
            if is_usd:
                price_str = f"${ev['price']:,.2f}"
                amt_str = f"${ev['amount']:,.2f}"
                avg_str = f"${ev['avg_buy_price']:,.2f}"
            else:
                price_str = f"{ev['price']:,.0f}원"
                amt_str = f"{ev['amount']:,.0f}원"
                avg_str = f"{ev['avg_buy_price']:,.0f}원"

            if ev["side"] == "bid":
                lines.append(
                    f"   └ {price_str} × {vol_str} = <b>{amt_str}</b> (보유 {hold_str} · 평단 {avg_str})"
                )
            else:
                pnl_val = ev["trade_pnl"] or 0.0
                sign = "+" if pnl_val >= 0 else ""
                pnl_str = f"{sign}${pnl_val:,.2f}" if is_usd else f"{sign}{pnl_val:,.0f}원"
                lines.append(
                    f"   └ {price_str} × {vol_str} = <b>{amt_str}</b> (실현손익 {pnl_str} · 잔여 {hold_str})"
                )

    lines.append("")
    lines.append("📊 <b>시계열 누적 요약</b>")
    if summary["bid_krw"] or summary["ask_krw"] or not (summary["bid_usd"] or summary["ask_usd"]):
        rpnl = summary["realized_pnl_krw"]
        rsign = "+" if rpnl >= 0 else ""
        cf = summary["net_cashflow_krw"]
        cfsign = "+" if cf >= 0 else ""
        lines.append(
            f"• 매수 {summary['bid_count']}건 ({summary['bid_krw']:,.0f}원) / "
            f"매도 {summary['ask_count']}건 ({summary['ask_krw']:,.0f}원)"
        )
        lines.append(
            f"• 누적 실현손익(평단기준): <b>{rsign}{rpnl:,.0f}원</b> (현금흐름 {cfsign}{cf:,.0f}원)"
        )
    if summary["bid_usd"] or summary["ask_usd"]:
        rpnl_u = summary["realized_pnl_usd"]
        rsign_u = "+" if rpnl_u >= 0 else ""
        lines.append(
            f"• 매수(USD) {summary['bid_count']}건 (${summary['bid_usd']:,.2f}) / "
            f"매도(USD) {summary['ask_count']}건 (${summary['ask_usd']:,.2f})"
        )
        lines.append(f"• 누적 실현손익(USD): <b>{rsign_u}${rpnl_u:,.2f}</b>")

    if cash_reports:
        lines.append("")
        lines.append(format_cash_health_section(cash_reports, html=True))

    lines.append("")
    lines.append("⚠️ 손익은 가격×수량 기준 추정치입니다. 수수료 미반영.")
    return "\n".join(lines), page, total_pages


def build_report_view(trades: list, period: str = "all", cash_reports: list[dict] | None = None) -> str:
    """체결 기록 기반 수익률 리포트 메시지 생성 (전체, 페이지네이션 없음)."""
    from core.dca_manager import format_cash_health_section

    period_label = {"today": "오늘", "week": "최근 7일", "month": "최근 30일"}.get(period, "전체")
    by_key, totals = aggregate_trades(trades)

    lines = [f"📊 <b>수익률 리포트 ({period_label})</b>", ""]
    lines.extend(render_report_ticker_lines(sorted(by_key.items())))
    lines.extend(render_report_totals_lines(totals))
    batch_lines = render_batch_summary_lines(trades)
    if batch_lines:
        lines.append("")
        lines.extend(batch_lines)
    if cash_reports:
        lines.append("")
        lines.append(format_cash_health_section(cash_reports, html=True))
    lines.append("")
    lines.append("⚠️ 손익은 가격×수량 기준 추정치입니다. 수수료 미반영.")
    lines.append("")
    lines.append("📊 더 상세한 내역과 리포트는 [웹 대시보드]에서 확인하실 수 있습니다.")
    return "\n".join(lines)


def build_report_view_page(
    trades: list,
    period: str = "all",
    page: int = 0,
    page_size: int = REPORT_PAGE_SIZE,
    cash_reports: list[dict] | None = None,
):
    """/report 페이지네이션용 — 종목 그룹을 page_size개씩 잘라 보여주고 합계·배치요약·예수금 점검을 표시.

    반환: (text, page, total_pages)
    """
    from core.dca_manager import format_cash_health_section

    period_label = {"today": "오늘", "week": "최근 7일", "month": "최근 30일"}.get(period, "전체")
    by_key, totals = aggregate_trades(trades)
    items = sorted(by_key.items())
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    page_items = items[page * page_size: (page + 1) * page_size]

    lines = [f"📊 <b>수익률 리포트 ({period_label})</b>"]
    if total_pages > 1:
        lines.append(
            f"📄 {page + 1}/{total_pages} 페이지 (종목 {len(items)}개 중 {page * page_size + 1}-{page * page_size + len(page_items)}번째)"
        )
    lines.append("")
    lines.extend(render_report_ticker_lines(page_items))
    lines.extend(render_report_totals_lines(totals))
    batch_lines = render_batch_summary_lines(trades)
    if batch_lines:
        lines.append("")
        lines.extend(batch_lines)
    if cash_reports:
        lines.append("")
        lines.append(format_cash_health_section(cash_reports, html=True))
    lines.append("")
    lines.append("⚠️ 손익은 가격×수량 기준 추정치입니다. 수수료 미반영.")
    lines.append("")
    lines.append("📊 더 상세한 내역과 리포트는 [웹 대시보드]에서 확인하실 수 있습니다.")
    return "\n".join(lines), page, total_pages
