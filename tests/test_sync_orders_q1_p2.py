import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import main


def test_cleanup_stale_caches():
    """Q1: _cleanup_stale_caches가 활성 목록에 없는 캐시 엔트리를 제거하는지 검증"""
    main._limit_warned_orders["old-uuid-1"] = True
    main._limit_warned_orders["active-uuid"] = True
    main._reorder_failures["old-uuid-2"] = 3
    main._reorder_failures["active-uuid"] = 1
    main._status_check_failures["old-uuid-3"] = 2
    main._status_check_failures["active-uuid"] = 1

    active_uuids = {"active-uuid"}
    main._cleanup_stale_caches(active_uuids)

    assert "old-uuid-1" not in main._limit_warned_orders
    assert "old-uuid-2" not in main._reorder_failures
    assert "old-uuid-3" not in main._status_check_failures
    assert main._limit_warned_orders.get("active-uuid") is True
    assert main._reorder_failures.get("active-uuid") == 1
    assert main._status_check_failures.get("active-uuid") == 1


@pytest.mark.asyncio
async def test_handle_market_closed():
    """Q1: _handle_market_closed가 장외 종목의 상태 및 next_check_at을 갱신하는지 검증"""
    ord_dict = {"uuid": "ord-closed-1", "ticker": "005930", "status": "wait"}
    ex_mock = MagicMock()
    ex_mock.is_market_open.return_value = False
    ex_mock.next_check_timestamp.return_value = 1799999999.0

    mock_om = MagicMock()
    with patch.object(main, "order_manager", mock_om):
        res = await main._handle_market_closed(ord_dict, ex_mock)
        assert res is True
        mock_om.update_order_status.assert_called_once_with("ord-closed-1", "market_closed")
        mock_om.update_next_check_at.assert_called_once_with("ord-closed-1", 1799999999.0)


@pytest.mark.asyncio
async def test_sync_orders_parallel_concurrency_limit():
    """P2: 서로 다른 유저의 주문들에 대해 거래소 세마포어(한도 4) 내에서 병렬 조회가 수행되는지 검증"""
    mock_om = MagicMock()
    orders = [
        {"uuid": f"uuid-{i}", "user_id": f"user-{i}", "exchange": "upbit", "ticker": "KRW-BTC", "status": "wait", "next_check_at": 0.0, "filled_volume": 0.0, "volume": 1.0, "side": "bid", "price": 1000.0}
        for i in range(8)
    ]
    mock_om.orders = list(orders)
    mock_om.has_order.return_value = True

    current_concurrent = 0
    max_concurrent = 0

    async def mock_get_order_status(user_id, exchange, uuid, ticker):
        nonlocal current_concurrent, max_concurrent
        current_concurrent += 1
        max_concurrent = max(max_concurrent, current_concurrent)
        await asyncio.sleep(0.05)
        current_concurrent -= 1
        return {"state": "wait", "executed_volume": 0.0}

    mock_ea = MagicMock()
    mock_ex = MagicMock()
    mock_ex.is_market_open.return_value = True
    mock_ex.supports_reserved_orders = False
    mock_ea.get_exchange.return_value = mock_ex
    mock_ea.get_order_status = AsyncMock(side_effect=mock_get_order_status)

    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock()

    with patch.object(main, "order_manager", mock_om), \
         patch.object(main, "exchange_adapter", mock_ea), \
         patch.object(main, "_spawn_bg", MagicMock()):
        await main.sync_orders(mock_app)

    # 병렬로 실행되어 max_concurrent가 1 초과이며 세마포어 한도(4) 이내임
    assert 1 < max_concurrent <= 4
    assert mock_ea.get_order_status.call_count == 8
