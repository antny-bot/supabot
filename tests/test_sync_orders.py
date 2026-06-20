import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.order_manager import OrderManager
from core.user_manager import UserManager
from core.exchanges.upbit import UpbitExchange
from core.exchanges.bithumb import BithumbExchange
from core.exchanges.kis import KisExchange
from core.exchanges.toss import TossExchange
import main

_EXCHANGE_CLASSES = {
    "upbit": UpbitExchange,
    "bithumb": BithumbExchange,
    "kis": KisExchange,
    "toss": TossExchange,
}


def _make_app():
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    return app


def _wire_real_exchanges(mock_adapter):
    """mock_adapter.get_exchange()가 capability 로직(round_volume/adjust_price_to_tick 등)을
    갖는 실제 Exchange 인스턴스를 돌려주도록 연결한다."""
    mock_adapter.get_exchange = lambda exchange: _EXCHANGE_CLASSES[exchange](mock_adapter)


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

    monkeypatch.setattr(main, "kis_next_check_timestamp", lambda: 9_999_999.0)

    mock_adapter = MagicMock()
    mock_adapter.get_order_status = AsyncMock()
    mock_adapter.get_exchange = lambda exchange: MagicMock(is_market_open=lambda: False)
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
    _wire_real_exchanges(mock_adapter)
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
    _wire_real_exchanges(mock_adapter)
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


# T4: RSITrade 매수 체결 → stop_loss_pct 설정 시 stop_price 계산
async def test_rsitrade_buy_fill_sets_stop_price_when_configured(tmp_path, monkeypatch):
    om = _make_order_manager(tmp_path)
    om.add_order(
        "111", "upbit", "KRW-BTC", "buy-uuid2", 50_000_000, 0.001,
        side="bid", strategy="rsitrade", linked_to="65-75",
    )
    monkeypatch.setattr(main, "order_manager", om)

    user = _default_user()
    user["preferences"]["stop_loss_pct"] = 5.0  # 5% 손절 설정

    mock_adapter = MagicMock()
    mock_adapter.get_order_status = AsyncMock(return_value={"state": "done", "executed_volume": 0.001})
    mock_adapter.create_order = AsyncMock(return_value={"uuid": "sell-uuid-2"})
    _wire_real_exchanges(mock_adapter)
    monkeypatch.setattr(main, "exchange_adapter", mock_adapter)

    mock_engine = MagicMock()
    mock_engine.get_price_by_rsi = AsyncMock(return_value=60_000_000)
    monkeypatch.setattr(main, "signal_engine", mock_engine)

    mock_um = MagicMock()
    mock_um.get_user = MagicMock(return_value=user)
    monkeypatch.setattr(main, "user_manager", mock_um)

    app = _make_app()
    await main.sync_orders(app)

    sell_orders = [o for o in om.orders if o["uuid"] == "sell-uuid-2"]
    assert len(sell_orders) == 1
    # stop_price = buy_price * (1 - 5/100) = 50_000_000 * 0.95 = 47_500_000
    assert sell_orders[0]["stop_price"] == pytest.approx(47_500_000, rel=0.01)


# T5: rsitrade_sell 포지션 stop-loss 발동 → 손절 주문 제출
async def test_stoploss_triggers_when_price_below_stop_price(tmp_path, monkeypatch):
    om = _make_order_manager(tmp_path)
    om.add_order(
        "222", "upbit", "KRW-ETH", "sell-uuid3", 4_000_000, 0.1,
        side="ask", strategy="rsitrade_sell", stop_price=3_000_000,
    )
    monkeypatch.setattr(main, "order_manager", om)

    mock_adapter = MagicMock()
    mock_adapter.get_order_status = AsyncMock(return_value={"state": "wait", "executed_volume": 0.0})
    mock_adapter.get_ticker = AsyncMock(return_value={"trade_price": 2_500_000})  # 손절 기준가 미만
    mock_adapter.cancel_order = AsyncMock(return_value=True)
    mock_adapter.create_order = AsyncMock(return_value={"uuid": "sl-uuid"})
    _wire_real_exchanges(mock_adapter)
    monkeypatch.setattr(main, "exchange_adapter", mock_adapter)

    app = _make_app()
    await main.sync_orders(app)

    # 기존 rsitrade_sell 제거
    assert not any(o["uuid"] == "sell-uuid3" for o in om.orders)
    # 손절 주문 추가
    sl_orders = [o for o in om.orders if o["strategy"] == "stoploss"]
    assert len(sl_orders) == 1

    mock_adapter.cancel_order.assert_called_once()
    mock_adapter.create_order.assert_called_once()

    app.bot.send_message.assert_called_once()
    sent_text = app.bot.send_message.call_args.kwargs.get("text", "")
    assert "손절 실행" in sent_text


# T6: rsitrade_sell 포지션 — 현재가가 stop_price 이상이면 손절 미발동
async def test_stoploss_does_not_trigger_when_price_above_stop_price(tmp_path, monkeypatch):
    om = _make_order_manager(tmp_path)
    om.add_order(
        "333", "upbit", "KRW-ETH", "sell-uuid4", 4_000_000, 0.1,
        side="ask", strategy="rsitrade_sell", stop_price=3_000_000,
    )
    monkeypatch.setattr(main, "order_manager", om)

    mock_adapter = MagicMock()
    mock_adapter.get_order_status = AsyncMock(return_value={"state": "wait", "executed_volume": 0.0})
    mock_adapter.get_ticker = AsyncMock(return_value={"trade_price": 3_500_000})  # 손절 기준가 이상
    mock_adapter.cancel_order = AsyncMock()
    _wire_real_exchanges(mock_adapter)
    monkeypatch.setattr(main, "exchange_adapter", mock_adapter)

    app = _make_app()
    await main.sync_orders(app)

    # 손절 미발동 → 원래 주문 유지
    assert any(o["uuid"] == "sell-uuid4" for o in om.orders)
    mock_adapter.cancel_order.assert_not_called()
    app.bot.send_message.assert_not_called()


# T7: 동기화 사이클 도중 /cancelno 등으로 이미 제거된 주문은 외부 개입 오탐을 발생시키지 않음
async def test_concurrently_removed_order_skips_external_cancel_alert(tmp_path, monkeypatch):
    om = _make_order_manager(tmp_path)
    om.add_order("444", "bithumb", "KRW-BTC", "uuid-a", 50_000_000, 0.001, side="bid", strategy="manual")
    om.add_order("444", "bithumb", "KRW-BTC", "uuid-b", 51_000_000, 0.001, side="bid", strategy="manual")
    monkeypatch.setattr(main, "order_manager", om)

    async def get_order_status(user_id, exchange, uuid, ticker):
        if uuid == "uuid-a":
            # uuid-a 처리 중 다른 코루틴(/cancelno)이 uuid-b를 취소·제거했다고 가정
            om.remove_order("uuid-b")
            return {"state": "wait", "executed_volume": 0.0}
        return {"state": "cancel", "executed_volume": 0.0}

    mock_adapter = MagicMock()
    mock_adapter.get_order_status = AsyncMock(side_effect=get_order_status)
    _wire_real_exchanges(mock_adapter)
    monkeypatch.setattr(main, "exchange_adapter", mock_adapter)

    app = _make_app()
    await main.sync_orders(app)

    # uuid-b는 이미 제거되었으므로 거래소에 재조회하지 않아야 함
    called_uuids = [c.args[2] for c in mock_adapter.get_order_status.call_args_list]
    assert called_uuids == ["uuid-a"]

    # "외부 개입" 오탐 알림이 발생하지 않아야 함
    sent_texts = [c.kwargs.get("text", "") for c in app.bot.send_message.call_args_list]
    assert not any("외부 개입" in t for t in sent_texts)


# T: next_check_at이 미래인 주문은 이번 사이클에서 거래소 재조회를 건너뛴다
async def test_future_next_check_at_skips_order(tmp_path, monkeypatch):
    om = _make_order_manager(tmp_path)
    om.add_order("123", "kis", "005930", "uuid-future", 70000, 10, side="bid", strategy="rsitrade")
    om.update_next_check_at("uuid-future", 9_999_999_999.0)  # 먼 미래
    monkeypatch.setattr(main, "order_manager", om)

    mock_adapter = MagicMock()
    mock_adapter.get_order_status = AsyncMock()
    mock_adapter.get_exchange = lambda exchange: MagicMock(is_market_open=lambda: True)
    monkeypatch.setattr(main, "exchange_adapter", mock_adapter)

    app = _make_app()
    await main.sync_orders(app)

    # next_check_at이 미래이므로 거래소 조회/상태 변경이 없어야 함
    mock_adapter.get_order_status.assert_not_called()
    assert om.orders[0]["next_check_at"] == 9_999_999_999.0


# T: has_order 인덱스가 add/remove/replace에 따라 정확히 유지된다
def test_has_order_index_consistency(tmp_path):
    om = _make_order_manager(tmp_path)
    om.add_order("u", "upbit", "KRW-BTC", "uuid-1", 100, 1, side="bid", strategy="manual")
    assert om.has_order("uuid-1") is True
    assert om.has_order("nope") is False

    om.replace_order_uuid("uuid-1", "uuid-2")
    assert om.has_order("uuid-1") is False
    assert om.has_order("uuid-2") is True

    om.remove_order("uuid-2")
    assert om.has_order("uuid-2") is False
