import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import core.manual_order_tokens as mot
from core.manual_order_tokens import create_reset_token, pop_valid_reset_token
from core.order_manager import OrderManager
import core.trade_log as trade_log
from core.trade_log import clear_user_trades


# --- reset 토큰 ---

def test_create_and_pop_reset_token():
    token = create_reset_token("admin1", "target1")
    pending, error = pop_valid_reset_token(token, "admin1")
    assert error is None
    assert pending["target_user_id"] == "target1"


def test_reset_token_single_use():
    token = create_reset_token("admin1", "target1")
    pending1, err1 = pop_valid_reset_token(token, "admin1")
    pending2, err2 = pop_valid_reset_token(token, "admin1")
    assert err1 is None and pending1 is not None
    assert pending2 is None and err2 is not None


def test_reset_token_wrong_admin_rejected():
    token = create_reset_token("admin1", "target1")
    pending, error = pop_valid_reset_token(token, "admin2")
    assert pending is None
    assert error is not None
    # 토큰은 보존되어 정당한 admin이 재시도 가능
    pending2, error2 = pop_valid_reset_token(token, "admin1")
    assert error2 is None
    assert pending2["target_user_id"] == "target1"


def test_reset_token_expired(monkeypatch):
    token = create_reset_token("admin1", "target1")
    mot._pending_reset_users[token]["created_at"] -= mot.MANUAL_ORDER_TTL_SECONDS + 1
    pending, error = pop_valid_reset_token(token, "admin1")
    assert pending is None
    assert "만료" in error


# --- order_manager.clear_user_orders ---

def _om(tmp_path, monkeypatch):
    monkeypatch.setattr("core.order_manager.is_db_available", lambda: False)
    return OrderManager(file_path=str(tmp_path / "orders.json"))


def test_clear_user_orders_removes_only_target_user(tmp_path, monkeypatch):
    om = _om(tmp_path, monkeypatch)
    om.add_order("u1", "upbit", "KRW-BTC", "uuid1", 100, 1)
    om.add_order("u1", "upbit", "KRW-ETH", "uuid2", 100, 1)
    om.add_order("u2", "upbit", "KRW-BTC", "uuid3", 100, 1)

    removed = om.clear_user_orders("u1")

    assert removed == 2
    assert om.get_user_orders("u1") == []
    assert len(om.get_user_orders("u2")) == 1
    assert "uuid1" not in om._uuid_set and "uuid2" not in om._uuid_set
    assert "uuid3" in om._uuid_set


def test_clear_user_orders_no_orders_is_noop(tmp_path, monkeypatch):
    om = _om(tmp_path, monkeypatch)
    om.add_order("u2", "upbit", "KRW-BTC", "uuid3", 100, 1)
    removed = om.clear_user_orders("u1")
    assert removed == 0
    assert len(om.get_user_orders("u2")) == 1


# --- trade_log.clear_user_trades ---

def test_clear_user_trades_filters_file(tmp_path, monkeypatch):
    monkeypatch.setattr(trade_log, "is_db_available", lambda: False)
    path = str(tmp_path / "trades.jsonl")
    trade_log.append_trade("u1", "upbit", "KRW-BTC", "bid", 100, 1, "manual", "uuid1", path=path)
    trade_log.append_trade("u2", "upbit", "KRW-BTC", "bid", 100, 1, "manual", "uuid2", path=path)
    trade_log.append_trade("u1", "upbit", "KRW-ETH", "ask", 200, 1, "manual", "uuid3", path=path)

    removed = clear_user_trades("u1", path=path)

    assert removed == 2
    with open(path, "r", encoding="utf-8") as f:
        lines = [json.loads(l) for l in f]
    assert len(lines) == 1
    assert lines[0]["user_id"] == "u2"


def test_clear_user_trades_missing_file_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(trade_log, "is_db_available", lambda: False)
    path = str(tmp_path / "nonexistent.jsonl")
    removed = clear_user_trades("u1", path=path)
    assert removed == 0
