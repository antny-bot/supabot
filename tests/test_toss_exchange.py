import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from core.exchange_adapter import ExchangeAdapter


class DummyUsers:
    def get_user(self, user_id):
        return {
            "exchanges": {
                "toss": {
                    "client_id": "c_test_client_id",
                    "client_secret": "s_test_secret",
                    "account_seq": 1,
                    "watchlist": [],
                }
            }
        }

    def update_toss_account_seq(self, user_id, account_seq):
        pass


def make_adapter():
    return ExchangeAdapter(DummyUsers())


# ── Token caching ──────────────────────────────────────────────────────────────

def test_toss_token_cached():
    adapter = make_adapter()
    import time

    token_responses = [
        {"access_token": "tok1", "token_type": "Bearer", "expires_in": 86400},
        {"access_token": "tok2", "token_type": "Bearer", "expires_in": 86400},
    ]
    call_count = [0]

    async def fake_post(*args, **kwargs):
        class FakeResp:
            async def json(self):
                idx = call_count[0]
                call_count[0] += 1
                return token_responses[idx] if idx < len(token_responses) else {}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

        return FakeResp()

    async def run():
        session = await adapter._get_toss_session()
        with patch.object(session, "post", side_effect=fake_post):
            keys = {"client_id": "c_test", "client_secret": "s_test", "account_seq": 1}
            t1 = await adapter._get_toss_token("u1", keys)
            t2 = await adapter._get_toss_token("u1", keys)
            return t1, t2, call_count[0]

    t1, t2, calls = asyncio.run(run())
    assert t1 == "tok1"
    assert t2 == "tok1"  # cached — no second call
    assert calls == 1


# ── get_ticker ─────────────────────────────────────────────────────────────────

def test_toss_get_ticker():
    adapter = make_adapter()

    FAKE_PRICE_RESPONSE = {
        "result": [
            {"symbol": "005930", "lastPrice": "72000", "currency": "KRW",
             "timestamp": "2026-06-18T09:30:00+09:00"}
        ]
    }

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        assert "prices" in path
        assert params == {"symbols": "005930"}
        return FAKE_PRICE_RESPONSE

    adapter._request_toss = fake_request_toss
    result = asyncio.run(adapter.get_ticker("toss", "005930", user_id="u1"))
    assert result is not None
    assert result["trade_price"] == 72000.0
    assert result["market"] == "005930"


# ── get_candles ────────────────────────────────────────────────────────────────

def test_toss_get_candles_day():
    adapter = make_adapter()

    FAKE_CANDLE_RESPONSE = {
        "result": {
            "candles": [
                {
                    "timestamp": "2026-06-18T09:00:00+09:00",
                    "openPrice": "71600",
                    "highPrice": "72300",
                    "lowPrice": "71500",
                    "closePrice": "72000",
                    "volume": "3521000",
                    "currency": "KRW",
                }
            ],
            "nextBefore": None,
        }
    }

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        assert "candles" in path
        assert params["interval"] == "1d"
        return FAKE_CANDLE_RESPONSE

    adapter._request_toss = fake_request_toss
    candles = asyncio.run(adapter.get_candles("toss", "005930", interval="day", count=1, user_id="u1"))
    assert candles is not None
    assert len(candles) == 1
    assert candles[0]["trade_price"] == 72000.0
    assert candles[0]["high_price"] == 72300.0


def test_toss_get_candles_minute():
    adapter = make_adapter()

    FAKE_CANDLE_RESPONSE = {
        "result": {
            "candles": [
                {
                    "timestamp": "2026-06-18T09:32:00+09:00",
                    "openPrice": "72000",
                    "highPrice": "72100",
                    "lowPrice": "71950",
                    "closePrice": "72050",
                    "volume": "15200",
                    "currency": "KRW",
                }
            ],
            "nextBefore": "2026-06-18T09:31:00+09:00",
        }
    }

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        assert params["interval"] == "1m"
        return FAKE_CANDLE_RESPONSE

    adapter._request_toss = fake_request_toss
    candles = asyncio.run(adapter.get_candles("toss", "005930", interval="1", count=1, user_id="u1"))
    assert candles is not None
    assert candles[0]["trade_price"] == 72050.0


# ── create_order ───────────────────────────────────────────────────────────────

def test_toss_create_order_buy():
    adapter = make_adapter()

    FAKE_ORDER_RESPONSE = {
        "result": {
            "orderId": "abc123",
            "clientOrderId": "my-order-001",
        }
    }

    calls = []

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        calls.append({"method": method, "path": path, "body": body})
        return FAKE_ORDER_RESPONSE

    adapter._request_toss = fake_request_toss
    result = asyncio.run(adapter.create_order("u1", "toss", "005930", "bid", 70000, 10))
    assert result is not None
    assert result["uuid"] == "abc123"
    assert calls[0]["body"]["side"] == "BUY"
    assert calls[0]["body"]["orderType"] == "LIMIT"
    assert calls[0]["body"]["price"] == "70000"


def test_toss_create_order_sell():
    adapter = make_adapter()

    FAKE_ORDER_RESPONSE = {
        "result": {"orderId": "xyz789"}
    }

    calls = []

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        calls.append(body)
        return FAKE_ORDER_RESPONSE

    adapter._request_toss = fake_request_toss
    result = asyncio.run(adapter.create_order("u1", "toss", "AAPL", "ask", 185.5, 5))
    assert result["uuid"] == "xyz789"
    assert calls[0]["side"] == "SELL"


# ── get_order_status ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("toss_status,expected_state,exec_qty,total_qty", [
    ("PENDING", "wait", 0, 10),
    ("PARTIAL_FILLED", "partial", 3, 10),
    ("FILLED", "done", 10, 10),
    ("CANCELED", "cancel", 0, 10),
    ("REJECTED", "cancel", 0, 5),
])
def test_toss_order_status_mapping(toss_status, expected_state, exec_qty, total_qty):
    adapter = make_adapter()

    FAKE_ORDER = {
        "result": {
            "orderId": "ord001",
            "symbol": "005930",
            "side": "BUY",
            "orderType": "LIMIT",
            "status": toss_status,
            "price": "70000",
            "quantity": str(total_qty),
            "currency": "KRW",
            "execution": {
                "filledQuantity": str(exec_qty),
                "commission": "0",
            },
        }
    }

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        return FAKE_ORDER

    adapter._request_toss = fake_request_toss
    result = asyncio.run(adapter.get_order_status("u1", "toss", "ord001"))
    assert result is not None
    assert result["state"] == expected_state
    assert result["executed_volume"] == exec_qty


# ── cancel_order ───────────────────────────────────────────────────────────────

def test_toss_cancel_order_success():
    adapter = make_adapter()

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        assert "cancel" in path
        assert method == "POST"
        return {"result": {"orderId": "ord001"}}

    adapter._request_toss = fake_request_toss
    ok = asyncio.run(adapter.cancel_order("u1", "toss", "ord001"))
    assert ok is True


def test_toss_cancel_order_fail():
    adapter = make_adapter()

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        return {"error": {"code": "already-filled"}}

    adapter._request_toss = fake_request_toss
    ok = asyncio.run(adapter.cancel_order("u1", "toss", "ord001"))
    assert ok is False


# ── parsers integration ────────────────────────────────────────────────────────

def test_normalize_exchange_toss():
    from core.parsers import normalize_exchange
    assert normalize_exchange("toss") == "toss"
    assert normalize_exchange("토스") == "toss"
    assert normalize_exchange("토스증권") == "toss"
    assert normalize_exchange("tossinvest") == "toss"
    assert normalize_exchange("TOSS") == "toss"


def test_exchange_display_name_toss():
    from core.parsers import exchange_display_name
    assert exchange_display_name("toss") == "토스증권"


def test_parse_exchange_and_ticker_toss():
    from core.parsers import parse_exchange_and_ticker
    exchange, ticker = parse_exchange_and_ticker(["toss", "005930"], "upbit")
    assert exchange == "toss"
    assert ticker == "005930"

    exchange, ticker = parse_exchange_and_ticker(["toss", "KRW-005930"], "upbit")
    assert ticker == "005930"

    exchange, ticker = parse_exchange_and_ticker(["toss", "AAPL"], "upbit")
    assert ticker == "AAPL"
