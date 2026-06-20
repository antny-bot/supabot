"""전략 주문(거미줄/RSI) 확인 버튼용 단일 사용 토큰 저장소.

`manual_order_tokens.py`와 동일한 패턴(인메모리, TTL, 단일 사용 pop)으로,
전략 confirm 콜백의 멱등성을 보장한다. 기존에는 전 파라미터를 텔레그램
callback_data에 인코딩(64바이트 한도 초과 위험 + 더블탭 시 중복 발행)했으나,
토큰만 callback_data에 싣고 실제 payload는 서버 메모리에 보관한다.

get→pop 사이에 await가 없어(asyncio 단일 스레드) 더블탭 시 두 번째 클릭은
이미 pop된 토큰을 찾지 못해 "만료/찾을 수 없음"으로 안전하게 처리된다.
"""
import time

from core.operational_events import append_operational_event

STRATEGY_ORDER_TTL_SECONDS = 600

_pending_strategy_orders = {}


def create_strategy_token(user_id, kind, payload: dict):
    """전략 확인 토큰 생성.

    kind: "gridrun" | "sgridrun" | "rsitrun" | "sgridrsirun"
    payload: 실행에 필요한 전 파라미터 dict (거래소/티커/가격/RSI구간/횟수/예산/dca 등)
    """
    token = str(len(_pending_strategy_orders) + 1)
    while token in _pending_strategy_orders:
        token = str(int(token) + 1)
    _pending_strategy_orders[token] = {
        "user_id": str(user_id),
        "kind": kind,
        "payload": dict(payload),
        "created_at": time.time(),
    }
    return token


def pop_valid_strategy_token(token, user_id):
    """토큰을 단일 사용으로 소비하고 payload를 반환한다.

    반환: (payload_dict, None) 또는 (None, error_message)
    """
    token = str(token)
    pending = _pending_strategy_orders.get(token)
    if not pending:
        return None, "만료되었거나 찾을 수 없는 전략 확인 요청입니다. 다시 입력해 주세요."
    if pending.get("user_id") != str(user_id):
        return None, "다른 사용자의 전략 확인 요청은 실행할 수 없습니다."
    if time.time() - float(pending.get("created_at", 0)) > STRATEGY_ORDER_TTL_SECONDS:
        _pending_strategy_orders.pop(token, None)
        append_operational_event("warning", "strategy_order", "strategy order confirmation expired", pending.get("kind"))
        return None, "전략 확인 요청이 만료되었습니다. 다시 입력해 주세요."
    _pending_strategy_orders.pop(token, None)
    return pending["payload"], None


def discard_strategy_token(token):
    """취소 등으로 토큰을 폐기한다 (조용히, 에러 무시)."""
    _pending_strategy_orders.pop(str(token), None)
