import os
import sys
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core import stock_resolver as sr


class DummyUserManager:
    def get_user(self, user_id):
        return {"exchanges": {"kis": {"app_key": "app", "app_secret": "secret"}}}


def _adapter_with_response(by_market):
    """by_market: {"STK": [...], "KSQ": [...]} -> output list per market."""
    adapter = MagicMock()
    adapter.user_manager = DummyUserManager()

    async def fake_request_kis(user_id, method, path, tr_id, params=None, **kwargs):
        return {"output": by_market.get(params["MKET_ID_CD"], [])}

    adapter._request_kis = fake_request_kis
    return adapter


async def test_search_via_kis_prefers_exact_match_over_order():
    # "삼성전자우"가 API 응답에서 먼저 나와도 정확히 일치하는 "삼성전자"를 선택해야 한다.
    adapter = _adapter_with_response({
        "STK": [
            {"pdno": "005935", "prdt_abrv_name": "삼성전자우"},
            {"pdno": "005930", "prdt_abrv_name": "삼성전자"},
        ],
        "KSQ": [],
    })

    result = await sr._search_via_kis(adapter, "user1", "삼성전자")

    assert result == "005930"


async def test_search_via_kis_ambiguous_prefix_returns_none():
    # 정확 일치가 없고 접두 일치 후보가 둘 이상이면 추측하지 않고 None.
    adapter = _adapter_with_response({
        "STK": [
            {"pdno": "005935", "prdt_abrv_name": "삼성전자우"},
            {"pdno": "005936", "prdt_abrv_name": "삼성전자2우B"},
        ],
        "KSQ": [],
    })

    result = await sr._search_via_kis(adapter, "user1", "삼성전자")

    assert result is None


async def test_search_via_kis_single_prefix_candidate_returned():
    # 정확 일치가 없고 접두 일치 후보가 단 하나면 그 종목코드를 반환한다.
    adapter = _adapter_with_response({
        "STK": [],
        "KSQ": [{"pdno": "247540", "prdt_abrv_name": "에코프로비엠"}],
    })

    result = await sr._search_via_kis(adapter, "user1", "에코프로비")

    assert result == "247540"


async def test_search_via_kis_no_candidates_returns_none():
    adapter = _adapter_with_response({"STK": [], "KSQ": []})

    result = await sr._search_via_kis(adapter, "user1", "존재하지않는종목")

    assert result is None


async def test_resolve_kr_stock_name_uses_static_map_without_api_call():
    adapter = MagicMock()
    adapter.user_manager = DummyUserManager()
    adapter._request_kis = MagicMock(side_effect=AssertionError("API should not be called"))

    result = await sr.resolve_kr_stock_name("삼성전자", adapter, "user1", "kis")

    assert result == "005930"


def test_is_kr_stock_name_handles_codes_and_coins():
    assert sr.is_kr_stock_name("005930") is False
    assert sr.is_kr_stock_name("KRW-BTC") is False
    assert sr.is_kr_stock_name("삼성전자") is True
    assert sr.is_kr_stock_name("samsung") is False
