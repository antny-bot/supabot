import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import main
from handlers import system_handlers


def _make_update():
    update = MagicMock()
    update.effective_chat.id = 111
    update.message.reply_text = AsyncMock()
    return update


def _admin_user():
    return {"is_admin": True, "is_active": True}


def _patch_auth(monkeypatch, user):
    mock_um = MagicMock()
    mock_um.get_user = MagicMock(return_value=user)
    monkeypatch.setattr(main, "user_manager", mock_um)
    return mock_um


async def test_dbsync_reloads_orders_and_users(monkeypatch):
    mock_um = _patch_auth(monkeypatch, _admin_user())
    mock_um.reload_from_db = MagicMock(return_value=True)
    mock_um.users = {"1": {}, "2": {}}

    mock_om = MagicMock()
    mock_om.reload_from_db = MagicMock(return_value=True)
    mock_om.orders = [{"uuid": "a"}]
    monkeypatch.setattr(main, "order_manager", mock_om)

    update = _make_update()
    await system_handlers.dbsync_command(update, MagicMock())

    mock_om.reload_from_db.assert_called_once()
    mock_um.reload_from_db.assert_called_once()
    msg = update.message.reply_text.call_args.args[0]
    assert "주문 1건" in msg
    assert "유저 2명" in msg


async def test_dbsync_reports_partial_failure(monkeypatch):
    mock_um = _patch_auth(monkeypatch, _admin_user())
    mock_um.reload_from_db = MagicMock(return_value=False)
    mock_um.users = {}

    mock_om = MagicMock()
    mock_om.reload_from_db = MagicMock(return_value=True)
    mock_om.orders = []
    monkeypatch.setattr(main, "order_manager", mock_om)

    update = _make_update()
    await system_handlers.dbsync_command(update, MagicMock())

    msg = update.message.reply_text.call_args.args[0]
    assert "일부 실패" in msg
    assert "유저 동기화 실패" in msg


async def test_dbsync_blocks_non_admin(monkeypatch):
    _patch_auth(monkeypatch, {"is_admin": False, "is_active": True})
    mock_om = MagicMock()
    monkeypatch.setattr(main, "order_manager", mock_om)

    update = _make_update()
    await system_handlers.dbsync_command(update, MagicMock())

    mock_om.reload_from_db.assert_not_called()
    msg = update.message.reply_text.call_args.args[0]
    assert "어드민 전용" in msg
