"""Phase 8 중기: 환경변수 검증 + 헬스체크 테스트"""
import json
import os
import sys
import time
from unittest.mock import patch, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import main


# ── _validate_env ────────────────────────────────────────────────────────────

def test_validate_env_exits_when_bot_token_missing(monkeypatch):
    """TELEGRAM_BOT_TOKEN 누락 시 sys.exit(1) 호출."""
    monkeypatch.setattr(main, "BOT_TOKEN", "")
    monkeypatch.setattr(main, "ADMIN_CHAT_ID", "12345")
    monkeypatch.setenv("USER_SECRET_KEY", "somekey")
    with patch("main.can_decrypt_secrets", return_value=True), \
         patch("sys.exit") as mock_exit, \
         patch("builtins.print"):
        main._validate_env()
    mock_exit.assert_called_with(1)


def test_validate_env_exits_when_admin_chat_id_missing(monkeypatch):
    """ADMIN_CHAT_ID 누락 시 sys.exit(1) 호출."""
    monkeypatch.setattr(main, "BOT_TOKEN", "tok:en")
    monkeypatch.setattr(main, "ADMIN_CHAT_ID", "")
    monkeypatch.setenv("USER_SECRET_KEY", "somekey")
    with patch("main.can_decrypt_secrets", return_value=True), \
         patch("sys.exit") as mock_exit, \
         patch("builtins.print"):
        main._validate_env()
    mock_exit.assert_called_with(1)


def test_validate_env_exits_when_user_secret_key_missing(monkeypatch):
    """USER_SECRET_KEY 누락 시 sys.exit(1) 호출."""
    monkeypatch.setattr(main, "BOT_TOKEN", "tok:en")
    monkeypatch.setattr(main, "ADMIN_CHAT_ID", "12345")
    monkeypatch.delenv("USER_SECRET_KEY", raising=False)
    with patch("main.can_decrypt_secrets", return_value=True), \
         patch("sys.exit") as mock_exit, \
         patch("builtins.print"):
        main._validate_env()
    mock_exit.assert_called_with(1)


def test_validate_env_exits_when_secret_key_invalid(monkeypatch):
    """USER_SECRET_KEY가 Fernet 포맷이 아니면 sys.exit(1) 호출."""
    monkeypatch.setattr(main, "BOT_TOKEN", "tok:en")
    monkeypatch.setattr(main, "ADMIN_CHAT_ID", "12345")
    monkeypatch.setenv("USER_SECRET_KEY", "not-a-valid-fernet-key")
    with patch("main.can_decrypt_secrets", return_value=False), \
         patch("sys.exit") as mock_exit, \
         patch("builtins.print"):
        main._validate_env()
    mock_exit.assert_called_once_with(1)


def test_validate_env_passes_when_all_valid(monkeypatch):
    """모든 필수 환경변수가 존재하고 키가 유효하면 sys.exit 미호출."""
    monkeypatch.setattr(main, "BOT_TOKEN", "tok:en")
    monkeypatch.setattr(main, "ADMIN_CHAT_ID", "12345")
    monkeypatch.setenv("USER_SECRET_KEY", "validkey")
    with patch("main.can_decrypt_secrets", return_value=True), \
         patch("sys.exit") as mock_exit:
        main._validate_env()
    mock_exit.assert_not_called()


# ── _write_heartbeat ─────────────────────────────────────────────────────────

def test_write_heartbeat_creates_health_json(tmp_path, monkeypatch):
    """_write_heartbeat()가 data/health.json에 ts 필드를 기록."""
    monkeypatch.chdir(tmp_path)
    before = time.time()
    main._write_heartbeat()
    health_file = tmp_path / "data" / "health.json"
    assert health_file.exists()
    data = json.loads(health_file.read_text())
    assert "ts" in data
    assert data["ts"] >= before


def test_write_heartbeat_ts_is_recent(tmp_path, monkeypatch):
    """기록된 ts가 현재 시각 기준 1초 이내."""
    monkeypatch.chdir(tmp_path)
    main._write_heartbeat()
    data = json.loads((tmp_path / "data" / "health.json").read_text())
    assert time.time() - data["ts"] < 1.0


def test_write_heartbeat_does_not_raise_on_permission_error(monkeypatch):
    """파일 쓰기 실패 시 예외를 밖으로 던지지 않음."""
    with patch("builtins.open", side_effect=PermissionError):
        main._write_heartbeat()  # should not raise
