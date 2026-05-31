import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.order_manager import OrderManager
from core.user_manager import UserManager
import main


def _make_app():
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    return app


def _make_order_manager(tmp_path):
    return OrderManager(str(tmp_path / "orders.json"))


def _default_user():
    return {
        "is_active": True,
        "preferences": dict(UserManager.DEFAULT_PREFERENCES),
        "exchanges": {},
        "llm": {"gemini_api_key": ""},
    }


# T1: KIS 시장 외 시간 → market_closed 상태 업데이트
async def test_kis_outside_market_hours_marks_market_closed(tmp_path, monkeypatch):
    om = _make_order_manager(tmp_path)
    om.add_order("123", "kis", "005930", "uuid-1", 70000, 10, side="bid", strategy="rsitrade")
    monkeypatch.setattr(main, "order_manager", om)

    monkeypatch.setattr(main, "is_kis_regular_session", lambda: False)
    monkeypatch.setattr(main, "kis_next_check_timestamp", lambda: 9_999_999.0)

    mock_adapter = MagicMock()
    mock_adapter.get_order_status = AsyncMock()
    monkeypatch.setattr(main, "exchange_adapter", mock_adapter)

    app = _make_app()
    await main.sync_orders(app)

    assert om.orders[0]["status"] == "market_closed"
    assert om.orders[0]["next_check_at"] == 9_999_999.0
    mock_adapter.get_order_status.assert_not_called()
    app.bot.send_message.assert_not_called()


# T2: 수동 주문 전량 체결 → 알림 발송 + 주문 제거
async def test_manual_order_full_fill_sends_message_and_removes(tmp_path, monkeypatch):
    om = _make_order_manager(tmp_path)
    om.add_order("456", "upbit", "KRW-BTC", "uuid-2", 50_000_000, 0.01, side="bid", strategy="manual")
    monkeypatch.setattr(main, "order_manager", om)

    mock_adapter = MagicMock()
    mock_adapter.get_order_status = AsyncMock(return_value={"state": "done", "executed_volume": 0.01})
    monkeypatch.setattr(main, "exchange_adapter", mock_adapter)

    app = _make_app()
    await main.sync_orders(app)

    assert len(om.orders) == 0
    app.bot.send_message.assert_called_once()
    sent_text = app.bot.send_message.call_args.kwargs.get("text", "")
    assert "주문 완료" in sent_text


# T3: RSITrade 매수 체결 → 연동 매도 주문 생성
async def test_rsitrade_buy_fill_creates_linked_sell_order(tmp_path, monkeypatch):
    om = _make_order_manager(tmp_path)
    om.add_order(
        "789", "upbit", "KRW-ETH", "buy-uuid", 3_000_000, 0.1,
        side="bid", strategy="rsitrade", linked_to="65-75",
    )
    monkeypatch.setattr(main, "order_manager", om)

    mock_adapter = MagicMock()
    mock_adapter.get_order_status = AsyncMock(return_value={"state": "done", "executed_volume": 0.1})
    mock_adapter.create_order = AsyncMock(return_value={"uuid": "sell-uuid-1"})
    monkeypatch.setattr(main, "exchange_adapter", mock_adapter)

    mock_engine = MagicMock()
    mock_engine.get_price_by_rsi = AsyncMock(return_value=4_500_000)
    monkeypatch.setattr(main, "signal_engine", mock_engine)

    mock_um = MagicMock()
    mock_um.get_user = MagicMock(return_value=_default_user())
    monkeypatch.setattr(main, "user_manager", mock_um)

    app = _make_app()
    await main.sync_orders(app)

    # 매수 주문은 제거되고 매도 주문이 생성되어야 함
    assert not any(o["uuid"] == "buy-uuid" for o in om.orders)
    sell_orders = [o for o in om.orders if o["uuid"] == "sell-uuid-1"]
    assert len(sell_orders) == 1
    assert sell_orders[0]["side"] == "ask"
    assert sell_orders[0]["strategy"] == "rsitrade_sell"

    mock_adapter.create_order.assert_called_once()
    call_kwargs = mock_adapter.create_order.call_args
    assert call_kwargs.args[3] == "ask" or call_kwargs.kwargs.get("side") == "ask"

    app.bot.send_message.assert_called_once()
    sent_text = app.bot.send_message.call_args.kwargs.get("text", "")
    assert "익절 예약 완료" in sent_text
