import time

from core.operational_events import append_operational_event

MANUAL_ORDER_TTL_SECONDS = 600

_pending_manual_orders = {}
_pending_cancel_orders = {}
_pending_reset_users = {}


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


def create_reset_token(admin_user_id, target_user_id):
    token = str(len(_pending_reset_users) + 1)
    while token in _pending_reset_users:
        token = str(int(token) + 1)
    _pending_reset_users[token] = {
        "admin_user_id": str(admin_user_id),
        "target_user_id": str(target_user_id),
        "created_at": time.time(),
    }
    return token


def pop_valid_reset_token(token, admin_user_id):
    token = str(token)
    pending = _pending_reset_users.get(token)
    if not pending:
        return None, "만료되었거나 찾을 수 없는 리셋 요청입니다. 다시 시도해 주세요."
    if pending.get("admin_user_id") != str(admin_user_id):
        return None, "다른 사용자의 리셋 요청은 실행할 수 없습니다."
    if time.time() - float(pending.get("created_at", 0)) > MANUAL_ORDER_TTL_SECONDS:
        _pending_reset_users.pop(token, None)
        return None, "리셋 요청이 만료되었습니다. 다시 시도해 주세요."
    _pending_reset_users.pop(token, None)
    return pending, None
