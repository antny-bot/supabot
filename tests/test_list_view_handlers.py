import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import main
import core.list_view_tokens as lvt
from handlers import list_view_handlers


def _order(exchange="upbit", ticker="KRW-BTC", side="bid", status="wait", group_no=None, price=50_000_000.0, volume=0.001, uuid="u1", strategy="manual", target_rsi=None):
    return {
        "user_id": "1", "exchange": exchange, "ticker": ticker, "uuid": uuid,
        "price": price, "volume": volume, "filled_volume": 0.0, "side": side,
        "strategy": strategy, "target_rsi": target_rsi, "linked_to": None, "status": status,
        "created_at": 0.0, "next_check_at": 0.0, "reorder_of": None, "stop_price": None,
        "group_no": group_no,
    }


def _make_query(user_id, callback_data):
    query = MagicMock()
    query.from_user.id = user_id
    query.data = callback_data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    return query


def _make_update(query):
    update = MagicMock()
    update.callback_query = query
    return update


def _make_context():
    return MagicMock()


# ── /orders ──────────────────────────────────────────────────────────────────

def test_orders_collapsed_summarizes_batch_groups(monkeypatch):
    orders = [_order(group_no=1, uuid=f"g{i}") for i in range(3)] + [_order(group_no=None, uuid="solo")]
    mock_om = MagicMock()
    mock_om.get_user_orders = MagicMock(return_value=orders)
    monkeypatch.setattr(main, "order_manager", mock_om)

    msg, markup = list_view_handlers.build_orders_message("1", "upbit", expanded=False, token="t1")
    assert "📦" in msg and "#1 배치" in msg
    assert "3건" in msg
    assert markup is not None


def test_orders_expanded_shows_every_order(monkeypatch):
    orders = [_order(group_no=1, uuid=f"g{i}") for i in range(3)]
    mock_om = MagicMock()
    mock_om.get_user_orders = MagicMock(return_value=orders)
    monkeypatch.setattr(main, "order_manager", mock_om)

    msg, markup = list_view_handlers.build_orders_message("1", "upbit", expanded=True, token="t1")
    assert msg.count("📌") == 3
    assert "📦" not in msg


async def test_orders_toggle_callback_expands_then_collapses(monkeypatch):
    orders = [_order(group_no=1, uuid=f"g{i}") for i in range(3)] + [_order(group_no=None, uuid="solo")]
    mock_om = MagicMock()
    mock_om.get_user_orders = MagicMock(return_value=orders)
    monkeypatch.setattr(main, "order_manager", mock_om)

    token = main.create_list_view_token("1", "orders", {"expanded": False, "exchange": "upbit"})
    query = _make_query(1, f"lv|orders|{token}|toggle")
    update = _make_update(query)

    await list_view_handlers.list_view_callback(update, _make_context())
    text = query.edit_message_text.call_args.args[0]
    assert "📦" not in text  # 펼쳐졌으니 배치 요약이 아니라 개별 주문이 보여야 함

    query2 = _make_query(1, f"lv|orders|{token}|toggle")
    update2 = _make_update(query2)
    await list_view_handlers.list_view_callback(update2, _make_context())
    text2 = query2.edit_message_text.call_args.args[0]
    assert "📦" in text2  # 다시 접힘


async def test_orders_toggle_discards_token_when_no_orders_left(monkeypatch):
    mock_om = MagicMock()
    mock_om.get_user_orders = MagicMock(return_value=[])
    monkeypatch.setattr(main, "order_manager", mock_om)

    token = main.create_list_view_token("1", "orders", {"expanded": False, "exchange": "upbit"})
    query = _make_query(1, f"lv|orders|{token}|toggle")
    update = _make_update(query)

    await list_view_handlers.list_view_callback(update, _make_context())
    text = query.edit_message_text.call_args.args[0]
    assert "없습니다" in text
    assert query.edit_message_text.call_args.kwargs.get("reply_markup") is None
    entry, error = main.peek_list_view(token, "1")
    assert entry is None and error is not None


# ── /status ──────────────────────────────────────────────────────────────────

async def test_status_toggle_reveals_truncated_orders(monkeypatch):
    orders = [_order(group_no=1, uuid=f"g{i}", strategy="grid") for i in range(5)]
    mock_om = MagicMock()
    mock_om.get_user_orders = MagicMock(return_value=orders)
    monkeypatch.setattr(main, "order_manager", mock_om)

    token = main.create_list_view_token("1", "status", {"expanded": False})
    query = _make_query(1, f"lv|status|{token}|toggle")
    update = _make_update(query)

    await list_view_handlers.list_view_callback(update, _make_context())
    text = query.edit_message_text.call_args.args[0]
    assert "그 외 생략" not in text
    assert "5. 매수" in text


# ── /history ─────────────────────────────────────────────────────────────────

def test_history_message_paginates_five_per_page():
    history = [{"side": "bid", "market": "KRW-BTC", "price": 100.0, "volume": 1.0, "created_at": f"2026-01-0{i+1}T00:00:00"} for i in range(12)]
    text, markup, page = list_view_handlers.build_history_message("upbit", "KRW-BTC", history, page=0, token="t1")
    assert page == 0
    assert "1-5/12건" in text
    assert markup is not None  # 다음 페이지 버튼 존재


async def test_history_next_then_prev_callback(monkeypatch):
    history = [{"side": "bid", "market": "KRW-BTC", "price": 100.0, "volume": 1.0, "created_at": f"2026-01-{i+1:02d}T00:00:00"} for i in range(12)]
    token = main.create_list_view_token("1", "history", {"page": 0}, snapshot={"exchange": "upbit", "ticker": "KRW-BTC", "history": history})

    query = _make_query(1, f"lv|history|{token}|next")
    await list_view_handlers.list_view_callback(_make_update(query), _make_context())
    text = query.edit_message_text.call_args.args[0]
    assert "6-10/12건" in text

    query2 = _make_query(1, f"lv|history|{token}|next")
    await list_view_handlers.list_view_callback(_make_update(query2), _make_context())
    text2 = query2.edit_message_text.call_args.args[0]
    assert "11-12/12건" in text2
    assert query2.edit_message_text.call_args.kwargs.get("reply_markup").inline_keyboard[0][0].text.startswith("◀️")

    query3 = _make_query(1, f"lv|history|{token}|prev")
    await list_view_handlers.list_view_callback(_make_update(query3), _make_context())
    text3 = query3.edit_message_text.call_args.args[0]
    assert "6-10/12건" in text3


# ── /report ──────────────────────────────────────────────────────────────────

def _trade(exchange, ticker, side, price=1000.0, volume=1.0):
    return {"exchange": exchange, "ticker": ticker, "side": side, "price": price, "volume": volume}


async def test_report_next_page_keeps_grand_totals(monkeypatch):
    trades = []
    for i in range(15):
        trades.append(_trade("upbit", f"KRW-COIN{i}", "bid", price=1000.0, volume=1.0))
        trades.append(_trade("upbit", f"KRW-COIN{i}", "ask", price=1100.0, volume=1.0))
    token = main.create_list_view_token("1", "report", {"page": 0}, snapshot={"trades": trades, "period": "all"})

    query = _make_query(1, f"lv|report|{token}|next")
    await list_view_handlers.list_view_callback(_make_update(query), _make_context())
    text = query.edit_message_text.call_args.args[0]
    assert "2/2 페이지" in text
    assert "총 손익" in text  # 합계는 페이지와 무관하게 항상 표시


# ── /asset ───────────────────────────────────────────────────────────────────

async def test_asset_toggle_expands_others_for_one_exchange(monkeypatch):
    coin_balances = [{"currency": "KRW", "balance": "0", "locked": "0"}]
    for i in range(8):
        coin_balances.append({"currency": f"COIN{i}", "balance": "1", "locked": "0"})
    ticker_prices = {f"COIN{i}": 1000.0 for i in range(8)}
    snapshot = {
        "exchanges": ["upbit"],
        "balances": {"upbit": coin_balances},
        "ticker_prices": {"upbit": ticker_prices},
    }
    token = main.create_list_view_token("1", "asset", {"expanded_exchanges": []}, snapshot=snapshot)

    query = _make_query(1, f"lv|asset|{token}|toggle|upbit")
    await list_view_handlers.list_view_callback(_make_update(query), _make_context())
    text = query.edit_message_text.call_args.args[0]
    assert "기타" not in text  # 펼쳤으니 기타 요약이 아니라 전부 표시
    assert "COIN7" in text


# ── 토큰 만료/타유저 ─────────────────────────────────────────────────────────

async def test_expired_token_shows_expiry_message(monkeypatch):
    token = main.create_list_view_token("1", "orders", {"expanded": False, "exchange": "upbit"})
    lvt._pending_list_views[token]["last_access"] -= (lvt.LIST_VIEW_TTL_SECONDS + 1)

    query = _make_query(1, f"lv|orders|{token}|toggle")
    await list_view_handlers.list_view_callback(_make_update(query), _make_context())
    text = query.edit_message_text.call_args.args[0]
    assert "만료" in text


async def test_other_user_cannot_use_token(monkeypatch):
    token = main.create_list_view_token("1", "orders", {"expanded": False, "exchange": "upbit"})

    query = _make_query(999, f"lv|orders|{token}|toggle")
    await list_view_handlers.list_view_callback(_make_update(query), _make_context())
    text = query.edit_message_text.call_args.args[0]
    assert "다른 사용자" in text
