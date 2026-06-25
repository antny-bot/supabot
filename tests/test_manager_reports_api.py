import asyncio
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from manager.backend.routers import reports as reports_router


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

    async def execute(self):
        rows = list(self.rows)

        user_filter = self._params.get("user_id")
        if user_filter and user_filter.startswith("eq."):
            user_id = user_filter[3:]
            rows = [r for r in rows if str(r.get("user_id")) == user_id]

        executed_at_filter = self._params.get("executed_at")
        if executed_at_filter and executed_at_filter.startswith("gte."):
            cutoff = float(executed_at_filter[4:])
            rows = [r for r in rows if float(r.get("executed_at", 0) or 0) >= cutoff]

        uuid_filter = self._params.get("uuid")
        if uuid_filter and uuid_filter.startswith("in.(") and uuid_filter.endswith(")"):
            allowed = set(uuid_filter[4:-1].split(","))
            rows = [r for r in rows if str(r.get("uuid")) in allowed]

        if self._params.get("order") == "executed_at.desc":
            rows.sort(key=lambda r: float(r.get("executed_at", 0) or 0), reverse=True)
        elif self._params.get("order") == "created_at.desc":
            rows.sort(key=lambda r: float(r.get("created_at", 0) or 0), reverse=True)

        limit = self._params.get("limit")
        if isinstance(limit, int):
            rows = rows[:limit]

        return _FakeResponse(rows, len(rows))


class _FakeTable:
    def __init__(self, table_name: str, rows: list[dict]):
        self.table_name = table_name
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return _FakeQuery(self.table_name, self.rows)


class _FakeDB:
    def __init__(self, trades: list[dict], orders: list[dict] | None = None):
        self.trades = trades
        self.orders = orders or []

    def table(self, name: str):
        if name == "trade_logs":
            return _FakeTable(name, self.trades)
        if name == "orders":
            return _FakeTable(name, self.orders)
        raise AssertionError(f"unexpected table: {name}")


def _trade(*, side: str, price: float, volume: float, executed_at: float, exchange="upbit", ticker="KRW-BTC",
           strategy="manual", fee_amount=0.0, uuid=None, user_id="user-1"):
    return {
        "user_id": user_id,
        "exchange": exchange,
        "ticker": ticker,
        "side": side,
        "price": price,
        "volume": volume,
        "strategy": strategy,
        "fee_amount": fee_amount,
        "executed_at": executed_at,
        "uuid": uuid,
    }


async def _fake_get_stock_name_map():
    return {}


def test_api_reports_pnl_buy_only_has_zero_realized_pnl(monkeypatch):
    trades = [
        _trade(side="bid", price=100.0, volume=2.0, executed_at=1_700_000_000.0),
    ]
    monkeypatch.setattr(reports_router, "get_db", lambda: _FakeDB(trades))
    monkeypatch.setattr(reports_router, "get_stock_name_map", _fake_get_stock_name_map)

    response = asyncio.run(reports_router.api_reports_pnl(_FakeRequest(), period="30d"))
    payload = json.loads(response.body)

    assert payload["summary"]["total_pnl"] == 0
    assert payload["summary"]["total_bid"] == 0
    assert payload["summary"]["total_ask"] == 0
    assert payload["rows"] == []


def test_api_reports_pnl_uses_average_cost_with_period_carry_over(monkeypatch):
    now_ts = 1_719_700_000.0
    trades = [
        _trade(side="bid", price=100.0, volume=1.0, executed_at=now_ts - 40 * 86400),
        _trade(side="bid", price=200.0, volume=1.0, executed_at=now_ts - 20 * 86400),
        _trade(side="ask", price=180.0, volume=1.0, executed_at=now_ts - 10 * 86400),
    ]
    monkeypatch.setattr(reports_router, "get_db", lambda: _FakeDB(trades))
    monkeypatch.setattr(reports_router, "get_stock_name_map", _fake_get_stock_name_map)
    monkeypatch.setattr(reports_router.time, "time", lambda: now_ts)

    response = asyncio.run(reports_router.api_reports_pnl(_FakeRequest(), period="30d"))
    payload = json.loads(response.body)

    assert payload["summary"]["total_bid"] == 150
    assert payload["summary"]["total_ask"] == 180
    assert payload["summary"]["total_pnl"] == 30
    assert payload["rows"] == [{
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "bid_krw": 150,
        "ask_krw": 180,
        "fee_amount": 0,
        "pnl": 30,
        "roi_pct": 20.0,
        "bid_count": 1,
        "ask_count": 1,
    }]


def test_api_reports_monthly_books_realized_pnl_in_sell_month(monkeypatch):
    trades = [
        _trade(side="bid", price=100.0, volume=1.0, executed_at=1_713_192_000.0),
        _trade(side="bid", price=200.0, volume=1.0, executed_at=1_717_848_000.0),
        _trade(side="ask", price=180.0, volume=1.0, executed_at=1_718_625_600.0),
    ]
    monkeypatch.setattr(reports_router, "get_db", lambda: _FakeDB(trades))

    response = asyncio.run(reports_router.api_reports_monthly(_FakeRequest()))
    payload = json.loads(response.body)

    assert payload["rows"] == [{
        "month": "2024-06",
        "bid_krw": 150,
        "ask_krw": 180,
        "fee_amount": 0,
        "pnl": 30,
        "bar_pct": 100,
    }]


def test_api_reports_holdings_returns_average_cost_and_valuation(monkeypatch):
    trades = [
        _trade(side="bid", price=100.0, volume=1.0, executed_at=1_700_000_000.0),
        _trade(side="bid", price=200.0, volume=1.0, executed_at=1_700_000_100.0),
        _trade(side="ask", price=180.0, volume=0.5, executed_at=1_700_000_200.0),
    ]
    monkeypatch.setattr(reports_router, "get_db", lambda: _FakeDB(trades))
    monkeypatch.setattr(reports_router, "get_stock_name_map", _fake_get_stock_name_map)

    async def fake_fetch_prices(positions, _bot_user_id):
        assert len(positions) == 1
        assert positions[0] == {"user_id": "user-1", "exchange": "upbit", "ticker": "KRW-BTC"}
        return {("user-1", "upbit", "KRW-BTC"): 190.0}

    monkeypatch.setattr(reports_router, "_fetch_current_prices", fake_fetch_prices)

    response = asyncio.run(reports_router.api_reports_holdings(_FakeRequest()))
    payload = json.loads(response.body)

    assert payload["summary"] == {
        "total_cost": 225,
        "total_value": 285,
        "total_pnl": 60,
        "total_roi_pct": 26.67,
        "asset_count": 1,
        "oversold_count": 0,
    }
    assert payload["rows"] == [{
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "quantity": 1.5,
        "avg_price": 150.0,
        "cost_krw": 225,
        "current_price": 190.0,
        "value_krw": 285,
        "pnl": 60,
        "roi_pct": 26.67,
        "oversold": False,
    }]


def test_api_reports_holdings_admin_aggregates_multi_user_prices(monkeypatch):
    trades = [
        _trade(side="bid", price=100.0, volume=1.0, executed_at=1_700_000_000.0, exchange="kis", ticker="005930", user_id="user-1"),
        _trade(side="bid", price=200.0, volume=2.0, executed_at=1_700_000_100.0, exchange="kis", ticker="005930", user_id="user-2"),
    ]
    monkeypatch.setattr(reports_router, "get_db", lambda: _FakeDB(trades))
    monkeypatch.setattr(reports_router, "get_stock_name_map", _fake_get_stock_name_map)

    async def fake_fetch_prices(positions, _bot_user_id):
        assert positions == [
            {"user_id": "user-1", "exchange": "kis", "ticker": "005930"},
            {"user_id": "user-2", "exchange": "kis", "ticker": "005930"},
        ]
        return {
            ("user-1", "kis", "005930"): 300.0,
            ("user-2", "kis", "005930"): 300.0,
        }

    monkeypatch.setattr(reports_router, "_fetch_current_prices", fake_fetch_prices)

    response = asyncio.run(reports_router.api_reports_holdings(_FakeRequest(is_admin=True)))
    payload = json.loads(response.body)

    assert payload["summary"] == {
        "total_cost": 500,
        "total_value": 900,
        "total_pnl": 400,
        "total_roi_pct": 80.0,
        "asset_count": 1,
        "oversold_count": 0,
    }
    assert payload["rows"] == [{
        "exchange": "kis",
        "ticker": "005930",
        "quantity": 3.0,
        "avg_price": 166.66666667,
        "cost_krw": 500,
        "current_price": 300.0,
        "value_krw": 900,
        "pnl": 400,
        "roi_pct": 80.0,
        "oversold": False,
    }]


def test_fetch_current_prices_uses_bot_webhook_for_toss_and_kis(monkeypatch):
    """KIS/Toss 보유분은 봇의 /internal/get_prices webhook(bot_client.get_prices)으로
    실시간가를 조회해야 한다 (해외주식 알파벳 티커 포함, 숫자 종목코드로 제한되지 않음)."""
    captured = {}

    def fake_get_prices(requests_):
        captured["requests"] = requests_
        return [
            {"user_id": "user-1", "exchange": "toss", "ticker": "005930", "price": 71000.0},
            {"user_id": "user-1", "exchange": "toss", "ticker": "AAPL", "price": 230.5},
            # kis 005930은 의도적으로 빠뜨려 FinanceDataReader 폴백을 유도한다.
        ]

    def fake_fdr_fallback(codes):
        captured["fallback_codes"] = set(codes)
        return {"005930": 70500.0}

    monkeypatch.setattr(reports_router.bot_client, "get_prices", fake_get_prices)
    monkeypatch.setattr(reports_router, "_fetch_kr_stock_prices_sync", fake_fdr_fallback)

    position_rows = [
        {"user_id": "user-1", "exchange": "toss", "ticker": "005930"},
        {"user_id": "user-1", "exchange": "toss", "ticker": "AAPL"},
        {"user_id": "user-1", "exchange": "kis", "ticker": "005930"},
    ]

    prices = asyncio.run(reports_router._fetch_current_prices(position_rows, "user-1"))

    assert {"user_id": "user-1", "exchange": "toss", "ticker": "005930"} in captured["requests"]
    assert {"user_id": "user-1", "exchange": "toss", "ticker": "AAPL"} in captured["requests"]
    assert {"user_id": "user-1", "exchange": "kis", "ticker": "005930"} in captured["requests"]

    # toss는 webhook이 가격을 반환했으므로 폴백 대상에서 빠지고, kis만 폴백된다.
    assert captured["fallback_codes"] == {"005930"}

    assert prices[("user-1", "toss", "005930")] == 71000.0
    assert prices[("user-1", "toss", "AAPL")] == 230.5
    assert prices[("user-1", "kis", "005930")] == 70500.0
