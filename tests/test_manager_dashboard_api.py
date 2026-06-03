import asyncio
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from manager.backend.routers import dashboard as dashboard_router


class _FakeResponse:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class _FakeQuery:
    def __init__(self, table_name: str, db):
        self.table_name = table_name
        self.db = db
        self._params = {}

    def eq(self, column: str, value):
        self._params[column] = f"eq.{value}"
        return self

    def in_(self, column: str, values: list):
        self._params[column] = f"in.({','.join(values)})"
        return self

    def is_(self, column: str, value: str):
        self._params[column] = f"is.{value}"
        return self

    def order(self, column: str, desc: bool = False):
        self._params["order"] = f"{column}.{'desc' if desc else 'asc'}"
        return self

    def limit(self, n: int):
        self._params["limit"] = n
        return self

    async def execute(self):
        if self.table_name == "users" and self._params.get("user_id") == "eq.admin-1":
            return _FakeResponse([{"mfa_enabled": True}])
        if self.table_name == "users":
            if self._params.get("status") == "eq.active":
                return _FakeResponse(count=3)
            if self._params.get("status") == "eq.pending":
                return _FakeResponse(count=1)
            return _FakeResponse(count=4)
        if self.table_name == "orders":
            return _FakeResponse(count=2)
        if self.table_name == "trade_logs":
            return _FakeResponse(count=5)
        if self.table_name == "operational_events":
            if "select" in self._params or True:
                if "count" in self._params:
                    return _FakeResponse(count=1)
                return _FakeResponse([
                    {
                        "id": 7,
                        "level": "warning",
                        "source": "poller",
                        "message": "Unseen event",
                        "details": "",
                        "created_at": "2026-06-03T10:00:00+09:00",
                        "read_at": None,
                        "archived_at": None,
                    }
                ])
        return _FakeResponse()


class _FakeTable:
    def __init__(self, name: str, db):
        self.name = name
        self.db = db

    def select(self, columns="*", count=None):
        query = _FakeQuery(self.name, self.db)
        query._params["select"] = columns
        if count:
          query._params["count"] = count
        self.db.last_queries.append(query)
        return query


class _FakeDB:
    def __init__(self):
        self.last_queries = []

    def table(self, name: str):
        return _FakeTable(name, self)


def test_api_dashboard_returns_only_unread_unarchived_events(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(dashboard_router, "get_db", lambda: fake_db)

    response = asyncio.run(dashboard_router.api_dashboard({
        "email": "admin@example.com",
        "is_admin": True,
        "bot_user_id": "admin-1",
    }))

    assert response.status_code == 200
    event_query = next(q for q in fake_db.last_queries if q.table_name == "operational_events" and q._params["select"].startswith("id,level"))
    assert event_query._params["read_at"] == "is.null"
    assert event_query._params["archived_at"] == "is.null"
