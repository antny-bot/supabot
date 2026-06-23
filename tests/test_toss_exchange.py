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

    class FakeResp:
        async def json(self):
            idx = call_count[0]
            call_count[0] += 1
            return token_responses[idx] if idx < len(token_responses) else {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    def fake_post(*args, **kwargs):
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
    FAKE_CANDLE_RESPONSE = {
        "result": {
            "candles": [
                {"timestamp": "2026-06-18T09:00:00+09:00", "openPrice": "71600", "highPrice": "72300",
                 "lowPrice": "71500", "closePrice": "72000", "volume": "3521000", "currency": "KRW"},
                {"timestamp": "2026-06-17T09:00:00+09:00", "openPrice": "71200", "highPrice": "71800",
                 "lowPrice": "71000", "closePrice": "71600", "volume": "2984000", "currency": "KRW"},
            ],
            "nextBefore": "2026-06-17T09:00:00+09:00",
        }
    }

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        if "prices" in path:
            assert params == {"symbols": "005930"}
            return FAKE_PRICE_RESPONSE
        assert "candles" in path
        return FAKE_CANDLE_RESPONSE

    adapter._request_toss = fake_request_toss
    result = asyncio.run(adapter.get_ticker("toss", "005930", user_id="u1"))
    assert result is not None
    assert result["trade_price"] == 72000.0
    assert result["market"] == "005930"
    assert result["high_price"] == 72300.0
    assert result["low_price"] == 71500.0
    assert result["acc_trade_price_24h"] == 72000.0 * 3521000
    assert result["change_price"] == 72000.0 - 71600.0
    assert result["change_rate"] == (72000.0 - 71600.0) / 71600.0


def test_toss_get_ticker_retries_once_on_empty_price_then_succeeds():
    adapter = make_adapter()

    FAKE_PRICE_RESPONSE = {
        "result": [
            {"symbol": "089970", "lastPrice": "100500", "currency": "KRW",
             "timestamp": "2026-06-22T09:30:00+09:00"}
        ]
    }
    FAKE_CANDLE_RESPONSE = {"result": {"candles": [], "nextBefore": None}}

    price_calls = [{"result": []}, FAKE_PRICE_RESPONSE]

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        if "prices" in path:
            return price_calls.pop(0)
        return FAKE_CANDLE_RESPONSE

    adapter._request_toss = fake_request_toss
    with patch("core.exchanges.toss.asyncio.sleep", new=AsyncMock()):
        result = asyncio.run(adapter.get_ticker("toss", "089970", user_id="u1"))

    assert result is not None
    assert result["trade_price"] == 100500.0
    assert price_calls == []  # 두 번 호출되어 큐가 비어야 함


def test_toss_get_ticker_returns_none_when_both_attempts_empty():
    adapter = make_adapter()

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        if "prices" in path:
            return {"result": []}
        return {"result": {"candles": []}}

    adapter._request_toss = fake_request_toss
    with patch("core.exchanges.toss.asyncio.sleep", new=AsyncMock()):
        result = asyncio.run(adapter.get_ticker("toss", "089970", user_id="u1"))

    assert result is None


def test_toss_get_ticker_returns_none_immediately_on_api_error_no_retry():
    adapter = make_adapter()
    call_count = [0]

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        if "prices" in path:
            call_count[0] += 1
            return {"error": {"code": "SYMBOL_NOT_FOUND", "message": "unsupported symbol"}}
        return {"result": {"candles": []}}

    adapter._request_toss = fake_request_toss
    with patch("core.exchanges.toss.asyncio.sleep", new=AsyncMock()) as fake_sleep:
        result = asyncio.run(adapter.get_ticker("toss", "000250", user_id="u1"))

    assert result is None
    assert call_count[0] == 1  # 에러 응답은 재시도하지 않음
    fake_sleep.assert_not_called()


def test_toss_get_ticker_returns_none_immediately_when_no_credentials():
    adapter = make_adapter()
    call_count = [0]

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        call_count[0] += 1
        return None  # _get_client/token 실패 시 _request_toss가 None 반환

    adapter._request_toss = fake_request_toss
    with patch("core.exchanges.toss.asyncio.sleep", new=AsyncMock()) as fake_sleep:
        result = asyncio.run(adapter.get_ticker("toss", "000250", user_id="u1"))

    assert result is None
    assert call_count[0] == 1
    fake_sleep.assert_not_called()


def test_request_toss_logs_error_response():
    adapter = make_adapter()

    class FakeResp:
        async def json(self):
            return {"error": {"code": "RATE_LIMIT", "message": "too many requests"}}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResp()

        @property
        def closed(self):
            return False

    async def run():
        adapter._toss_session = FakeSession()
        adapter._get_toss_token = AsyncMock(return_value="tok")
        return await adapter._request_toss("u1", "GET", "/api/v1/prices", params={"symbols": "000250"}, need_account=False)

    from core.exchanges import toss as toss_module
    with patch.object(toss_module._log, "error") as fake_error:
        result = asyncio.run(run())

    assert result == {"error": {"code": "RATE_LIMIT", "message": "too many requests"}}
    fake_error.assert_called_once()
    assert fake_error.call_args[0][0] == "Toss API error response"
    assert fake_error.call_args[1]["extra"]["code"] == "RATE_LIMIT"


def test_toss_get_ticker_us_stock_volume_is_share_count():
    adapter = make_adapter()

    FAKE_PRICE_RESPONSE = {
        "result": [
            {"symbol": "AAPL", "lastPrice": "185.70", "currency": "USD",
             "timestamp": "2026-06-18T22:30:00+09:00"}
        ]
    }
    FAKE_CANDLE_RESPONSE = {
        "result": {
            "candles": [
                {"timestamp": "2026-06-18T09:00:00+09:00", "openPrice": "184.00", "highPrice": "186.00",
                 "lowPrice": "183.50", "closePrice": "185.70", "volume": "1200000", "currency": "USD"},
            ],
            "nextBefore": None,
        }
    }

    async def fake_request_toss(user_id, method, path, params=None, body=None, need_account=True):
        if "prices" in path:
            return FAKE_PRICE_RESPONSE
        return FAKE_CANDLE_RESPONSE

    adapter._request_toss = fake_request_toss
    result = asyncio.run(adapter.get_ticker("toss", "AAPL", user_id="u1"))
    assert result is not None
    assert result["high_price"] == 186.0
    assert result["low_price"] == 183.5
    assert result["acc_trade_price_24h"] == 1200000.0


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


# ── KRX tick size (KIS/Toss) ───────────────────────────────────────────────────

@pytest.mark.parametrize("price,expected_tick", [
    (1500, 1),
    (3000, 5),
    (10000, 10),
    (35000, 50),
    (100000, 100),
    (300000, 500),
    (1000000, 1000),
])
def test_get_krx_tick_size(price, expected_tick):
    assert ExchangeAdapter.get_krx_tick_size(price) == expected_tick


def test_adjust_krx_price_to_tick_rounds_down_to_valid_tick():
    # 35,000~50,000원대는 50원 단위 -> 35,037 -> 35,000
    assert ExchangeAdapter.adjust_krx_price_to_tick(35_037) == 35_000
    # 크립토(업비트) 호가 단위(10원)로는 35,030이 되지만 KRX는 50원 단위이므로 달라야 함
    assert ExchangeAdapter.adjust_price_to_tick(35_037) != ExchangeAdapter.adjust_krx_price_to_tick(35_037)


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
