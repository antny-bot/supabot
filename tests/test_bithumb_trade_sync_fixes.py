import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


@pytest.mark.asyncio
async def test_bithumb_get_order_status_returns_none_on_error_response():
    from core.exchanges.bithumb import BithumbExchange
    from core.exchanges.common import CommonMixin

    adapter = MagicMock()
    adapter._is_error_response = CommonMixin._is_error_response
    adapter._normalize_order_state = CommonMixin._normalize_order_state
    adapter._request_bithumb = AsyncMock(return_value={
        "error": {"name": "order_not_found", "message": "주문을 찾지 못했습니다."}
    })

    ex = BithumbExchange(adapter)
    res = await ex.get_order_status("user1", {"access_key": "a", "secret_key": "b"}, "uuid-err")
    assert res is None


@pytest.mark.asyncio
async def test_bithumb_get_order_status_handles_none_volumes():
    from core.exchanges.bithumb import BithumbExchange
    from core.exchanges.common import CommonMixin

    adapter = MagicMock()
    adapter._is_error_response = CommonMixin._is_error_response
    adapter._normalize_order_state = CommonMixin._normalize_order_state
    adapter._request_bithumb = AsyncMock(return_value={
        "state": "done",
        "market": "KRW-BTC",
        "side": "bid",
        "executed_volume": None,
        "volume": None,
        "paid_fee": None,
    })

    ex = BithumbExchange(adapter)
    res = await ex.get_order_status("user1", {"access_key": "a", "secret_key": "b"}, "uuid-ok")
    assert res is not None
    assert res["state"] == "done"
    assert res["executed_volume"] == 0.0
    assert res["remaining_volume"] == 0.0
    assert res["fee_amount"] == 0.0


@pytest.mark.asyncio
async def test_append_trade_enqueues_db_sync_on_db_failure(tmp_path, monkeypatch):
    from core.trade_log import append_trade

    monkeypatch.setattr("core.trade_log.is_db_available", lambda: True)

    class FailingTable:
        def insert(self, data):
            return self
        def execute(self):
            raise RuntimeError("Supabase 503")

    fake_db = MagicMock()
    fake_db.table.return_value = FailingTable()
    monkeypatch.setattr("core.trade_log.get_db", lambda: fake_db)

    enqueued = []

    async def fake_enqueue(action, table, key_col, key_val, data=None):
        enqueued.append((action, table, key_col, key_val, data))

    monkeypatch.setattr("core.db_sync.enqueue_task", fake_enqueue)

    path = str(tmp_path / "trades.jsonl")
    append_trade(
        user_id="5438389996",
        exchange="bithumb",
        ticker="KRW-BTC",
        side="bid",
        price=99399000.0,
        volume=0.001,
        strategy="manual",
        uuid="uuid-fail-1",
        fee_amount=248.49,
        path=path,
    )
    await asyncio.sleep(0)

    assert len(enqueued) == 1
    action, table, key_col, key_val, data = enqueued[0]
    assert action == "insert"
    assert table == "trade_logs"
    assert key_col == "uuid"
    assert key_val == "uuid-fail-1"
    assert data["price"] == 99399000.0
    assert data["fee_amount"] == 248.49


@pytest.mark.asyncio
async def test_db_sync_process_queue_insert_skips_if_uuid_exists(monkeypatch):
    from core import db_sync

    inserted = []

    class FakeQuery:
        def __init__(self, op, table, data=None):
            self.op = op
            self.table = table
            self.data = data
            self.uuid_filter = None

        def eq(self, col, val):
            self.uuid_filter = val
            return self

        async def execute_async(self):
            if self.op == "select":
                if self.uuid_filter == "uuid-exists":
                    return type("R", (), {"data": [{"id": 99}]})()
                return type("R", (), {"data": []})()
            if self.op == "insert":
                inserted.append(self.data)
                return type("R", (), {"data": [self.data]})()
            return type("R", (), {"data": []})()

    class FakeTable:
        def __init__(self, name):
            self.name = name
        def select(self, *a, **k):
            return FakeQuery("select", self.name)
        def insert(self, data):
            return FakeQuery("insert", self.name, data=data)

    fake_db = MagicMock()
    fake_db.table.side_effect = lambda name: FakeTable(name)

    monkeypatch.setattr(db_sync, "test_db_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(db_sync, "get_db", lambda: fake_db)
    monkeypatch.setattr(db_sync, "_save_queue", lambda: None)

    db_sync._queue = [
        {
            "action": "insert",
            "table": "trade_logs",
            "key_col": "uuid",
            "key_val": "uuid-exists",
            "data": {"uuid": "uuid-exists", "price": 100.0},
        },
        {
            "action": "insert",
            "table": "trade_logs",
            "key_col": "uuid",
            "key_val": "uuid-new",
            "data": {"uuid": "uuid-new", "price": 200.0},
        },
    ]

    await db_sync._process_queue()
    assert len(db_sync._queue) == 0
    assert len(inserted) == 1
    assert inserted[0]["uuid"] == "uuid-new"


@pytest.mark.asyncio
async def test_order_sync_process_order_fill_logs_partial_fill_on_cancel(monkeypatch):
    from core import order_sync

    fake_om = MagicMock()
    fake_om.orders = []
    monkeypatch.setattr(order_sync, "_get_app_context", lambda: (fake_om, MagicMock(), MagicMock(), MagicMock()))
    monkeypatch.setattr(order_sync, "_refund_unfilled_budget", AsyncMock())

    logged = []
    monkeypatch.setattr(order_sync, "_call_append_trade", lambda **kw: logged.append(kw))

    app = MagicMock()
    app.bot.send_message = AsyncMock()

    ex_obj = MagicMock()
    ex_obj.supports_reserved_orders = False

    ord_dict = {
        "uuid": "C0101000009999999999",
        "user_id": "5438389996",
        "exchange": "bithumb",
        "ticker": "KRW-BTC",
        "side": "bid",
        "price": 99399000.0,
        "volume": 0.002,
        "filled_volume": 0.0,
        "strategy": "manual",
        "status": "wait",
    }
    res = {
        "state": "cancel",
        "executed_volume": 0.001,
        "fee_amount": 248.49,
    }

    await order_sync._process_order_fill(app, ord_dict, res, ex_obj)

    assert len(logged) == 1
    assert logged[0]["uuid"] == "C0101000009999999999"
    assert logged[0]["volume"] == 0.001
    assert logged[0]["fee_amount"] == 248.49
    fake_om.remove_order.assert_called_once_with("C0101000009999999999")
