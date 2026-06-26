import asyncio
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.order_manager import OrderManager
import core.order_manager as om_mod


# flush_pending_writes는 진행 중인 fire-and-forget DB 쓰기 태스크가 모두 끝날 때까지 기다린다.
async def test_flush_pending_writes_awaits_inflight_tasks():
    om_mod._bg_tasks.clear()
    done = []

    async def slow_write():
        await asyncio.sleep(0.05)
        done.append(True)

    task = asyncio.create_task(slow_write())
    om_mod._track_task(task)

    await OrderManager.flush_pending_writes()

    assert task.done()
    assert done == [True]


# reload_from_db_async는 DB를 읽기 전에 반드시 flush_pending_writes를 먼저 호출한다 —
# 아직 DB에 닿지 않은 인메모리 변경이 stale read로 되돌려져 중복 처리되는 것을 막기 위함.
async def test_reload_flushes_pending_writes_before_fetch(tmp_path, monkeypatch):
    om = OrderManager(str(tmp_path / "orders.json"))
    calls = []

    monkeypatch.setattr(om_mod, "is_db_available", lambda: True)

    async def fake_flush():
        calls.append("flush")

    async def fake_fetch():
        calls.append("fetch")
        return []

    monkeypatch.setattr(OrderManager, "flush_pending_writes", staticmethod(fake_flush))
    monkeypatch.setattr(om, "_fetch_all_orders_async", fake_fetch)

    ok = await om.reload_from_db_async()

    assert ok is True
    assert calls == ["flush", "fetch"]
