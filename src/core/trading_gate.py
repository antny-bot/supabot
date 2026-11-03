"""글로벌 거래 중지(kill-switch) 게이트.

관리자가 `/halt`로 전체 거래를 즉시 중단하고 `/resume`로 재개한다. 주문 발행
초크포인트(수동 주문 confirm, 전략 confirm, KIS 재주문)에서 `assert_can_trade()`로
차단한다. 손절/익절 등 보호성 매도는 차단하지 않는다(포지션 방치 방지).

저장: `system_config` 테이블 key `trading_halt` (`'1'`/`'0'`). DB 미사용 시
`data/trading_halt.flag` 파일 존재 여부로 폴백. 프로세스 인메모리 캐시 병행.
"""
import os
import time

from core.bot_logger import get_logger
from core.db import get_db, is_db_available
from core.operational_events import append_operational_event

_log = get_logger("trading_gate")

_HALT_KEY = "trading_halt"
_HALT_FLAG_FILE = "data/trading_halt.flag"
_HALT_MESSAGE = "🛑 관리자가 전체 거래를 일시 중지했습니다. (/resume 으로 재개)"

# 프로세스 인메모리 캐시 — DB/파일 조회 실패 시 마지막 알려진 상태 유지.
# is_trading_halted()는 주문 발행 게이트와 sync_orders 루프(async 핫경로)에서 호출되는데,
# 동기 requests 기반 DB 조회를 매번 수행하면 DB 지연 시 이벤트 루프가 통째로 블로킹된다.
# 짧은 TTL 캐시로 DB 조회 빈도를 낮추되, set_trading_halt()는 캐시를 즉시 갱신하므로
# 같은 프로세스 내 /halt·/resume은 지연 없이 즉시 반영된다(타 프로세스 변경만 최대 TTL 지연).
_HALT_CACHE_TTL_SECONDS = 5
_halt_cache = None
_halt_cache_ts = 0.0

# 전략 패밀리 매핑 (동일 종목 복수 전략 충돌 방지용)
_STRATEGY_FAMILIES = {
    "rsitrade": "rsi",
    "rsitrade_sell": "rsi",
    "gridrsi": "rsi",
    "grid": "grid",
    "sgrid": "grid",
    "sgridrsi": "sgridrsi",
    "dca": "dca",
    "sdca": "dca",
    "kospi_top": "kospi_top",
}

# KOSPI 대표 시총 상위 TOP 10 대형주 (유니버스 분리 정책 전담 종목)
DEFAULT_TOP_UNIVERSE_TICKERS = {
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "373220",  # LG에너지솔루션
    "207940",  # 삼성바이오로직스
    "005380",  # 현대차
    "000270",  # 기아
    "068270",  # 셀트리온
    "105560",  # KB금융
    "055550",  # 신한지주
    "012450",  # 한화에어로스페이스
}


def is_top_universe_ticker(ticker: str, custom_top_tickers: set = None) -> bool:
    """해당 종목이 TOP N 전략 전담 대형주 유니버스에 속하는지 판별한다."""
    if not ticker:
        return False
    t = str(ticker).strip().upper()
    top_set = custom_top_tickers if custom_top_tickers is not None else DEFAULT_TOP_UNIVERSE_TICKERS
    return t in top_set


def get_strategy_family(strategy: str) -> str:
    """전략 이름을 전략 패밀리 그룹명으로 정규화한다."""
    if not strategy:
        return "manual"
    return _STRATEGY_FAMILIES.get(strategy.lower(), strategy.lower())


def assert_single_strategy_per_ticker(
    open_orders,
    ticker: str,
    strategy: str = "manual",
    dca_schedules=None,
    top_universe_tickers=None,
    enforce_universe_partition: bool = True,
):
    """종목 독점 및 유니버스 분리 원칙(Universe Partitioning) 검증.

    동일 종목(ticker)에 대해 이미 다른 전략 패밀리의 활성 주문이나 DCA 스케줄이 운용 중인 경우 차단한다.
    또한 유니버스 분리 정책에 따라 TOP N 대형주 전담 종목에 대해 개별 전략(RSI, Grid 등) 신규 등록을 차단한다.
    - manual(수동), stoploss(손절)는 검사에서 완전 면제되어 항상 허용.
    - 동일 전략 패밀리 내(예: rsitrade 매수와 rsitrade_sell 익절 매도)는 동일 전략으로 취급하여 허용.
    (ok: bool, message: str | None) 반환.
    """
    if not ticker or strategy in ("manual", "stoploss"):
        return True, None

    new_family = get_strategy_family(strategy)

    # 1. 유니버스 분리 검증: TOP N 대형주 전담 종목에 개별 전략 진입 차단
    if enforce_universe_partition and new_family != "kospi_top":
        if is_top_universe_ticker(ticker, custom_top_tickers=top_universe_tickers):
            return False, (
                f"🛑 [{ticker}] 해당 종목은 'TOP N 모으기 전략' 전담 종목입니다. "
                f"유니버스 분리 정책에 따라 개별 전략(RSI/그리드)으로 등록할 수 없습니다. "
                f"(시총 11위 이하 종목이나 코스닥/코인을 선택해주세요)"
            )

    # 2. 오픈 주문(order_manager) 검사
    for o in open_orders or []:
        if o.get("ticker") == ticker:
            o_strat = o.get("strategy")
            if not o_strat or o_strat in ("manual", "stoploss"):
                continue
            o_family = get_strategy_family(o_strat)
            if o_family != new_family:
                return False, f"🛑 [{ticker}] 이미 '{o_strat}' 전략이 운용 중입니다. 포지션 충돌을 방지하기 위해 동일 종목의 복수 전략 동시 운용은 제한됩니다."

    # 3. 활성 DCA 스케줄 검사
    if dca_schedules:
        for sched in dca_schedules:
            if sched.get("ticker") == ticker:
                if new_family != "dca":
                    return False, f"🛑 [{ticker}] 이미 정기적립(DCA) 전략이 운용 중입니다. 동일 종목의 복수 전략 동시 운용은 제한됩니다."

    return True, None


def is_trading_halted() -> bool:
    """현재 거래 중지 상태를 반환한다. TTL 캐시 → DB → 파일 → 인메모리 캐시 순."""
    global _halt_cache, _halt_cache_ts
    now = time.time()
    if _halt_cache is not None and (now - _halt_cache_ts) < _HALT_CACHE_TTL_SECONDS:
        return _halt_cache
    if is_db_available():
        try:
            rows = get_db().table("system_config").select("value").eq("key", _HALT_KEY).execute().data
            halted = bool(rows) and str(rows[0].get("value")) == "1"
            _halt_cache = halted
            _halt_cache_ts = now
            return halted
        except Exception as e:
            _log.warning("Failed to read trading_halt from DB, falling back", exc_info=e)
    if os.path.exists(_HALT_FLAG_FILE):
        _halt_cache = True
        _halt_cache_ts = now
        return True
    if _halt_cache is not None:
        return _halt_cache
    return False


def set_trading_halt(halted: bool, by_user_id=None) -> None:
    """거래 중지 상태를 설정한다 (DB + 파일 폴백 이중 기록)."""
    global _halt_cache, _halt_cache_ts
    _halt_cache = bool(halted)
    _halt_cache_ts = time.time()
    value = "1" if halted else "0"
    if is_db_available():
        try:
            get_db().table("system_config").upsert({"key": _HALT_KEY, "value": value}).execute()
        except Exception as e:
            _log.error("Failed to persist trading_halt to DB", exc_info=e)
    # 파일 폴백도 항상 동기화해 DB 장애 시에도 상태 일관성 유지.
    try:
        if halted:
            os.makedirs(os.path.dirname(_HALT_FLAG_FILE), exist_ok=True)
            with open(_HALT_FLAG_FILE, "w", encoding="utf-8") as f:
                f.write("1")
        elif os.path.exists(_HALT_FLAG_FILE):
            os.remove(_HALT_FLAG_FILE)
    except Exception as e:
        _log.error("Failed to sync trading_halt flag file", exc_info=e)
    append_operational_event(
        "warning", "trading_gate",
        f"trading {'halted' if halted else 'resumed'}",
        str(by_user_id) if by_user_id else None,
    )


def assert_can_trade():
    """거래 가능 여부를 (ok, message) 튜플로 반환한다. 중지 시 (False, 안내문)."""
    if is_trading_halted():
        return False, _HALT_MESSAGE
    return True, None


def assert_risk_limits(user, open_orders, new_order_krw, ticker=None, side="bid", strategy="manual", today_order_count=0, today_realized_loss_krw=0.0):
    """글로벌 리스크 한도 검증 (F2).

    - 보호성 매도(손절, stoploss)는 한도와 무관하게 항상 허용.
    - 종목별 최대 노출액, 일일 최대 주문 건수, 일일 최대 손실액 검증.
    (ok: bool, message: str | None) 반환.
    """
    # 보호성 매도(손절)는 항상 허용
    if strategy == "stoploss":
        return True, None

    prefs = (user or {}).get("preferences", {})

    # 1. 일일 최대 주문 건수 검증
    daily_max_orders = prefs.get("daily_max_order_count")
    if daily_max_orders is not None and today_order_count >= int(daily_max_orders):
        return False, f"🛑 일일 최대 주문 건수({daily_max_orders}건)에 도달하여 신규 주문이 제한됩니다."

    # 2. 일일 최대 손실액 검증
    daily_max_loss = prefs.get("daily_max_loss_krw")
    if daily_max_loss is not None and today_realized_loss_krw >= float(daily_max_loss):
        return False, f"🛑 일일 최대 허용 손실액({float(daily_max_loss):,.0f}원)을 초과하여 신규 주문이 제한됩니다."

    # 3. 종목별 최대 노출액 검증 (매수 주문에만 적용)
    max_ticker_exposure = prefs.get("max_ticker_exposure_krw")
    if max_ticker_exposure is not None and side == "bid" and ticker:
        ticker_current_exposure = 0.0
        for o in open_orders or []:
            if o.get("ticker") == ticker and o.get("side") == "bid":
                rem = max(float(o.get("volume", 0)) - float(o.get("filled_volume", 0)), 0)
                ticker_current_exposure += rem * float(o.get("price", 0))

        if ticker_current_exposure + float(new_order_krw) > float(max_ticker_exposure):
            return False, f"🛑 [{ticker}] 종목별 최대 노출 한도({float(max_ticker_exposure):,.0f}원)를 초과합니다 (현재: {ticker_current_exposure:,.0f}원)."

    return True, None


def check_can_place_order(user, open_orders, new_order_krw, is_usd=False, ticker=None, side="bid", strategy="manual", today_order_count=0, today_realized_loss_krw=0.0):
    """주문 발행 직전 통합 게이트: 글로벌 중지 + 총 노출 한도 + 리스크 한도(F2). (ok, message) 반환."""
    # 손절은 글로벌 중지와 상관없이 허용
    if strategy == "stoploss":
        return True, None

    ok, msg = assert_can_trade()
    if not ok:
        return ok, msg

    # 리스크 한도 검증
    risk_ok, risk_msg = assert_risk_limits(
        user, open_orders, new_order_krw,
        ticker=ticker, side=side, strategy=strategy,
        today_order_count=today_order_count,
        today_realized_loss_krw=today_realized_loss_krw,
    )
    if not risk_ok:
        return risk_ok, risk_msg

    # 종목 독점 원칙 (Single Strategy per Ticker) 검증
    strat_ok, strat_msg = assert_single_strategy_per_ticker(open_orders, ticker=ticker, strategy=strategy)
    if not strat_ok:
        return strat_ok, strat_msg

    from core.parsers import compute_open_exposure_krw, validate_total_exposure
    return validate_total_exposure(
        user, compute_open_exposure_krw(open_orders), new_order_krw, is_usd,
    )
