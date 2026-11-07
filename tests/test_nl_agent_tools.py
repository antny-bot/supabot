"""텔레그램 Gemini Function Calling 멀티턴 에이전트 및 Manager REST API 단위 테스트."""
import asyncio
import hashlib
import hmac
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import core.db
core.db.is_db_available = lambda: False

from core.nl_agent import run_nl_agent_loop, AgentRunResult, MAX_AGENT_STEPS
from core.nl_tools import (
    ALL_NL_TOOLS,
    NLToolContext,
    current_nl_context,
    get_account_balances,
    get_ticker_price,
    get_open_orders,
    propose_manual_order,
    propose_cancel_orders,
    propose_template_action,
)
from core.manager_api_client import _generate_hmac_headers, request_manager_api
from manager.backend.routers._auth import _extract_bot_auth_user, get_current_user
from handlers.nl_intent_handlers import (
    natural_language_command,
    natural_language_confirm_callback,
    execute_confirmed_actions,
)


def _create_mock_content(text=None, function_calls=None):
    from google.genai import types
    parts = []
    if text:
        parts.append(types.Part.from_text(text=text))
    if function_calls:
        for name, args in function_calls:
            fc = types.FunctionCall(name=name, args=args)
            parts.append(types.Part(function_call=fc))
    return types.Content(role="model", parts=parts)


def _create_mock_generate_response(content, text=None):
    mock_resp = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.content = content
    mock_resp.candidates = [mock_candidate]
    mock_resp.text = text or (content.parts[0].text if content.parts and content.parts[0].text else "")
    return mock_resp


# ==============================================================================
# 1. Phase 1 검증: HMAC 헤더 생성 및 Manager Auth 검증
# ==============================================================================


def test_hmac_header_generation_and_verification():
    secret_key = "test-manager-secret-key-123"
    with patch.dict(os.environ, {"MANAGER_API_KEY": secret_key}):
        bot_user_id = "12345678"
        path = "/api/templates"
        headers = _generate_hmac_headers(bot_user_id, path, is_admin=True)

        assert headers["X-Bot-User-Id"] == "12345678"
        assert headers["X-Is-Admin"] == "true"
        assert "X-Timestamp" in headers
        assert "X-Signature" in headers

        # 가짜 Request 객체로 _extract_bot_auth_user 검증
        mock_req = MagicMock()
        mock_req.headers = headers
        mock_req.url.path = "/api/templates"

        user = _extract_bot_auth_user(mock_req)
        assert user is not None
        assert user["email"] == "bot_12345678@telegram.local"
        assert user["is_admin"] is True
        assert user["bot_user_id"] == "12345678"


def test_hmac_header_tampered_or_expired():
    secret_key = "test-manager-secret-key-123"
    with patch.dict(os.environ, {"MANAGER_API_KEY": secret_key}):
        bot_user_id = "12345678"
        path = "/api/templates"
        headers = _generate_hmac_headers(bot_user_id, path, is_admin=False)

        mock_req = MagicMock()
        mock_req.headers = dict(headers)
        mock_req.url.path = "/api/templates"

        # 1. 서명 변조 시 거부
        mock_req.headers["X-Signature"] = "invalid_signature"
        assert _extract_bot_auth_user(mock_req) is None

        # 2. 5분 초과 타임스탬프 거부
        mock_req.headers = dict(headers)
        mock_req.headers["X-Timestamp"] = str(int(time.time()) - 400)
        assert _extract_bot_auth_user(mock_req) is None


# ==============================================================================
# 2. Phase 2 & 3 검증: 멀티턴 Read-Only 및 Write-Proposal 에이전트 루프
# ==============================================================================


@pytest.mark.asyncio
async def test_read_only_multi_step_query():
    """시나리오 1: '내 업비트 잔고랑 비트코인 현재가 같이 알려줘' -> 순수 읽기 도구 2종 연속 호출 후 요약."""
    user = {
        "llm": {"gemini_api_key": "test_api_key"},
        "preferences": {"llm_model": "gemini-2.5-flash-lite", "default_exchange": "upbit"},
    }

    mock_exchange_adapter = MagicMock()
    mock_exchange_adapter.resolve_ticker = AsyncMock(return_value="BTC")
    mock_exchange_adapter.get_ticker = AsyncMock(return_value={"price": 105000000.0, "high_price": 108000000.0, "low_price": 103000000.0, "change_rate": 0.02})
    mock_exchange_adapter.get_balances = AsyncMock(return_value=[
        {"currency": "KRW", "balance": "2500000", "locked": "0"},
        {"currency": "BTC", "balance": "0.15", "locked": "0", "avg_buy_price": "90000000"},
    ])

    # Step 1: get_account_balances & get_ticker_price 호출 반환
    step1_content = _create_mock_content(function_calls=[
        ("get_account_balances", {"exchange": "upbit"}),
        ("get_ticker_price", {"exchange": "upbit", "ticker": "BTC"}),
    ])
    # Step 2: 최종 자연어 텍스트 응답 반환
    final_text = "업비트 원화 잔고는 250만 원이며, BTC는 현재 1억 500만 원(+2.0%)입니다."
    step2_content = _create_mock_content(text=final_text)

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _create_mock_generate_response(step1_content),
        _create_mock_generate_response(step2_content, text=final_text),
    ]

    with patch("google.genai.Client", return_value=mock_client):
        result = await run_nl_agent_loop(
            text="내 업비트 잔고랑 비트코인 현재가 같이 알려줘",
            user=user,
            user_id="12345",
            exchange_adapter=mock_exchange_adapter,
        )

    assert result.reply_text == final_text
    assert len(result.proposed_actions) == 0  # 쓰기 제안 없음
    assert len(result.tool_trace) == 2        # 도구 2회 호출 기록
    tool_names = [t["tool"] for t in result.tool_trace]
    assert "get_account_balances" in tool_names
    assert "get_ticker_price" in tool_names


@pytest.mark.asyncio
async def test_lookup_then_propose_cancel_orders():
    """시나리오 2: '삼성전자 걸려있는 미체결 주문 확인해서 다 취소해줘' -> get_open_orders -> propose_cancel_orders."""
    user = {
        "llm": {"gemini_api_key": "test_api_key"},
        "preferences": {"llm_model": "gemini-2.5-flash-lite", "default_exchange": "kis"},
    }

    mock_order_mgr = MagicMock()
    mock_order_mgr.orders = [
        {"uuid": "order-uuid-1", "exchange": "kis", "ticker": "005930", "side": "bid", "price": 70000, "volume": 10, "status": "open", "created_at": "2026-11-08"},
        {"uuid": "order-uuid-2", "exchange": "kis", "ticker": "005930", "side": "bid", "price": 69000, "volume": 10, "status": "open", "created_at": "2026-11-08"},
    ]

    # Step 1: get_open_orders 호출
    step1_content = _create_mock_content(function_calls=[
        ("get_open_orders", {"exchange": "kis", "ticker": "005930"}),
    ])
    # Step 2: 주문 2건 확인 후 propose_cancel_orders 호출
    step2_content = _create_mock_content(function_calls=[
        ("propose_cancel_orders", {"exchange": "kis", "order_uuids": ["order-uuid-1", "order-uuid-2"], "reason": "사용자 요청 전량 취소"}),
    ])
    # Step 3: 최종 텍스트
    final_text = "삼성전자 미체결 매수 주문 2건(총 20주)에 대한 취소를 준비했습니다. 아래 버튼으로 승인해 주세요."
    step3_content = _create_mock_content(text=final_text)

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _create_mock_generate_response(step1_content),
        _create_mock_generate_response(step2_content),
        _create_mock_generate_response(step3_content, text=final_text),
    ]

    with patch("google.genai.Client", return_value=mock_client):
        result = await run_nl_agent_loop(
            text="삼성전자 걸려있는 미체결 주문 확인해서 다 취소해줘",
            user=user,
            user_id="12345",
            order_manager=mock_order_mgr,
        )

    assert result.reply_text == final_text
    assert len(result.proposed_actions) == 1
    act = result.proposed_actions[0]
    assert act["action_type"] == "cancel_orders"
    assert act["exchange"] == "kis"
    assert act["order_uuids"] == ["order-uuid-1", "order-uuid-2"]


@pytest.mark.asyncio
async def test_balance_check_then_propose_half_buy():
    """시나리오 3: '업비트 잔고 절반으로 비트코인 1억원에 사줘' -> get_account_balances -> propose_manual_order."""
    user = {
        "llm": {"gemini_api_key": "test_api_key"},
        "preferences": {"llm_model": "gemini-2.5-flash-lite", "default_exchange": "upbit"},
    }

    mock_exchange_adapter = MagicMock()
    mock_exchange_adapter.resolve_ticker = AsyncMock(return_value="BTC")
    mock_exchange_adapter.get_balances = AsyncMock(return_value=[
        {"currency": "KRW", "balance": "2000000", "locked": "0"},
    ])

    # Step 1: 잔고 조회
    step1_content = _create_mock_content(function_calls=[
        ("get_account_balances", {"exchange": "upbit"}),
    ])
    # Step 2: 원화 200만 확인 -> 절반 100만 원어치 1억원 지정가 매수 제안 (volume = 0.01)
    step2_content = _create_mock_content(function_calls=[
        ("propose_manual_order", {
            "exchange": "upbit",
            "ticker": "BTC",
            "side": "bid",
            "price": 100000000.0,
            "volume": 0.01,
            "amount_krw": 1000000.0,
        }),
    ])
    # Step 3: 최종 텍스트
    final_text = "업비트 원화 잔고 200만 원 중 절반인 100만 원으로 비트코인 0.01 BTC(단가 1억 원) 지정가 매수를 제안합니다."
    step3_content = _create_mock_content(text=final_text)

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _create_mock_generate_response(step1_content),
        _create_mock_generate_response(step2_content),
        _create_mock_generate_response(step3_content, text=final_text),
    ]

    with patch("google.genai.Client", return_value=mock_client):
        result = await run_nl_agent_loop(
            text="업비트 잔고 절반으로 비트코인 1억원에 사줘",
            user=user,
            user_id="12345",
            exchange_adapter=mock_exchange_adapter,
        )

    assert len(result.proposed_actions) == 1
    act = result.proposed_actions[0]
    assert act["action_type"] == "manual_order"
    assert act["ticker"] == "BTC"
    assert act["price"] == 100000000.0
    assert act["volume"] == 0.01


@pytest.mark.asyncio
async def test_agent_loop_max_steps_guard():
    """시나리오 4: 도구 호출이 무한 반복되는 비정상 상황에서 MAX_AGENT_STEPS(5)에 안전 종료."""
    user = {
        "llm": {"gemini_api_key": "test_api_key"},
        "preferences": {"llm_model": "gemini-2.5-flash-lite"},
    }

    # 끝없이 get_user_settings 도구를 호출하는 무한 루프 시뮬레이션
    infinite_tool_content = _create_mock_content(function_calls=[
        ("get_user_settings", {}),
    ])

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _create_mock_generate_response(infinite_tool_content)

    with patch("google.genai.Client", return_value=mock_client):
        result = await run_nl_agent_loop(
            text="루프 테스트",
            user=user,
            user_id="12345",
            max_steps=5,
        )

    assert "최대 단계(5회)에 도달했습니다" in result.reply_text
    assert len(result.tool_trace) == 5


# ==============================================================================
# 3. Phase 4 검증: 핸들러 통합 및 사용자 승인/취소 라이프사이클
# ==============================================================================


@pytest.mark.asyncio
async def test_full_telegram_handler_flow_with_confirmation():
    """시나리오 5: 사용자 입력 -> AI 에이전트 루프 -> 실행 계획 제안 및 인라인 버튼 -> [✅ 실행] 클릭 후 실제 주문 실행."""
    import main

    user = {
        "user_id": "99999",
        "is_active": True,
        "llm": {"gemini_api_key": "test_api_key"},
        "preferences": {"llm_enabled": True, "default_exchange": "upbit"},
    }

    mock_update = MagicMock()
    mock_update.effective_user.id = "99999"
    mock_update.effective_chat.id = "99999"
    mock_update.message.text = "업비트 비트코인 1억원에 100만원어치 사줘"

    status_msg = AsyncMock()
    mock_update.message.reply_text = AsyncMock(return_value=status_msg)

    # 1. 에이전트 결과 모킹 (단일 매수 제안)
    mock_agent_result = AgentRunResult(
        reply_text="비트코인 1억원 지정가 매수 계획을 준비했습니다.",
        proposed_actions=[{
            "action_type": "manual_order",
            "exchange": "upbit",
            "ticker": "BTC",
            "side": "bid",
            "price": 100000000.0,
            "volume": 0.01,
            "amount_krw": 1000000.0,
        }],
        tool_trace=[{"tool": "propose_manual_order"}],
    )

    with patch("handlers.nl_intent_handlers.run_nl_agent_loop", return_value=mock_agent_result):
        with patch.object(main.user_manager, "get_user", return_value=user):
            await natural_language_command(mock_update, MagicMock())

    # 확인 메시지가 status_msg.edit_text로 전송되었는지 검증
    status_msg.edit_text.assert_called_once()
    confirm_args, confirm_kwargs = status_msg.edit_text.call_args
    assert "📋 **실행 계획 (1건)**" in confirm_args[0]
    assert "reply_markup" in confirm_kwargs

    # main._pending_nl_intents에 저장된 토큰 확인
    pending_tokens = list(main._pending_nl_intents.keys())
    assert len(pending_tokens) > 0
    token = pending_tokens[-1]
    pending_item = main._pending_nl_intents[token]
    assert pending_item["user_id"] == "99999"
    assert len(pending_item["actions"]) == 1

    # 2. 사용자가 [✅ 실행] 인라인 버튼 클릭 시뮬레이션
    mock_cb_update = MagicMock()
    mock_cb_query = AsyncMock()
    mock_cb_query.data = f"nlrun|{token}"
    mock_cb_query.from_user.id = "99999"
    mock_cb_update.callback_query = mock_cb_query

    mock_exchange_adapter = MagicMock()
    mock_exchange_adapter.get_exchange.return_value.round_volume = lambda v: v
    mock_exchange_adapter.create_order = AsyncMock(return_value={"uuid": "real-exchange-uuid-999"})

    with patch.object(main, "exchange_adapter", mock_exchange_adapter):
        with patch.object(main.user_manager, "get_user", return_value=user):
            await natural_language_confirm_callback(mock_cb_update, MagicMock())

    # 실제 거래소 create_order가 비로소 호출되었는지 검증
    mock_exchange_adapter.create_order.assert_called_once_with(
        "99999", "upbit", "BTC", "bid", 100000000.0, 0.01
    )
    # 실행 완료 결과가 메시지에 반영되었는지 검증
    mock_cb_query.edit_message_text.assert_called_once()
    result_text = mock_cb_query.edit_message_text.call_args[0][0]
    assert "성공 (ID: real-exchange-uuid-999)" in result_text


# ==============================================================================
# 4. Phase 6 검증: 관리자 > NL 로그 리포트 API 멀티턴 도구 체인 및 통계 검증
# ==============================================================================


@pytest.mark.asyncio
async def test_api_reports_nl_logs_multiturn_and_stats():
    """관리자 NL 로그 리포트 API가 멀티턴 도구 체인과 통계를 정확히 계산하여 반환하는지 검증."""
    from manager.backend.routers.reports import api_reports_nl_logs

    mock_req = MagicMock()
    mock_req.session = {"user_email": "admin@supabot.local", "is_admin": True}

    mock_db = MagicMock()
    mock_rows = [
        {
            "id": "nl-1",
            "user_id": "111",
            "raw_text": "내 잔고랑 비트 시세 알려줘",
            "llm_action": "get_account_balances, get_ticker_price",
            "final_action": "answer",
            "confirm_status": "auto",
            "logged_at": time.time(),
        },
        {
            "id": "nl-2",
            "user_id": "222",
            "raw_text": "비트코인 100만원어치 사줘",
            "llm_action": "propose_manual_order",
            "final_action": "multi_action",
            "confirm_status": "confirmed",
            "logged_at": time.time() - 100,
        },
    ]

    mock_query = MagicMock()
    mock_res = MagicMock()
    mock_res.data = mock_rows
    mock_query.order.return_value.limit.return_value = mock_query
    mock_query.execute = AsyncMock(return_value=mock_res)
    mock_query._params = {}

    count_res = MagicMock()
    count_res.count = 2
    count_query = MagicMock()
    count_query.execute = AsyncMock(return_value=count_res)

    def table_side_effect(name):
        t = MagicMock()
        t.select.side_effect = lambda *args, **kwargs: count_query if kwargs.get("count") == "exact" else mock_query
        return t

    mock_db.table.side_effect = table_side_effect

    with patch("manager.backend.routers.reports.is_db_available", return_value=True):
        with patch("manager.backend.routers.reports.get_db", return_value=mock_db):
            response = await api_reports_nl_logs(mock_req)

    import json
    data = json.loads(response.body)
    assert response.status_code == 200
    assert len(data["rows"]) == 2

    # 멀티턴 도구 체인 검증
    first_row = data["rows"][0]
    assert first_row["tool_chain"] == ["get_account_balances", "get_ticker_price"]
    assert first_row["tool_count"] == 2
    assert first_row["is_multi_turn"] is True

    # 통계 검증
    stats = data["stats"]
    assert stats["total_queries"] == 2
    assert stats["tool_call_count"] == 2
    assert stats["multi_turn_count"] == 1
    assert stats["confirmed_count"] == 1
    assert stats["approval_rate"] == 100.0  # 결정된 1건 중 1건 승인
    top_tool_names = [t["tool"] for t in stats["top_tools"]]
    assert "get_account_balances" in top_tool_names


@pytest.mark.asyncio
async def test_api_reports_nl_logs_file_fallback(tmp_path):
    """DB 미사용 환경에서 data/nl_unmatched.jsonl 로컬 파일로부터 멀티턴 로그를 안전하게 읽어오는지 검증."""
    from manager.backend.routers.reports import api_reports_nl_logs
    import json

    mock_file = tmp_path / "nl_unmatched.jsonl"
    sample_records = [
        {
            "id": "nl_local_1",
            "ts": "2026-11-08T00:00:00+09:00",
            "text_norm": "미체결 취소해줘",
            "llm_action": "get_open_orders, propose_cancel_orders",
            "final_action": "multi_action",
            "confirm_status": "rejected",
            "logged_at": time.time(),
        }
    ]
    with open(mock_file, "w", encoding="utf-8") as f:
        for r in sample_records:
            f.write(json.dumps(r) + "\n")

    mock_req = MagicMock()
    mock_req.session = {"user_email": "admin@supabot.local", "is_admin": True}

    with patch.dict(os.environ, {"NL_UNMATCHED_LOG_PATH": str(mock_file)}):
        with patch("manager.backend.routers.reports.is_db_available", return_value=False):
            response = await api_reports_nl_logs(mock_req)

    data = json.loads(response.body)
    assert response.status_code == 200
    assert len(data["rows"]) == 1
    assert data["rows"][0]["id"] == "nl_local_1"
    assert data["rows"][0]["is_multi_turn"] is True
    assert data["rows"][0]["tool_chain"] == ["get_open_orders", "propose_cancel_orders"]
    assert data["stats"]["rejected_count"] == 1

