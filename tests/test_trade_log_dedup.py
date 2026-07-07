import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.trade_log import is_trade_logged, append_trade


def test_is_trade_logged_false_for_empty_file(tmp_path, monkeypatch):
    monkeypatch.setattr("core.trade_log.is_db_available", lambda: False)
    path = str(tmp_path / "trades.jsonl")

    assert is_trade_logged("uuid-1", path=path) is False


def test_is_trade_logged_true_after_append(tmp_path, monkeypatch):
    monkeypatch.setattr("core.trade_log.is_db_available", lambda: False)
    path = str(tmp_path / "trades.jsonl")
    append_trade("1", "upbit", "KRW-BTC", "bid", 100.0, 0.1, "manual", "uuid-1", path=path)

    assert is_trade_logged("uuid-1", path=path) is True
    assert is_trade_logged("uuid-2", path=path) is False


def test_is_trade_logged_exact_match_not_substring(tmp_path, monkeypatch):
    """uuid 부분일치로 인한 오탐(L3)이 없어야 한다 — 정확한 JSON 필드 일치만 허용."""
    monkeypatch.setattr("core.trade_log.is_db_available", lambda: False)
    path = str(tmp_path / "trades.jsonl")
    append_trade("1", "upbit", "KRW-BTC", "bid", 100.0, 0.1, "manual", "uuid-1-extra", path=path)

    assert is_trade_logged("uuid-1", path=path) is False
    assert is_trade_logged("uuid-1-extra", path=path) is True


def test_is_trade_logged_ignores_malformed_lines(tmp_path, monkeypatch):
    monkeypatch.setattr("core.trade_log.is_db_available", lambda: False)
    path = str(tmp_path / "trades.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write("not valid json\n")
        f.write(json.dumps({"uuid": "uuid-1"}) + "\n")

    assert is_trade_logged("uuid-1", path=path) is True


def test_is_trade_logged_prefers_db_and_skips_file_when_db_says_logged(tmp_path, monkeypatch):
    monkeypatch.setattr("core.trade_log.is_db_available", lambda: True)
    fake_db = type("FakeDb", (), {})()
    fake_response = type("R", (), {"data": [{"id": 1}]})()

    class FakeTable:
        def select(self, *a, **k):
            return self
        def eq(self, *a, **k):
            return self
        def execute(self):
            return fake_response

    fake_db.table = lambda name: FakeTable()
    monkeypatch.setattr("core.trade_log.get_db", lambda: fake_db)

    path = str(tmp_path / "trades.jsonl")
    assert is_trade_logged("uuid-db-only", path=path) is True


def test_is_trade_logged_db_says_not_logged_skips_file_fallback(tmp_path, monkeypatch):
    """DB 가용 시 DB 조회 결과를 단일 근거로 삼는다(L3) — 파일 스캔으로 다시 확인하지 않는다."""
    monkeypatch.setattr("core.trade_log.is_db_available", lambda: True)
    fake_db = type("FakeDb", (), {})()
    fake_response = type("R", (), {"data": []})()

    class FakeTable:
        def select(self, *a, **k):
            return self
        def eq(self, *a, **k):
            return self
        def execute(self):
            return fake_response

    fake_db.table = lambda name: FakeTable()
    monkeypatch.setattr("core.trade_log.get_db", lambda: fake_db)

    path = str(tmp_path / "trades.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"uuid": "uuid-only-in-file"}) + "\n")

    assert is_trade_logged("uuid-only-in-file", path=path) is False
