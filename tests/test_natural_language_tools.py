import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core import natural_language as nl


def test_ambiguous_ticker_phrase_returns_clarify_intent():
    intent = nl.preprocess_natural_language_intent("비트 봐줘", {"preferences": {}})

    assert intent["action"] == "clarify"
    assert "시세" in intent["question"]
    assert "전략 상태" in intent["question"]


def test_preprocess_hit_counter_stores_action_only(tmp_path):
    path = tmp_path / "hits.json"

    nl.append_preprocess_hit({"action": "price", "ticker": "BTC"}, path=str(path))
    nl.append_preprocess_hit({"action": "price", "ticker": "ETH"}, path=str(path))
    nl.append_preprocess_hit({"action": "asset", "exchange": "bithumb"}, path=str(path))

    assert nl.read_preprocess_hit_stats(path=str(path)) == {"price": 2, "asset": 1}
    assert "BTC" not in path.read_text(encoding="utf-8")
    assert "bithumb" not in path.read_text(encoding="utf-8")


def test_natural_language_export_limits_and_uses_sanitized_text(tmp_path):
    path = tmp_path / "nl_unmatched.jsonl"
    for i in range(3):
        nl.append_natural_language_log(
            f"BTC {123456 + i}원 TOKENabcdef1234567890abcdef 주문?",
            {"action": "clarify"},
            {"action": "clarify"},
            path=str(path),
        )

    rows = nl.read_recent_natural_language_logs(path=str(path), limit=2)

    assert len(rows) == 2
    assert rows[0]["text_norm"] == "BTC <STOCK>원 <TOKEN> 주문?"
    assert "TOKENabcdef" not in str(rows)


def test_extract_ticker_from_text_prefers_longer_specific_name():
    # "포스코퓨처엠"이 "포스코"(그 자체로도 유효한 별칭)의 부분 문자열이므로,
    # 길이 내림차순 매칭이 없으면 짧은 "포스코"(005490)가 먼저 잡혀버린다.
    assert nl._extract_ticker_from_text("포스코퓨처엠 시세 알려줘") == "003670"
    assert nl._extract_ticker_from_text("포스코 시세 알려줘") == "005490"


def test_extract_ticker_from_text_covers_expanded_kr_stock_map():
    # stock_resolver._KR_NAME_MAP과 통합되면서 새로 인식 가능해진 종목명들.
    assert nl._extract_ticker_from_text("카카오 시세 알려줘") == "035720"
    assert nl._extract_ticker_from_text("SK하이닉스 시세 알려줘") == "000660"


def test_clear_natural_language_operational_logs(tmp_path):
    log_path = tmp_path / "nl_unmatched.jsonl"
    hit_path = tmp_path / "hits.json"
    nl.append_natural_language_log("BTC 123456원", {"action": "clarify"}, {"action": "clarify"}, path=str(log_path))
    nl.append_preprocess_hit({"action": "price"}, path=str(hit_path))

    nl.clear_natural_language_logs(log_path=str(log_path), hit_path=str(hit_path))

    assert nl.read_natural_language_log_stats(path=str(log_path)) == []
    assert nl.read_preprocess_hit_stats(path=str(hit_path)) == {}
