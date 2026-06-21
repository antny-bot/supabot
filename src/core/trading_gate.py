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


def check_can_place_order(user, open_orders, new_order_krw, is_usd=False):
    """주문 발행 직전 통합 게이트: 글로벌 중지 + 총 노출 한도. (ok, message) 반환."""
    ok, msg = assert_can_trade()
    if not ok:
        return ok, msg
    from core.parsers import compute_open_exposure_krw, validate_total_exposure
    return validate_total_exposure(
        user, compute_open_exposure_krw(open_orders), new_order_krw, is_usd,
    )
