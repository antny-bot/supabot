import os
import sys
import asyncio

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.exchange_adapter import ExchangeAdapter


class DummyUsers:
    def get_user(self, user_id):
        return {
            "exchanges": {
                "kis": {
                    "app_key": "app",
                    "app_secret": "secret",
                    "account_no": "12345678",
                    "product_code": "01",
                    "env": "paper",
                }
            }
        }


def test_upbit_day_uses_day_candles():
    adapter = ExchangeAdapter(DummyUsers())
    calls = []

    async def fake_cli(resource, command, args=None, keys=None):
        calls.append((resource, command, args))
        return []

    adapter._run_upbit_cli = fake_cli
    asyncio.run(adapter.get_candles("upbit", "KRW-BTC", interval="day", count=20))

    assert calls == [("candles", "list-days", ["--market", "KRW-BTC", "--count", "20"])]


def test_bithumb_day_uses_day_candles():
    adapter = ExchangeAdapter(DummyUsers())
    calls = []

    async def fake_request(method, path, keys=None, params=None, body=None):
        calls.append((method, path, params))
        return []

    adapter._request_bithumb = fake_request
    asyncio.run(adapter.get_candles("bithumb", "KRW-BTC", interval="day", count=20))

    assert calls == [("GET", "/v1/candles/days", {"market": "KRW-BTC", "count": "20"})]


def test_kis_day_candles_are_normalized():
    adapter = ExchangeAdapter(DummyUsers())

    async def fake_request(user_id, method, path, tr_id, params=None, body=None):
        assert path == "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        assert tr_id == "FHKST03010100"
        return {
            "output2": [
                {
                    "stck_bsop_date": "20260529",
                    "stck_clpr": "70000",
                    "stck_oprc": "69000",
                    "stck_hgpr": "71000",
                    "stck_lwpr": "68000",
                }
            ]
        }

    adapter._request_kis = fake_request
    candles = asyncio.run(adapter.get_candles("kis", "005930", interval="day", count=1, user_id="1"))

    assert candles == [
        {
            "candle_date_time_kst": "20260529",
            "trade_price": 70000.0,
            "opening_price": 69000.0,
            "high_price": 71000.0,
            "low_price": 68000.0,
        }
    ]
