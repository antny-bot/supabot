import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

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


def test_kr_stock_display_formats_kis_toss_with_known_code():
    assert sr.kr_stock_display("kis", "000250") == "삼천당제약(000250)"
    assert sr.kr_stock_display("toss", "005930") == "삼성전자(005930)"


def test_kr_stock_display_returns_code_when_unmapped_or_other_exchange():
    assert sr.kr_stock_display("kis", "999999") == "999999"  # 매핑 없는 코드
    assert sr.kr_stock_display("toss", "AAPL") == "AAPL"  # 미국주식
    assert sr.kr_stock_display("upbit", "KRW-BTC") == "KRW-BTC"  # 코인 거래소는 변환 안 함


def test_is_kr_stock_name_handles_codes_and_coins():
    assert sr.is_kr_stock_name("005930") is False
    assert sr.is_kr_stock_name("KRW-BTC") is False
    assert sr.is_kr_stock_name("삼성전자") is True
    assert sr.is_kr_stock_name("samsung") is False


def test_db_lookup_finds_fresh_cached_row():
    # kr_stock_cache에 데이터가 있으면 _db_lookup이 실제로 그 값을 찾아 반환해야 한다
    # (core.db.Table.select()가 .eq() 체이닝을 지원하지 않으면 AttributeError가
    # 발생해 항상 (None, False)로 떨어지는 회귀를 막기 위한 테스트).
    now = datetime.now(timezone.utc).isoformat()
    fake_row = {"code": "204270", "updated_at": now}

    fake_query = MagicMock()
    fake_query.eq.return_value = fake_query
    fake_query.execute.return_value = MagicMock(data=[fake_row])

    fake_table = MagicMock()
    fake_table.select.return_value = fake_query

    fake_db = MagicMock()
    fake_db.table.return_value = fake_table

    with patch("core.db.is_db_available", return_value=True), \
         patch("core.db.get_db", return_value=fake_db):
        code, is_fresh = sr._db_lookup("제이앤티씨")

    assert code == "204270"
    assert is_fresh is True
    fake_table.select.assert_called_once_with("code,updated_at")
    fake_query.eq.assert_called_once_with("name", "제이앤티씨")


async def test_find_kr_stock_candidates_static_map_partial_match_is_capped():
    # "삼성"은 정적 맵에서 삼성전자/삼성SDI/삼성물산/삼성생명/삼성화재/삼성전기/삼성SDS 등
    # 다수와 부분일치한다. DB/KIS 호출 없이도(여기선 user에 KIS 키가 없으므로 스킵)
    # limit 이하로 잘려야 한다.
    adapter = MagicMock()
    adapter.user_manager.get_user.return_value = {"exchanges": {}}

    with patch("core.db.is_db_available", return_value=False):
        candidates = await sr.find_kr_stock_candidates("삼성", adapter, "user1", "bithumb", limit=3)

    assert len(candidates) == 3
    assert all(name.find("삼성") != -1 or "삼성" in name for name, _ in candidates)


async def test_find_kr_stock_candidates_dedupes_across_sources():
    # 정적 맵과 DB 캐시에 같은 코드가 중복으로 잡혀도 한 번만 포함되어야 한다.
    adapter = MagicMock()
    adapter.user_manager.get_user.return_value = {"exchanges": {}}

    fake_query = MagicMock()
    fake_query.ilike.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.execute.return_value = MagicMock(data=[{"name": "삼성전자", "code": "005930"}])

    fake_table = MagicMock()
    fake_table.select.return_value = fake_query

    fake_db = MagicMock()
    fake_db.table.return_value = fake_table

    with patch("core.db.is_db_available", return_value=True), \
         patch("core.db.get_db", return_value=fake_db):
        candidates = await sr.find_kr_stock_candidates("삼성전자", adapter, "user1", "bithumb", limit=5)

    codes = [code for _, code in candidates]
    assert codes.count("005930") == 1
    fake_query.ilike.assert_called_once_with("name", "*삼성전자*")


async def test_find_kr_stock_candidates_includes_kis_search_results():
    # exchange=kis면 KIS 검색 API 결과도 후보에 포함되어야 한다 (모호해도 버리지 않음).
    adapter = _adapter_with_response({
        "STK": [
            {"pdno": "005935", "prdt_abrv_name": "삼성전자우"},
            {"pdno": "005936", "prdt_abrv_name": "삼성전자2우B"},
        ],
        "KSQ": [],
    })

    with patch("core.db.is_db_available", return_value=False):
        candidates = await sr.find_kr_stock_candidates("삼성전자", adapter, "user1", "kis", limit=10)

    codes = {code for _, code in candidates}
    assert "005935" in codes
    assert "005936" in codes
