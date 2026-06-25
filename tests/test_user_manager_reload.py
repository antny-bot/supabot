import os
import sys
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.user_manager import UserManager


def _db_row(user_id, status="active", watchlist=None):
    return {
        "user_id": user_id,
        "username": f"user-{user_id}",
        "is_admin": False,
        "status": status,
        "preferences": dict(UserManager.DEFAULT_PREFERENCES),
        "exchanges": {"upbit": {"access_key": "", "secret_key": "", "watchlist": watchlist or []}},
        "llm": {"gemini_api_key": ""},
        "api_validation": {},
    }


def test_reload_from_db_replaces_in_memory_users(tmp_path, monkeypatch):
    """manager UI가 users 테이블을 직접 갱신해도, /dbsync(reload_from_db)가
    실행되면 봇 인메모리 상태(승인 여부·watchlist 등)가 즉시 DB와 일치해야 한다."""
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: False)
    manager = UserManager(str(tmp_path / "users.json"))
    manager.add_user("1", "alice", is_admin=False)
    assert manager.users["1"]["status"] == "pending"

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.execute.return_value.data = [
        _db_row("1", status="active", watchlist=["KRW-BTC"]),
    ]
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: True)
    monkeypatch.setattr("core.user_manager.get_db", lambda: fake_db)

    assert manager.reload_from_db() is True
    assert manager.users["1"]["status"] == "active"
    assert manager.users["1"]["exchanges"]["upbit"]["watchlist"] == ["KRW-BTC"]


def test_reload_from_db_is_noop_without_db(tmp_path, monkeypatch):
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: False)
    manager = UserManager(str(tmp_path / "users.json"))
    manager.add_user("1", "alice", is_admin=False)

    assert manager.reload_from_db() is False
    assert "1" in manager.users


def test_reload_from_db_returns_false_on_error(tmp_path, monkeypatch):
    manager = UserManager(str(tmp_path / "users.json"))
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: True)
    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.execute.side_effect = RuntimeError("boom")
    monkeypatch.setattr("core.user_manager.get_db", lambda: fake_db)

    assert manager.reload_from_db() is False
