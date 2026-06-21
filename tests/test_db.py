import os
import sys
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core import db as db_module


def _fake_session(json_data=None, content_range=None):
    session = MagicMock()
    resp = MagicMock()
    resp.ok = True
    resp.text = "[]" if json_data is None else "non-empty"
    resp.json.return_value = json_data if json_data is not None else []
    resp.headers = {"content-range": content_range} if content_range else {}
    session.request.return_value = resp
    return session, resp


def test_select_returns_filtered_query_with_eq():
    session, resp = _fake_session(json_data=[{"name": "삼성전자", "code": "005930"}])
    table = db_module._Table(session, "https://x.test/rest/v1/kr_stock_cache")

    query = table.select("name,code")
    assert isinstance(query, db_module._FilteredQuery)

    query = query.eq("name", "삼성전자")
    result = query.execute()

    assert result.data == [{"name": "삼성전자", "code": "005930"}]
    called_kwargs = session.request.call_args
    assert called_kwargs.kwargs["params"] == {"select": "name,code", "name": "eq.삼성전자"}


def test_select_chain_supports_in_and_limit():
    session, resp = _fake_session(json_data=[])
    table = db_module._Table(session, "https://x.test/rest/v1/system_config")

    table.select("key,value").in_("key", ["a", "b"]).execute()
    params = session.request.call_args.kwargs["params"]
    assert params == {"select": "key,value", "key": "in.(a,b)"}

    table.select("key").limit(1).execute()
    params = session.request.call_args.kwargs["params"]
    assert params == {"select": "key", "limit": "1"}


def test_range_sets_pagination_headers():
    session, resp = _fake_session(json_data=[])
    table = db_module._Table(session, "https://x.test/rest/v1/orders")

    table.select("*").range(0, 999).execute()
    headers = session.request.call_args.kwargs["headers"]
    assert headers["Range"] == "0-999"
    assert headers["Range-Unit"] == "items"


def test_fetch_all_orders_paginates_beyond_page_size(monkeypatch):
    """주문이 1000건을 넘으면 여러 페이지로 나눠 모두 읽어와야 한다."""
    from core.order_manager import OrderManager, _DB_PAGE_SIZE

    page1 = [{"uuid": f"a{i}"} for i in range(_DB_PAGE_SIZE)]   # 가득 찬 첫 페이지
    page2 = [{"uuid": f"b{i}"} for i in range(5)]               # 마지막 페이지(부분)
    pages = [page1, page2]
    captured_ranges = []

    class _FakeQuery:
        def select(self, *a, **k):
            return self

        def range(self, start, end):
            captured_ranges.append((start, end))
            return self

        def execute(self):
            return db_module._APIResponse(data=pages[len(captured_ranges) - 1])

    fake_db = MagicMock()
    fake_db.table.return_value = _FakeQuery()
    monkeypatch.setattr("core.order_manager.get_db", lambda: fake_db)

    rows = OrderManager._fetch_all_orders()

    assert len(rows) == _DB_PAGE_SIZE + 5
    assert captured_ranges == [(0, _DB_PAGE_SIZE - 1), (_DB_PAGE_SIZE, 2 * _DB_PAGE_SIZE - 1)]
