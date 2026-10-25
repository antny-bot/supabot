import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from unittest.mock import MagicMock, patch

# DB 접속 타임아웃 방지
import core.db
core.db.is_db_available = lambda: False

import pytest
from pydantic import ValidationError

from core.nl_schema import TradeIntentModel
from handlers.nl_intent_handlers import (
    _build_llm_prompt,
    _update_user_nl_context,
    parse_natural_language_intent,
)


def test_trade_intent_model_validation():
    # 정상 케이스
    model = TradeIntentModel(
        action="buy",
        exchange="upbit",
        ticker="BTC",
        price=95000000.0,
        volume=0.01,
        amount_krw=1000000,
    )
    assert model.action == "buy"
    assert model.ticker == "BTC"
    assert model.exchange == "upbit"
    assert model.amount_krw == 1000000

    # 잘못된 액션 값 테스트
    with pytest.raises(ValidationError):
        TradeIntentModel(action="invalid_action_xyz")


def test_build_llm_prompt_with_recent_context():
    user = {"preferences": {"default_exchange": "bithumb"}}
    recent_ctx = [
        {"role": "user", "text": "비트코인 얼마야?"},
        {"role": "bot", "action": "price", "ticker": "BTC"},
    ]

    prompt = _build_llm_prompt("그럼 100만원어치 사줘", user, recent_context=recent_ctx)

    assert "Recent conversation context:" in prompt
    assert "User: 비트코인 얼마야?" in prompt
    assert "Bot resolved: action=price, ticker=BTC" in prompt
    assert "User text: 그럼 100만원어치 사줘" in prompt
    assert "Default exchange: bithumb" in prompt


def test_update_user_nl_context():
    context = MagicMock()
    context.user_data = {}

    # 첫 번째 대화
    _update_user_nl_context(context, "삼성전자 얼마야?", {"action": "price", "ticker": "005930"})
    history = context.user_data["_nl_recent_context"]
    assert len(history) == 2
    assert history[0] == {"role": "user", "text": "삼성전자 얼마야?"}
    assert history[1] == {"role": "bot", "action": "price", "ticker": "005930"}

    # 두 번째 대화
    _update_user_nl_context(context, "10주 사줘", {"action": "buy", "ticker": "005930"})
    history = context.user_data["_nl_recent_context"]
    assert len(history) == 4

    # 세 번째 대화 (최대 4개 초과 시 슬라이딩 윈도우 유지)
    _update_user_nl_context(context, "잔고는?", {"action": "asset"})
    history = context.user_data["_nl_recent_context"]
    assert len(history) == 4
    assert history[-1] == {"role": "bot", "action": "asset", "ticker": None}


@pytest.mark.asyncio
async def test_parse_natural_language_intent_mocked():
    user = {
        "llm": {"gemini_api_key": "test_key"},
        "preferences": {"llm_model": "gemini-2.5-flash-lite"},
    }

    mock_response = MagicMock()
    mock_response.text = '{"action": "buy", "ticker": "BTC", "amount_krw": 500000}'

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        intent = await parse_natural_language_intent("비트 50만 사줘", user)

    assert intent is not None
    assert intent["action"] == "buy"
    assert intent["ticker"] == "BTC"
    assert intent["amount_krw"] == 500000
