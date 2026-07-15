"""/orders,/status,/history,/report,/asset 펼치기·페이지네이션 버튼용 다회용 토큰 저장소.

`manual_order_tokens.py`/`strategy_tokens.py`와 같은 인메모리 TTL 토큰 패턴이지만,
confirm 버튼과 달리 같은 메시지에서 사용자가 펼치기/접기/이전/다음을 여러 번 누를 수
있어야 하므로 **단일 사용(pop)이 아니라 비파괴 조회(peek)** 로 동작한다. 클릭마다
`last_access`를 갱신하는 sliding TTL이라, 계속 보고 있는 메시지는 만료되지 않고
방치된 메시지만 마지막 클릭 후 TTL 경과 시 만료된다.
"""
import time

from core.operational_events import append_operational_event

LIST_VIEW_TTL_SECONDS = 600

_pending_list_views = {}


def create_list_view_token(user_id, kind, state: dict, snapshot=None):
    """리스트뷰 토큰 생성.

    kind: "orders" | "status" | "history" | "report" | "asset"
    state: 현재 표시 상태(예: {"expanded": False}, {"page": 0}) — 클릭마다 in-place 갱신됨
    snapshot: history/report/asset처럼 조회 비용이 있는 데이터를 명령어 실행 시점에 고정해
              담아둔다. orders/status는 매 클릭 라이브 재조회하므로 None.
    """
    token = str(len(_pending_list_views) + 1)
    while token in _pending_list_views:
        token = str(int(token) + 1)
    now = time.time()
    _pending_list_views[token] = {
        "user_id": str(user_id),
        "kind": kind,
        "state": dict(state),
        "snapshot": snapshot,
        "created_at": now,
        "last_access": now,
    }
    return token


def peek_list_view(token, user_id):
    """토큰을 소비하지 않고 조회한다 (sliding TTL 갱신).

    반환: (entry_dict, None) 또는 (None, error_message)
    """
    token = str(token)
    entry = _pending_list_views.get(token)
    if not entry:
        return None, "만료되었거나 찾을 수 없는 조회 요청입니다. 명령어를 다시 입력해 주세요."
    if entry.get("user_id") != str(user_id):
        return None, "다른 사용자의 조회 요청은 실행할 수 없습니다."
    if time.time() - float(entry.get("last_access", 0)) > LIST_VIEW_TTL_SECONDS:
        _pending_list_views.pop(token, None)
        append_operational_event("info", "list_view", "list view session expired", entry.get("kind"))
        return None, "조회 세션이 만료되었습니다. 명령어를 다시 입력해 주세요."
    entry["last_access"] = time.time()
    return entry, None


def update_list_view_state(token, **updates):
    """entry["state"]를 in-place 갱신한다. peek_list_view로 유효성 검증 후 호출할 것."""
    entry = _pending_list_views.get(str(token))
    if entry is None:
        return
    entry["state"].update(updates)


def discard_list_view(token):
    """토큰을 즉시 폐기한다 (조용히, 에러 무시)."""
    _pending_list_views.pop(str(token), None)
