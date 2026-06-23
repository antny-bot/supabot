"""한글 종목명이 모호하게 매칭될 때 후보 선택을 위한 단일사용 TTL 토큰 저장소.

strategy_tokens.py / manual_order_tokens.py와 동일한 in-memory 패턴.
"""
import time

DISAMBIGUATION_TTL_SECONDS = 300
_pending_disambiguations: dict[str, dict] = {}


def create_disambiguation_token(
    user_id: str,
    original_text: str,
    raw_name: str,
    candidates: list[tuple[str, str]],
) -> str:
    token = str(len(_pending_disambiguations) + 1)
    while token in _pending_disambiguations:
        token = str(int(token) + 1)
    _pending_disambiguations[token] = {
        "user_id": str(user_id),
        "original_text": original_text,
        "raw_name": raw_name,
        "candidates": list(candidates),
        "created_at": time.time(),
    }
    return token


def pop_valid_disambiguation(token: str, user_id: str, idx: int):
    """토큰/유저/인덱스를 검증해 (code, original_text, raw_name) 또는 (None, error_msg, None)을 반환."""
    token = str(token)
    pending = _pending_disambiguations.get(token)
    if not pending:
        return None, "만료되었거나 찾을 수 없는 종목 선택 요청입니다. 다시 입력해 주세요.", None
    if pending.get("user_id") != str(user_id):
        return None, "다른 사용자의 종목 선택 요청은 실행할 수 없습니다.", None
    if time.time() - float(pending.get("created_at", 0)) > DISAMBIGUATION_TTL_SECONDS:
        _pending_disambiguations.pop(token, None)
        return None, "종목 선택 요청이 만료되었습니다. 다시 입력해 주세요.", None

    candidates = pending["candidates"]
    if idx < 0 or idx >= len(candidates):
        _pending_disambiguations.pop(token, None)
        return None, "유효하지 않은 종목 선택입니다. 다시 입력해 주세요.", None

    _pending_disambiguations.pop(token, None)
    _, code = candidates[idx]
    return code, pending["original_text"], pending["raw_name"]


_pending_nl_disambiguations: dict[str, dict] = {}


def create_nl_disambiguation_token(
    user_id: str,
    intent: dict,
    candidates: list[tuple[str, str]],
) -> str:
    """자연어(NL) 확인 흐름용 — 원문 텍스트 대신 intent dict 전체를 저장한다."""
    token = str(len(_pending_nl_disambiguations) + 1)
    while token in _pending_nl_disambiguations:
        token = str(int(token) + 1)
    _pending_nl_disambiguations[token] = {
        "user_id": str(user_id),
        "intent": dict(intent),
        "candidates": list(candidates),
        "created_at": time.time(),
    }
    return token


def pop_valid_nl_disambiguation(token: str, user_id: str, idx: int):
    """토큰/유저/인덱스를 검증해 (intent_with_resolved_ticker, None) 또는 (None, error_msg)을 반환."""
    token = str(token)
    pending = _pending_nl_disambiguations.get(token)
    if not pending:
        return None, "만료되었거나 찾을 수 없는 종목 선택 요청입니다. 다시 입력해 주세요."
    if pending.get("user_id") != str(user_id):
        return None, "다른 사용자의 종목 선택 요청은 실행할 수 없습니다."
    if time.time() - float(pending.get("created_at", 0)) > DISAMBIGUATION_TTL_SECONDS:
        _pending_nl_disambiguations.pop(token, None)
        return None, "종목 선택 요청이 만료되었습니다. 다시 입력해 주세요."

    candidates = pending["candidates"]
    if idx < 0 or idx >= len(candidates):
        _pending_nl_disambiguations.pop(token, None)
        return None, "유효하지 않은 종목 선택입니다. 다시 입력해 주세요."

    _pending_nl_disambiguations.pop(token, None)
    _, code = candidates[idx]
    intent = dict(pending["intent"])
    intent["ticker"] = code
    return intent, None
