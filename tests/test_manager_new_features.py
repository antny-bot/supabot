import asyncio
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from manager.backend.routers import reports as reports_router
from manager.backend.routers import orders as orders_router


class _FakeRequest:
    def __init__(self, *, is_admin=False, bot_user_id="user-1"):
        self.session = {
            "user_email": "tester@example.com",
            "is_admin": is_admin,
            "bot_user_id": bot_user_id,
        }


class _FakeResponse:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class _FakeQuery:
    def __init__(self, table_name: str, rows: list[dict]):
        self.table_name = table_name
        self.rows = list(rows)
        self._params = {}

    def select(self, *_args, **_kwargs):
        return self

    def order(self, column: str, desc: bool = False):
        self._params["order"] = f"{column}.{'desc' if desc else 'asc'}"
        return self

    def limit(self, n: int):
        self._params["limit"] = n
        return self

    def in_(self, col, vals):
        self._params["in"] = vals
        return self

    def eq(self, col, val):
        self._params[col] = f"eq.{val}"
        return self

    async def execute(self):
        rows = list(self.rows)
        return _FakeResponse(data=rows, count=len(rows))


class _FakeDb:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = {name: list(rows) for name, rows in tables.items()}

    def table(self, name: str):
        return _FakeQuery(name, self.tables.get(name, []))


async def _fake_stock_map():
    return {}


def test_api_reports_drawdown(monkeypatch):
    trades = [
        {"user_id": "user-1", "exchange": "upbit", "ticker": "KRW-BTC", "side": "bid", "price": 1000, "volume": 1, "fee_amount": 1, "executed_at": 100},
        {"user_id": "user-1", "exchange": "upbit", "ticker": "KRW-BTC", "side": "ask", "price": 1200, "volume": 1, "fee_amount": 1, "executed_at": 200},
        {"user_id": "user-1", "exchange": "upbit", "ticker": "KRW-BTC", "side": "bid", "price": 1200, "volume": 1, "fee_amount": 1, "executed_at": 300},
        {"user_id": "user-1", "exchange": "upbit", "ticker": "KRW-BTC", "side": "ask", "price": 1100, "volume": 1, "fee_amount": 1, "executed_at": 400},
    ]
    db = _FakeDb({"trade_logs": trades})
    monkeypatch.setattr(reports_router, "get_db", lambda: db)
    monkeypatch.setattr(reports_router, "get_stock_name_map", _fake_stock_map)

    req = _FakeRequest(is_admin=True)
    res = asyncio.run(reports_router.api_reports_drawdown(req, period="all"))
    assert res.status_code == 200
    data = json.loads(res.body)
    assert "metrics" in data
    assert "series" in data
    assert data["metrics"]["win_count"] >= 1
    assert data["metrics"]["loss_count"] >= 1


def test_api_reports_allocation(monkeypatch):
    trades = [
        {"user_id": "user-1", "exchange": "upbit", "ticker": "KRW-BTC", "side": "bid", "price": 1000, "volume": 2, "fee_amount": 0, "executed_at": 100},
    ]
    db = _FakeDb({"trade_logs": trades})
    monkeypatch.setattr(reports_router, "get_db", lambda: db)
    monkeypatch.setattr(reports_router, "get_stock_name_map", _fake_stock_map)

    async def fake_fetch_prices(*_args, **_kwargs):
        return {("user-1", "upbit", "KRW-BTC"): 1500.0}

    monkeypatch.setattr(reports_router, "_fetch_current_prices", fake_fetch_prices)

    req = _FakeRequest(is_admin=False, bot_user_id="user-1")
    res = asyncio.run(reports_router.api_reports_allocation(req))
    assert res.status_code == 200
    data = json.loads(res.body)
    assert data["total_value"] == 3000
    assert len(data["by_exchange"]) >= 1
    assert len(data["by_category"]) >= 1


def test_api_cancel_all_orders(monkeypatch):
    orders = [
        {"uuid": "ord-1", "user_id": "user-1", "exchange": "upbit", "ticker": "KRW-BTC", "status": "wait"},
        {"uuid": "ord-2", "user_id": "user-1", "exchange": "upbit", "ticker": "KRW-ETH", "status": "partial"},
    ]
    db = _FakeDb({"orders": orders})
    monkeypatch.setattr(orders_router, "get_db", lambda: db)

    cancelled = []
    async def fake_cancel(user_id, exchange, uuid, ticker):
        cancelled.append(uuid)
        return True, None

    monkeypatch.setattr(orders_router.bot_client, "cancel_order", fake_cancel)

    user = {"is_admin": False, "bot_user_id": "user-1"}
    res = asyncio.run(orders_router.api_cancel_all_orders(user))
    assert res.status_code == 200
    data = json.loads(res.body)
    assert data["ok"] is True
    assert data["cancelled_count"] == 2
    assert cancelled == ["ord-1", "ord-2"]
