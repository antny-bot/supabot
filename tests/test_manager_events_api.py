import asyncio
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from manager.backend.routers import events as events_router


class _FakeResponse:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _FakeQuery:
    def __init__(self, db, table_name: str, data=None, count=None, payload=None):
        self._db = db
        self._table_name = table_name
        self._params = {}
        self._data = data
        self._count = count
        self._payload = payload

    def eq(self, column: str, value):
        self._params[column] = f"eq.{value}"
        return self

    def order(self, column: str, desc: bool = False):
        self._params["order"] = f"{column}.{'desc' if desc else 'asc'}"
        return self

    def limit(self, n: int):
        self._params["limit"] = n
        return self

    async def execute(self):
        if self._payload is not None:
            event_id = int(str(self._params["id"]).split(".", 1)[1])
            row = self._db.rows[event_id]
            row.update(self._payload)
            return _FakeResponse([row])

        if "id" in self._params:
            event_id = int(str(self._params["id"]).split(".", 1)[1])
            row = self._db.rows.get(event_id)
            return _FakeResponse([row] if row else [])

        return _FakeResponse(self._data if self._data is not None else list(self._db.rows.values()), self._count)


class _FakeTable:
    def __init__(self, db, table_name: str):
        self._db = db
        self._table_name = table_name

    def select(self, *_args, **_kwargs):
        return _FakeQuery(self._db, self._table_name)

    def update(self, payload):
        return _FakeQuery(self._db, self._table_name, payload=payload)


class _FakeDB:
    def __init__(self):
        self.rows = {
            1: {
                "id": 1,
                "level": "warning",
                "source": "bot",
                "message": "Needs review",
                "details": "",
                "created_at": "2026-06-03T09:00:00+09:00",
                "read_at": None,
                "archived_at": None,
            }
        }

    def table(self, name: str):
        assert name == "operational_events"
        return _FakeTable(self, name)


def test_api_list_events_applies_unread_state_filter(monkeypatch):
    fake_db = _FakeDB()
    captured = {}

    class _CaptureTable(_FakeTable):
        def select(self, *_args, **_kwargs):
            query = super().select(*_args, **_kwargs)
            captured["query"] = query
            return query

    monkeypatch.setattr(events_router, "get_db", lambda: type("DB", (), {"table": lambda _self, name: _CaptureTable(fake_db, name)})())

    response = asyncio.run(events_router.api_list_events(level="warning", state="unread", _={}))

    assert response.status_code == 200
    assert captured["query"]._params["level"] == "eq.warning"
    assert captured["query"]._params["read_at"] == "is.null"
    assert captured["query"]._params["archived_at"] == "is.null"


def test_api_mark_event_read_updates_timestamp(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(events_router, "get_db", lambda: fake_db)

    response = asyncio.run(events_router.api_mark_event_read(1, _={}))

    assert response.status_code == 200
    assert fake_db.rows[1]["read_at"] is not None


def test_api_archive_event_marks_event_read_and_archived(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(events_router, "get_db", lambda: fake_db)

    response = asyncio.run(events_router.api_archive_event(1, _={}))

    assert response.status_code == 200
    assert fake_db.rows[1]["read_at"] is not None
    assert fake_db.rows[1]["archived_at"] is not None
