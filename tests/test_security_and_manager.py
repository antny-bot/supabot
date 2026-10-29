import asyncio
import os
import subprocess
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from manager.backend.main import app, realtime_manager, _is_rate_limited, _reset_rate_limit
from src import internal_api


def test_session_secret_validation_raises():
    """S1: SESSION_SECRET 미설정 또는 기본값 시 기동 실패 검증"""
    cmd = [
        sys.executable,
        "-c",
        "import os; os.environ['SESSION_SECRET'] = 'change-me-in-production'; import manager.backend.main",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode != 0
    assert "SESSION_SECRET must be set" in res.stderr

    cmd_empty = [
        sys.executable,
        "-c",
        "import os; os.environ['SESSION_SECRET'] = ''; import manager.backend.main",
    ]
    res_empty = subprocess.run(cmd_empty, capture_output=True, text=True)
    assert res_empty.returncode != 0
    assert "SESSION_SECRET must be set" in res_empty.stderr


def test_csrf_origin_validation():
    """S2: Origin/Referer 검증 미들웨어 동작 검증"""
    client = TestClient(app)

    # 1. 허용되지 않은 Origin의 POST 요청 -> 403
    with patch.dict(os.environ, {"MANAGER_ALLOWED_ORIGINS": "https://allowed.example.com"}):
        resp = client.post(
            "/api/login",
            json={"email": "test@example.com", "password": "pass"},
            headers={"Origin": "https://attacker.example.com"},
        )
        assert resp.status_code == 403
        assert "Forbidden" in resp.json().get("error", "")

        # 2. 허용된 Origin의 요청 -> 403이 아님 (인증 실패 401 등 정상 흐름)
        resp_allowed = client.post(
            "/api/login",
            json={"email": "test@example.com", "password": "pass"},
            headers={"Origin": "https://allowed.example.com"},
        )
        assert resp_allowed.status_code != 403

        # 3. /api/realtime/trigger 경로는 Origin 검증 예외
        with patch.dict(os.environ, {"MANAGER_API_KEY": "test-key"}):
            resp_trigger = client.post(
                "/api/realtime/trigger",
                json={"event": "refresh"},
                headers={"Origin": "https://attacker.example.com", "X-API-Key": "test-key"},
            )
            assert resp_trigger.status_code == 200


def test_realtime_trigger_auth_compare_digest():
    """S3: 매니저 API Key 검증 (상수시간 비교)"""
    client = TestClient(app)
    with patch.dict(os.environ, {"MANAGER_API_KEY": "super-secret-key-123"}):
        # 1. 키 미제공 -> 401
        resp = client.post("/api/realtime/trigger", json={})
        assert resp.status_code == 401

        # 2. 잘못된 키 -> 401
        resp_bad = client.post("/api/realtime/trigger", json={}, headers={"X-API-Key": "wrong-key"})
        assert resp_bad.status_code == 401

        # 3. 올바른 키 -> 200
        resp_ok = client.post("/api/realtime/trigger", json={}, headers={"X-API-Key": "super-secret-key-123"})
        assert resp_ok.status_code == 200
        assert resp_ok.json() == {"ok": True}


@pytest.mark.asyncio
async def test_internal_api_500_masks_error_details():
    """S4: 예외 발생 시 500 응답 본문이 'Internal error'로 마스킹되는지 검증"""
    req = MagicMock()
    req.remote = "127.0.0.1"
    req.headers = {
        "X-Timestamp": str(int(time.time())),
        "X-Signature": "mocked",
    }
    # HMAC 검증 통과 모킹
    with patch("src.internal_api._verify_webhook_request", return_value=True):
        # json() 호출 시 예외 유도
        req.json = AsyncMock(side_effect=RuntimeError("Sensitive DB password leaked in exception"))
        resp = await internal_api._internal_notify_handler(req)
        assert resp.status == 500
        assert resp.text == "Internal error"
        assert "Sensitive" not in resp.text


def test_webhook_ip_cidr_and_loopback():
    """S5: 웹훅 IP CIDR 대역 허용 및 loopback 차단 옵션 검증"""
    # 1. CIDR 대역 테스트
    allowed_ips = ["192.168.1.0/24", "10.0.0.1"]
    assert internal_api._is_ip_allowed("192.168.1.50", allowed_ips) is True
    assert internal_api._is_ip_allowed("192.168.2.1", allowed_ips) is False
    assert internal_api._is_ip_allowed("10.0.0.1", allowed_ips) is True
    assert internal_api._is_ip_allowed("10.0.0.2", allowed_ips) is False

    # 2. loopback 비허용 설정 검증
    with patch.dict(os.environ, {"ALLOWED_WEBHOOK_IPS": "", "WEBHOOK_ALLOW_LOOPBACK": "false"}):
        req = MagicMock()
        req.remote = "127.0.0.1"
        req.headers = {}
        loop = asyncio.new_event_loop()
        try:
            allowed = loop.run_until_complete(internal_api._verify_webhook_request(req))
            assert allowed is False
        finally:
            loop.close()


@pytest.mark.asyncio
async def test_realtime_broadcast_manager_robustness():
    """Q4: SSE 브로드캐스터 견고화 (큐 풀 드롭 및 연결 종료 시 discard)"""
    mgr = realtime_manager

    # 1. 구독 생성
    gen = mgr.subscribe()
    sub_task = asyncio.create_task(gen.__anext__())
    await asyncio.sleep(0.01)

    assert len(mgr.active_connections) >= 1

    # 2. 큐 초과 푸시 테스트 (maxsize=100 초과)
    for i in range(120):
        mgr.trigger(f"event-{i}")

    # 예외 없이 처리됨
    val = await sub_task
    assert "data:" in val

    # 3. 구독 취소 시 cleanup
    await gen.aclose()
    await asyncio.sleep(0.01)


def test_login_rate_limit():
    """Q5: 로그인 시도 Rate Limit (5분 내 10회 초과 시 429)"""
    client_ip = "127.0.0.99"
    email = "target@example.com"
    _reset_rate_limit(client_ip, email)

    # 10회 시도
    for _ in range(10):
        assert _is_rate_limited(client_ip, email) is False

    # 11번째는 한도 초과
    assert _is_rate_limited(client_ip, email) is True

    # 성공 시 리셋
    _reset_rate_limit(client_ip, email)
    assert _is_rate_limited(client_ip, email) is False
