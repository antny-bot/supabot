import asyncio
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from manager.backend.routers import orders as orders_router


class _FakeResponse:
    def __init__(self, data, count):
        self.data = data
        self.count = count


class _FakeQuery:
    def __init__(self, data, count):
        self._params = {}
        self._data = data
        self._count = count

    def order(self, column: str, desc: bool = False):
        self._params["order"] = f"{column}.{'desc' if desc else 'asc'}"
        return self

    async def execute(self):
        return _FakeResponse(self._data, self._count)


class _FakeTable:
    def __init__(self, query):
        self._query = query

    def select(self, *_args, **_kwargs):
        return self._query


class _FakeDB:
    def __init__(self, query):
        self.query = query

    def table(self, name: str):
        assert name == "orders"
        return _FakeTable(self.query)


def test_api_list_orders_adds_order_value_and_formats(monkeypatch):
    query = _FakeQuery(
        [
            {
                "user_id": "1",
                "exchange": "upbit",
                "ticker": "KRW-BTC",
                "side": "bid",
                "strategy": "manual",
                "price": 50000000,
                "volume": 0.001,
                "filled_volume": 0.0,
                "status": "wait",
                "created_at": 1710000000,
            }
        ],
        1,
    )
    monkeypatch.setattr(orders_router, "get_db", lambda: _FakeDB(query))

    response = asyncio.run(
        orders_router.api_list_orders(
            status="open",
            exchange="upbit",
            page=2,
            page_size=10,
            user={"is_admin": False, "bot_user_id": "1"},
        )
    )

    payload = json.loads(response.body)
    order = payload["orders"][0]

    assert payload["total"] == 1
    assert order["order_value"] == 50000.0
    assert order["status_label"] == orders_router._STATUS_LABELS["wait"]
    assert order["fill_pct"] == 0
    assert order["created_fmt"] == orders_router._fmt_ts(1710000000)
    assert query._params["status"] == "in.(wait,partial,pending_reorder)"
    assert query._params["exchange"] == "eq.upbit"
    assert query._params["user_id"] == "eq.1"
    assert query._params["limit"] == 10
    assert query._params["offset"] == 10


def test_api_list_orders_handles_missing_price_and_volume(monkeypatch):
    query = _FakeQuery(
        [
            {
                "user_id": "1",
                "exchange": "kis",
                "ticker": "005930",
                "side": "ask",
                "strategy": "manual",
                "price": None,
                "volume": None,
                "filled_volume": None,
                "status": "done",
                "created_at": None,
            }
        ],
        1,
    )
    monkeypatch.setattr(orders_router, "get_db", lambda: _FakeDB(query))

    response = asyncio.run(
        orders_router.api_list_orders(
            page=1,
            page_size=50,
            user={"is_admin": True, "bot_user_id": None},
        )
    )

    payload = json.loads(response.body)
    order = payload["orders"][0]

    assert order["order_value"] == 0.0
    assert order["fill_pct"] == 0
    assert order["created_fmt"] == "—"
