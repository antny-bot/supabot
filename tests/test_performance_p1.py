import pandas as pd
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.order_execution import execute_rsitrade_orders
from core.signal_engine import SignalEngine


@pytest.mark.asyncio
async def test_get_prices_by_rsi_batch_fetches_candles_once():
    """P1: 여러 RSI 목표가 계산 시 캔들(get_rsi)을 1회만 조회하는지 검증"""
    mock_um = MagicMock()
    mock_ea = MagicMock()
    mock_ex = MagicMock()
    mock_ex.adjust_price_to_tick.side_effect = lambda p, t: round(p, 0)
    mock_ea.get_exchange.return_value = mock_ex

    se = SignalEngine(mock_um, mock_ea)

    # 50개 캔들 데이터 모킹
    df = pd.DataFrame({
        "close": [100.0 + i for i in range(50)],
        "open": [100.0 + i for i in range(50)],
        "high": [101.0 + i for i in range(50)],
        "low": [99.0 + i for i in range(50)],
    })
    se.get_rsi = AsyncMock(return_value=(55.0, df))

    targets = [25.0, 26.0, 27.0, 28.0, 29.0, 30.0]
    prices = await se.get_prices_by_rsi("upbit", "KRW-BTC", targets, side="bid")

    # targets가 6개임에도 get_rsi는 정확히 1회만 호출됨
    assert se.get_rsi.call_count == 1
    assert len(prices) == 6
    assert all(p is not None for p in prices)


@pytest.mark.asyncio
async def test_execute_rsitrade_orders_uses_batch_rsi():
    """P1: execute_rsitrade_orders 실행 시 get_prices_by_rsi 배치가 호출되어 레그당 중복 조회가 없는지 검증"""
    mock_ea = MagicMock()
    mock_ea.create_order = AsyncMock(return_value={"uuid": "order-123"})
    mock_ex = MagicMock()
    mock_ex.supports_reserved_orders = False
    mock_ex.is_market_open.return_value = True
    mock_ex.round_volume.side_effect = lambda v: round(v, 4)
    mock_ex.requires_integer_volume.return_value = False
    mock_ea.get_exchange.return_value = mock_ex

    mock_om = MagicMock()
    mock_se = MagicMock()
    mock_se.get_prices_by_rsi = AsyncMock(return_value=[1000.0] * 5)

    user = {"preferences": {"rsi_interval": "day"}}
    bot = MagicMock()
    bot.send_message = AsyncMock()

    res = await execute_rsitrade_orders(
        exchange_adapter=mock_ea,
        order_manager=mock_om,
        signal_engine=mock_se,
        user_id="user1",
        exchange="upbit",
        ticker="KRW-BTC",
        buy_rsi_range="25-30",
        sell_rsi_range="65-70",
        count=5,
        per_order_budgets=[10000.0] * 5,
        user=user,
        group_no=1,
        bot=bot,
        notify_chat_id="123",
    )

    assert res["success"] == 5
    # get_prices_by_rsi가 1회만 호출됨
    assert mock_se.get_prices_by_rsi.call_count == 1
    assert mock_se.get_price_by_rsi.call_count == 0
