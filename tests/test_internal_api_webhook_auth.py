import os
import sys
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import internal_api


def _make_request(remote, headers=None):
    request = MagicMock()
    request.remote = remote
    request.headers = headers or {}
    return request


def _capture_warnings(monkeypatch):
    messages = []
    monkeypatch.setattr(internal_api._log, "warning", lambda msg, *a, **k: messages.append(msg))
    return messages


async def test_xff_spoofing_no_longer_bypasses_ip_whitelist(monkeypatch):
    """L2: 화이트리스트에 없는 실제 피어가 X-Forwarded-For를 위조해도 차단되어야 한다."""
    monkeypatch.setenv("ALLOWED_WEBHOOK_IPS", "10.0.0.5")
    monkeypatch.setenv("MANAGER_API_KEY", "secret")
    messages = _capture_warnings(monkeypatch)

    request = _make_request("203.0.113.1", headers={"X-Forwarded-For": "10.0.0.5"})

    assert await internal_api._verify_webhook_request(request) is False
    assert any("whitelist" in m for m in messages)


async def test_real_peer_in_whitelist_proceeds_past_ip_check(monkeypatch):
    """화이트리스트에 있는 실제 피어는 XFF 없이도 IP 검증을 통과해 HMAC 단계로 진행한다."""
    monkeypatch.setenv("ALLOWED_WEBHOOK_IPS", "10.0.0.5")
    monkeypatch.setenv("MANAGER_API_KEY", "secret")
    messages = _capture_warnings(monkeypatch)

    request = _make_request("10.0.0.5")

    assert await internal_api._verify_webhook_request(request) is False
    assert not any("whitelist" in m for m in messages)
    assert any("X-Timestamp" in m for m in messages)


async def test_loopback_peer_proceeds_past_ip_check_even_when_not_whitelisted(monkeypatch):
    monkeypatch.setenv("ALLOWED_WEBHOOK_IPS", "10.0.0.5")
    monkeypatch.setenv("MANAGER_API_KEY", "secret")
    messages = _capture_warnings(monkeypatch)

    request = _make_request("127.0.0.1")

    assert await internal_api._verify_webhook_request(request) is False
    assert not any("whitelist" in m for m in messages)
