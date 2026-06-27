import os
import sys
from unittest.mock import AsyncMock, MagicMock

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


def test_refresh_user_updates_single_user_in_place(tmp_path, monkeypatch):
    """manager가 승인 처리한 직후, /start나 /internal/notify가 reload_from_db()
    전체 테이블 스캔 없이도 해당 유저 한 명만 가볍게 동기화할 수 있어야 한다."""
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: False)
    manager = UserManager(str(tmp_path / "users.json"))
    manager.add_user("1", "alice", is_admin=False)
    assert manager.users["1"]["status"] == "pending"

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        _db_row("1", status="active", watchlist=["KRW-BTC"]),
    ]
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: True)
    monkeypatch.setattr("core.user_manager.get_db", lambda: fake_db)

    assert manager.refresh_user("1") is True
    assert manager.users["1"]["status"] == "active"
    assert manager.users["1"]["exchanges"]["upbit"]["watchlist"] == ["KRW-BTC"]


def test_refresh_user_is_noop_without_db(tmp_path, monkeypatch):
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: False)
    manager = UserManager(str(tmp_path / "users.json"))
    manager.add_user("1", "alice", is_admin=False)

    assert manager.refresh_user("1") is False


def test_refresh_user_returns_false_when_row_missing(tmp_path, monkeypatch):
    manager = UserManager(str(tmp_path / "users.json"))
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: True)
    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    monkeypatch.setattr("core.user_manager.get_db", lambda: fake_db)

    assert manager.refresh_user("999") is False


def test_refresh_user_returns_false_on_error(tmp_path, monkeypatch):
    manager = UserManager(str(tmp_path / "users.json"))
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: True)
    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = RuntimeError("boom")
    monkeypatch.setattr("core.user_manager.get_db", lambda: fake_db)

    assert manager.refresh_user("1") is False


# M5: order_sync_loop/signal_analysis_loop가 매 사이클 호출하는 비동기 reload —
# manager UI의 차단/비활성화가 /start·/dbsync 없이도 다음 폴링 사이클에 반영되어야 한다.
async def test_reload_from_db_async_replaces_in_memory_users(tmp_path, monkeypatch):
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: False)
    manager = UserManager(str(tmp_path / "users.json"))
    manager.add_user("1", "alice", is_admin=False)
    assert manager.users["1"]["status"] == "pending"

    fake_response = MagicMock()
    fake_response.data = [_db_row("1", status="active", watchlist=["KRW-BTC"])]
    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.execute_async = AsyncMock(return_value=fake_response)
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: True)
    monkeypatch.setattr("core.user_manager.get_db", lambda: fake_db)

    assert await manager.reload_from_db_async() is True
    assert manager.users["1"]["status"] == "active"
    assert manager.users["1"]["exchanges"]["upbit"]["watchlist"] == ["KRW-BTC"]


async def test_reload_from_db_async_is_noop_without_db(tmp_path, monkeypatch):
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: False)
    manager = UserManager(str(tmp_path / "users.json"))
    manager.add_user("1", "alice", is_admin=False)

    assert await manager.reload_from_db_async() is False
    assert "1" in manager.users


async def test_reload_from_db_async_returns_false_on_error(tmp_path, monkeypatch):
    manager = UserManager(str(tmp_path / "users.json"))
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: True)
    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.execute_async = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr("core.user_manager.get_db", lambda: fake_db)

    assert await manager.reload_from_db_async() is False


# L4: get_user()가 읽기 시 기본값을 보정하며 매번 DB 업서트를 유발하던 문제 —
# 보정은 DB 행이 메모리로 들어오는 reload/refresh 시점에 1회만 일어나야 한다.
def test_reload_from_db_backfills_missing_preference_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: False)
    manager = UserManager(str(tmp_path / "users.json"))

    incomplete_prefs = dict(UserManager.DEFAULT_PREFERENCES)
    del incomplete_prefs["stop_loss_pct"]
    row = _db_row("1", status="active")
    row["preferences"] = incomplete_prefs

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.execute.return_value.data = [row]
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: True)
    monkeypatch.setattr("core.user_manager.get_db", lambda: fake_db)

    assert manager.reload_from_db() is True
    assert manager.users["1"]["preferences"]["stop_loss_pct"] == UserManager.DEFAULT_PREFERENCES["stop_loss_pct"]


def test_refresh_user_backfills_missing_preference_defaults(tmp_path, monkeypatch):
    manager = UserManager(str(tmp_path / "users.json"))

    incomplete_prefs = dict(UserManager.DEFAULT_PREFERENCES)
    del incomplete_prefs["max_open_exposure_krw"]
    row = _db_row("1", status="active")
    row["preferences"] = incomplete_prefs

    fake_db = MagicMock()
    fake_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [row]
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: True)
    monkeypatch.setattr("core.user_manager.get_db", lambda: fake_db)

    assert manager.refresh_user("1") is True
    assert manager.users["1"]["preferences"]["max_open_exposure_krw"] == UserManager.DEFAULT_PREFERENCES["max_open_exposure_krw"]


def test_get_user_does_not_trigger_db_upsert(tmp_path, monkeypatch):
    """get_user()는 순수 읽기여야 한다 — 기본값 보정으로 인한 쓰기 증폭 금지(L4)."""
    monkeypatch.setattr("core.user_manager.is_db_available", lambda: False)
    manager = UserManager(str(tmp_path / "users.json"))
    manager.add_user("1", "alice", is_admin=False)

    mock_upsert = MagicMock()
    monkeypatch.setattr(manager, "_upsert_user", mock_upsert)

    for _ in range(5):
        manager.get_user("1")

    mock_upsert.assert_not_called()
