import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import core.order_sync as order_sync
from core.order_manager import OrderManager


@pytest.fixture
def mock_app():
    app = MagicMock()
    app.bot = MagicMock()
    app.bot.send_message = AsyncMock()
    return app


@pytest.mark.asyncio
async def test_order_manager_reload_preserves_concurrent_add():
    """(c) OrderManager.reload_from_db_async: DB 읽기 중 add_order 된 주문이 병합되어 보존되는지 검증."""
    om = OrderManager("data/test_orders_p0.json")
    om.orders = []
    om._orders_by_uuid = {}
    om._uuid_set = set()

    with patch("core.order_manager.is_db_available", return_value=True), \
         patch.object(om, "flush_pending_writes", new=AsyncMock()), \
         patch.object(om, "_save_orders_to_file"):

        async def fake_fetch():
            # simulate DB fetch delay during which a new order is added
            await asyncio.sleep(0.01)
            om.add_order("u1", "upbit", "KRW-BTC", "uuid_concurrent", 1000, 1.0, side="bid")
            return [{"uuid": "uuid_db_1", "user_id": "u1", "ticker": "KRW-ETH"}]

        with patch.object(om, "_fetch_all_orders_async", side_effect=fake_fetch):
            ok = await om.reload_from_db_async()
            assert ok is True
            assert om.has_order("uuid_db_1")
            assert om.has_order("uuid_concurrent")
            assert len(om.orders) == 2


@pytest.mark.asyncio
async def test_stop_loss_keeps_order_on_failure(mock_app):
    """(b) _apply_stop_loss: 손절 주문 발행 실패 시 remove_order 하지 않고 추적 유지·재시도하는지 검증."""
    om = OrderManager("data/test_orders_p0.json")
    om.orders = []
    om._orders_by_uuid = {}
    om._uuid_set = set()

    test_ord = {
        "uuid": "rsitrade_sell_1",
        "user_id": "u1",
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "strategy": "rsitrade_sell",
        "stop_price": 50000.0,
        "volume": 1.0,
        "filled_volume": 0.0,
    }
    om.orders.append(test_ord)
    om._orders_by_uuid[test_ord["uuid"]] = test_ord
    om._uuid_set.add(test_ord["uuid"])

    mock_ex_adapter = MagicMock()
    mock_ex_adapter.cancel_order = AsyncMock(return_value=True)
    mock_ex_adapter.create_order = AsyncMock(side_effect=Exception("Network error"))
    mock_ex = MagicMock()
    mock_ex.round_volume = MagicMock(side_effect=lambda v: v)
    mock_ex.adjust_price_to_tick = MagicMock(side_effect=lambda p, t: p)
    mock_ex_adapter.get_exchange = MagicMock(return_value=mock_ex)

    with patch("core.order_sync._get_app_context", return_value=(om, None, mock_ex_adapter, None)):
        handled = await order_sync._apply_stop_loss(
            mock_app, test_ord, "wait", {("upbit", "KRW-BTC"): 48000.0}
        )
        assert handled is True
        # 주문이 삭제되지 않고 남아있어야 함
        assert om.has_order("rsitrade_sell_1")
        # 실패 알림 전송 확인
        mock_app.bot.send_message.assert_called_once()
        assert "손절 주문 발행 실패" in mock_app.bot.send_message.call_args[1]["text"]


@pytest.mark.asyncio
async def test_partial_fill_trade_logged_before_mark_reorder_pending(mock_app):
    """(d) _process_order_fill: 만료→재주문 대기 전환 전에 exec_vol>0 부분 체결분 append_trade 기록 검증."""
    om = OrderManager("data/test_orders_p0.json")
    ord_item = {
        "uuid": "kis_order_1",
        "user_id": "u1",
        "exchange": "kis",
        "ticker": "005930",
        "side": "bid",
        "strategy": "grid",
        "price": 70000.0,
        "volume": 10.0,
        "filled_volume": 2.0,
        "status": "wait",
    }
    om.orders = [ord_item]
    om._orders_by_uuid = {ord_item["uuid"]: ord_item}
    om._uuid_set = {ord_item["uuid"]}

    ex_obj = MagicMock()
    ex_obj.supports_reserved_orders = True
    ex_obj.next_check_timestamp = MagicMock(return_value=123456789.0)

    trades_recorded = []
    def fake_append_trade(**kwargs):
        trades_recorded.append(kwargs)

    res = {
        "state": "cancel",
        "executed_volume": 5.0,  # 2.0 -> 5.0 (신규 체결 3.0주)
        "fee_amount": 100,
    }

    with patch("core.order_sync._get_app_context", return_value=(om, None, None, None)), \
         patch("core.order_sync._call_append_trade", side_effect=fake_append_trade), \
         patch("core.order_sync._refund_unfilled_budget", new=AsyncMock()):

        await order_sync._process_order_fill(mock_app, ord_item, res, ex_obj)

        # 재주문 대기로 전환되었는지 확인
        assert ord_item["status"] == "pending_reorder"
        assert ord_item["next_check_at"] == 123456789.0
        # 신규 체결분 3주에 대해 append_trade가 기록되었는지 확인
        assert len(trades_recorded) == 1
        assert trades_recorded[0]["volume"] == 3.0
        assert trades_recorded[0]["uuid"] == "kis_order_1"


@pytest.mark.asyncio
async def test_create_linked_sell_balance_symbol_matching(mock_app):
    """(e) _create_linked_sell_order 잔고 심볼 매칭 정규화 및 빈 문자열 버그 방지 검증."""
    om = OrderManager("data/test_orders_p0.json")
    ord_item = {
        "uuid": "rsi_buy_1",
        "user_id": "u1",
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "side": "bid",
        "strategy": "rsitrade",
        "linked_to": "70",
        "price": 50000000.0,
        "volume": 0.01,
        "filled_volume": 0.0,
    }
    om.orders = [ord_item]
    om._orders_by_uuid = {ord_item["uuid"]: ord_item}
    om._uuid_set = {ord_item["uuid"]}

    user_mgr = MagicMock()
    user_mgr.get_user = MagicMock(return_value={"preferences": {}})

    signal_engine = MagicMock()
    signal_engine.get_price_by_rsi = AsyncMock(return_value=55000000.0)

    mock_ex = MagicMock()
    mock_ex.round_volume = MagicMock(side_effect=lambda v: v)
    mock_ex.requires_integer_volume = MagicMock(return_value=False)
    mock_ex.adjust_price_to_tick = MagicMock(side_effect=lambda p, t: p)

    mock_ex_adapter = MagicMock()
    mock_ex_adapter.get_exchange = MagicMock(return_value=mock_ex)
    # create_order returns None to simulate failure -> triggers balance check
    mock_ex_adapter.create_order = AsyncMock(return_value=None)
    # Balances contain empty string and other coin
    mock_ex_adapter.get_balances = AsyncMock(return_value=[
        {"currency": "", "balance": "100.0"},
        {"currency": "ETH", "balance": "5.0"},
        {"currency": "BTC", "balance": "0.005"}, # insufficient for 0.01
    ])

    with patch("core.order_sync._get_app_context", return_value=(om, user_mgr, mock_ex_adapter, signal_engine)):
        outcome = await order_sync._create_linked_sell_order(mock_app, ord_item, 0.01, "done")
        # Empty string shouldn't match. BTC balance 0.005 < 0.01 -> external_sold detected!
        assert outcome == "external_sold"


@pytest.mark.asyncio
async def test_linked_sell_retry_limit(mock_app):
    """(f) 연동 매도 no_price/failed 재시도 횟수 제한 및 알림 검증."""
    order_sync._linked_sell_failures.clear()
    om = OrderManager("data/test_orders_p0.json")
    ord_item = {
        "uuid": "rsi_buy_fail",
        "user_id": "u1",
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "side": "bid",
        "strategy": "rsitrade",
        "linked_to": "70",
        "price": 50000000.0,
        "volume": 0.01,
        "filled_volume": 0.0,
    }
    om.orders = [ord_item]
    om._orders_by_uuid = {ord_item["uuid"]: ord_item}
    om._uuid_set = {ord_item["uuid"]}

    res = {"state": "done", "executed_volume": 0.01}
    ex_obj = MagicMock()
    ex_obj.supports_reserved_orders = False

    with patch("core.order_sync._get_app_context", return_value=(om, None, None, None)), \
         patch("core.order_sync._create_linked_sell_order", new=AsyncMock(return_value="failed")):

        # 4 times: keep_order_for_retry is True, order is not removed
        for i in range(4):
            await order_sync._process_order_fill(mock_app, ord_item, res, ex_obj)
            assert om.has_order("rsi_buy_fail")

        # 5th time: fail limit reached -> give up -> keep_order_for_retry becomes False -> order removed
        await order_sync._process_order_fill(mock_app, ord_item, res, ex_obj)
        assert not om.has_order("rsi_buy_fail")
        assert "연동 익절 매도 생성 5회 실패" in mock_app.bot.send_message.call_args[1]["text"]


@pytest.mark.asyncio
async def test_sync_orders_isolates_per_order_exceptions_and_fetch_errors(mock_app):
    """(a) sync_orders 메인 루프 주문 단위 예외 격리 및 _fetch_status return_exceptions 검증."""
    om = OrderManager("data/test_orders_p0.json")
    ord_err = {
        "uuid": "ord_err_1",
        "user_id": "u1",
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "side": "bid",
        "strategy": "manual",
        "price": 1000.0,
        "volume": 1.0,
        "filled_volume": 0.0,
        "status": "wait",
    }
    ord_ok = {
        "uuid": "ord_ok_2",
        "user_id": "u1",
        "exchange": "upbit",
        "ticker": "KRW-ETH",
        "side": "bid",
        "strategy": "manual",
        "price": 2000.0,
        "volume": 1.0,
        "filled_volume": 0.0,
        "status": "wait",
    }
    om.orders = [ord_err, ord_ok]
    om._orders_by_uuid = {ord_err["uuid"]: ord_err, ord_ok["uuid"]: ord_ok}
    om._uuid_set = {"ord_err_1", "ord_ok_2"}

    mock_ex = MagicMock()
    mock_ex.is_market_open = MagicMock(return_value=True)
    mock_ex.supports_reserved_orders = False

    async def fake_get_order_status(uid, ex, uuid, ticker):
        if uuid == "ord_err_1":
            raise RuntimeError("API timeout")
        return {"state": "done", "executed_volume": 1.0}

    mock_ex_adapter = MagicMock()
    mock_ex_adapter.get_exchange = MagicMock(return_value=mock_ex)
    mock_ex_adapter.get_order_status = AsyncMock(side_effect=fake_get_order_status)

    with patch("core.order_sync._get_app_context", return_value=(om, None, mock_ex_adapter, None)), \
         patch("core.order_sync._call_append_trade"), \
         patch("main._spawn_bg"):
        await order_sync.sync_orders(mock_app)

    # ord_err_1이 예외를 던져도 ord_ok_2는 정상 체결 완료 처리되어야 함
    assert om.has_order("ord_err_1")
    assert not om.has_order("ord_ok_2")


@pytest.mark.asyncio
async def test_stop_loss_retry_succeeds_without_status_lookup(mock_app):
    """(b-2) _apply_stop_loss 실패 후 stoploss_retry 상태에서 다음 사이클이 get_order_status 없이 손절 재시도를 성공하는지 검증."""
    om = OrderManager("data/test_orders_p0.json")
    test_ord = {
        "uuid": "rsitrade_sell_retry",
        "user_id": "u1",
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "strategy": "rsitrade_sell",
        "stop_price": 50000.0,
        "volume": 1.0,
        "filled_volume": 0.0,
        "status": "wait",
        "next_check_at": 0.0,
    }
    om.orders = [test_ord]
    om._orders_by_uuid = {test_ord["uuid"]: test_ord}
    om._uuid_set = {test_ord["uuid"]}

    mock_ex = MagicMock()
    mock_ex.is_market_open = MagicMock(return_value=True)
    mock_ex.supports_reserved_orders = False
    mock_ex.round_volume = MagicMock(side_effect=lambda v: v)
    mock_ex.adjust_price_to_tick = MagicMock(side_effect=lambda p, t: p)

    mock_ex_adapter = MagicMock()
    mock_ex_adapter.get_exchange = MagicMock(return_value=mock_ex)
    mock_ex_adapter.cancel_order = AsyncMock(return_value=True)
    mock_ex_adapter.get_ticker = AsyncMock(return_value={"trade_price": 48000.0})
    mock_ex_adapter.get_order_status = AsyncMock(return_value={"state": "wait", "executed_volume": 0.0})
    # 1차 사이클: 3회 실패 -> 2차 사이클: 성공
    mock_ex_adapter.create_order = AsyncMock(
        side_effect=[
            None, None, None,
            {"uuid": "sl_new_uuid"},
        ]
    )

    with patch("core.order_sync._get_app_context", return_value=(om, None, mock_ex_adapter, None)), \
         patch("core.order_sync._call_append_operational_event"), \
         patch("core.order_sync.asyncio.sleep", new=AsyncMock()), \
         patch("main._spawn_bg"):
        # 1차 사이클: 손절 발동 후 create_order 실패 -> stoploss_retry 전환
        await order_sync.sync_orders(mock_app)
        assert test_ord["status"] == "stoploss_retry"
        assert om.has_order("rsitrade_sell_retry")

        # next_check_at 도래 시뮬레이션 후 2차 사이클 실행
        test_ord["next_check_at"] = 0.0
        mock_ex_adapter.get_order_status.reset_mock()
        await order_sync.sync_orders(mock_app)

        # stoploss_retry는 get_order_status를 거치지 않고 바로 손절 재시도해야 함
        mock_ex_adapter.get_order_status.assert_not_called()
        assert not om.has_order("rsitrade_sell_retry")
        assert om.has_order("sl_new_uuid")
        sl_ord = om.get_order("sl_new_uuid")
        assert sl_ord["strategy"] == "stoploss"
