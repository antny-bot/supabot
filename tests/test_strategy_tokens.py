import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import core.strategy_tokens as st
from core.strategy_tokens import (
    create_strategy_token,
    pop_valid_strategy_token,
    discard_strategy_token,
)


def _payload():
    return {"exchange": "upbit", "ticker": "KRW-BTC", "start_p": 100, "count": 5, "budget": 1000}


def test_create_and_pop_returns_payload():
    token = create_strategy_token("u1", "gridrun", _payload())
    payload, error = pop_valid_strategy_token(token, "u1")
    assert error is None
    assert payload["ticker"] == "KRW-BTC"
    assert payload["budget"] == 1000


def test_single_use_double_tap_second_click_rejected():
    """더블탭 방지: 첫 클릭은 성공, 두 번째 클릭은 만료/없음 처리."""
    token = create_strategy_token("u1", "gridrun", _payload())
    payload1, err1 = pop_valid_strategy_token(token, "u1")
    payload2, err2 = pop_valid_strategy_token(token, "u1")
    assert err1 is None and payload1 is not None
    assert payload2 is None
    assert err2 is not None


def test_wrong_user_rejected_and_token_preserved():
    token = create_strategy_token("u1", "gridrun", _payload())
    payload, error = pop_valid_strategy_token(token, "intruder")
    assert payload is None
    assert "다른 사용자" in error
    # 정당한 사용자는 여전히 사용 가능해야 한다 (소유자 검증 실패가 토큰을 소모하지 않음)
    payload2, error2 = pop_valid_strategy_token(token, "u1")
    assert error2 is None and payload2 is not None


def test_expired_token_rejected(monkeypatch):
    token = create_strategy_token("u1", "gridrun", _payload())
    st._pending_strategy_orders[token]["created_at"] = 0  # 아주 오래 전
    payload, error = pop_valid_strategy_token(token, "u1")
    assert payload is None
    assert "만료" in error


def test_unknown_token_rejected():
    payload, error = pop_valid_strategy_token("does-not-exist", "u1")
    assert payload is None
    assert error is not None


def test_discard_token():
    token = create_strategy_token("u1", "gridrun", _payload())
    discard_strategy_token(token)
    payload, error = pop_valid_strategy_token(token, "u1")
    assert payload is None
