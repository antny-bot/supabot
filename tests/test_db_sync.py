import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import pytest
import core.db_sync as db_sync


@pytest.fixture(autouse=True)
def restore_db_sync_queue():
    original_queue = list(db_sync._queue)
    yield
    db_sync._queue = original_queue


def _task(key_val):
    return {"action": "upsert", "table": "orders", "key_col": "uuid", "key_val": key_val, "data": {"uuid": key_val}}


class _UpsertCall:
    def __init__(self, key_val, fail_on):
        self._key_val = key_val
        self._fail_on = fail_on

    async def execute_async(self):
        if self._key_val in self._fail_on:
            raise RuntimeError(f"boom on {self._key_val}")
        return MagicMock()


def _make_fake_db(fail_on: set):
    """upsert가 fail_on에 담긴 key_val에 대해서만 예외를 던지는 가짜 Supabase 클라이언트."""
    fake_db = MagicMock()
    table = MagicMock()
    table.upsert.side_effect = lambda data: _UpsertCall(data["uuid"], fail_on)
    fake_db.table.return_value = table
    return fake_db


def _patched(fake_db):
    return (
        patch.object(db_sync, "is_db_available", lambda: True),
        patch.object(db_sync, "test_db_connection", AsyncMock(return_value=True)),
        patch.object(db_sync, "get_db", lambda: fake_db),
        patch.object(db_sync, "_save_queue", lambda: None),
    )


async def test_process_queue_keeps_untried_tasks_after_mid_queue_failure():
    """큐 [A, B, C, D]에서 B가 실패하면 A만 큐에서 빠지고 [B, C, D]는 남아야 한다.

    과거 버그: 성공 개수를 len(queue) - len(failed_tasks)로 계산해, break 이후
    시도조차 안 된 C가 큐에서 통째로 증발했다.
    """
    db_sync._queue = [_task("A"), _task("B"), _task("C"), _task("D")]
    fake_db = _make_fake_db(fail_on={"B"})

    with patch.object(db_sync, "is_db_available", lambda: True), \
         patch.object(db_sync, "test_db_connection", AsyncMock(return_value=True)), \
         patch.object(db_sync, "get_db", lambda: fake_db), \
         patch.object(db_sync, "_save_queue", lambda: None):
        await db_sync._process_queue()

    assert [t["key_val"] for t in db_sync._queue] == ["B", "C", "D"]


async def test_process_queue_clears_queue_when_all_succeed():
    db_sync._queue = [_task("A"), _task("B")]
    fake_db = _make_fake_db(fail_on=set())

    with patch.object(db_sync, "is_db_available", lambda: True), \
         patch.object(db_sync, "test_db_connection", AsyncMock(return_value=True)), \
         patch.object(db_sync, "get_db", lambda: fake_db), \
         patch.object(db_sync, "_save_queue", lambda: None):
        await db_sync._process_queue()

    assert db_sync._queue == []


async def test_process_queue_leaves_queue_untouched_when_first_task_fails():
    db_sync._queue = [_task("A"), _task("B")]
    fake_db = _make_fake_db(fail_on={"A"})

    with patch.object(db_sync, "is_db_available", lambda: True), \
         patch.object(db_sync, "test_db_connection", AsyncMock(return_value=True)), \
         patch.object(db_sync, "get_db", lambda: fake_db), \
         patch.object(db_sync, "_save_queue", lambda: None):
        await db_sync._process_queue()

    assert [t["key_val"] for t in db_sync._queue] == ["A", "B"]
