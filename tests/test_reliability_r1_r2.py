import asyncio
import pandas as pd
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.order_manager import OrderManager
from core.signal_engine import SignalEngine


@pytest.mark.asyncio
async def test_replace_order_uuid_db_sequence():
    """R1: replace_order_uuid 호출 시 신규 upsert 성공 -> 구 uuid delete 순서 검증 및 upsert 실패 시 delete 미호출 검증"""
    om = OrderManager(file_path="data/test_orders_r1.json")
    om.orders = [
        {
            "uuid": "old-123",
            "user_id": "1",
            "exchange": "upbit",
            "ticker": "KRW-BTC",
            "price": 1000.0,
            "volume": 1.0,
            "status": "wait",
        }
    ]
    om._uuid_set = {"old-123"}

    call_sequence = []

    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_db.table.return_value = mock_table

    async def mock_upsert_async():
        call_sequence.append(("upsert", mock_table.upsert.call_args[0][0]["uuid"]))
        return MagicMock()

    async def mock_delete_async():
        call_sequence.append(("delete", mock_table.delete().eq.call_args[0][1]))
        return MagicMock()

    mock_table.upsert.return_value.execute_async = mock_upsert_async
    mock_table.delete.return_value.eq.return_value.execute_async = mock_delete_async

    with patch("core.order_manager.is_db_available", return_value=True), \
         patch("core.order_manager.get_db", return_value=mock_db):
        # 1. 정상 교체 테스트
        res = om.replace_order_uuid("old-123", "new-456")
        assert res is True
        # 백그라운드 태스크 완료 대기
        await om.flush_pending_writes()

        assert len(call_sequence) == 2
        assert call_sequence[0] == ("upsert", "new-456")
        assert call_sequence[1] == ("delete", "old-123")

        # 2. upsert 실패 시 delete가 호출되지 않아야 함 (구 주문 보존)
        call_sequence.clear()
        om.orders = [
            {
                "uuid": "old-789",
                "user_id": "1",
                "exchange": "upbit",
                "ticker": "KRW-BTC",
                "price": 1000.0,
                "volume": 1.0,
                "status": "wait",
            }
        ]
        om._uuid_set = {"old-789"}

        async def mock_upsert_fail():
            call_sequence.append(("upsert_fail", "new-999"))
            raise RuntimeError("Database connection lost")

        mock_table.upsert.return_value.execute_async = mock_upsert_fail

        with patch("core.db_sync.enqueue_task", new_callable=AsyncMock) as mock_enqueue:
            res_fail = om.replace_order_uuid("old-789", "new-999")
            assert res_fail is True
            await om.flush_pending_writes()

            # upsert만 시도되고 delete는 execute_async로 나가지 않음
            assert ("delete", "old-789") not in call_sequence
            # 대신 fallback enqueue_task에 순서대로 적재됨
            assert mock_enqueue.call_count == 2
            assert mock_enqueue.call_args_list[0][0][0] == "upsert"
            assert mock_enqueue.call_args_list[1][0][0] == "delete"


def test_rsi_search_price_finite_time_and_boundaries():
    """R2: 극단 RSI 목표(0.01, 99.99) 및 평탄 시계열에서도 유한 시간 내 종료 검증"""
    se = SignalEngine(MagicMock(), MagicMock())
    # 평탄한 시계열
    flat_prices = pd.Series([1000.0] * 50)

    # 1. 극단 ask 목표 (99.99)
    res_ask = se._search_price_for_target_rsi(
        close_series=flat_prices,
        current_price=1000.0,
        current_rsi=50.0,
        target_rsi=99.99,
        side="ask",
        period=14,
    )
    # 무한 루프 없이 결과 또는 None 반환
    assert res_ask is None or res_ask > 1000.0

    # 2. 극단 bid 목표 (0.01)
    res_bid = se._search_price_for_target_rsi(
        close_series=flat_prices,
        current_price=1000.0,
        current_rsi=50.0,
        target_rsi=0.01,
        side="bid",
        period=14,
    )
    assert res_bid is None or res_bid < 1000.0

    # 3. 1원 미만 저가 종목 (0.05원)
    micro_prices = pd.Series([0.05, 0.048, 0.052, 0.051, 0.049] * 10)
    res_micro = se._search_price_for_target_rsi(
        close_series=micro_prices,
        current_price=0.05,
        current_rsi=50.0,
        target_rsi=30.0,
        side="bid",
        period=14,
    )
    assert res_micro is not None
    assert 0 < res_micro <= 0.05
