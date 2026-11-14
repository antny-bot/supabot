"""최근 로직 보완 및 예산/정산/동기화 버그 수정 검증 테스트."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_budget_ledger_spend_sets_accounted_and_sync_does_not_double_deduct():
    """record_budget_spend가 accounted_buy_order_uuids를 기록하고 sync_single_strategy_budget_events가 이중 차감하지 않는지 검증."""
    from core import budget_ledger
    from manager.backend.services import budget_manager

    tpl_state = {
        "id": 77,
        "user_id": "u1",
        "strategy_type": "dca",
        "budget": 100000.0,
        "ticker": "005930",
        "params": {
            "budget_mode": "monthly",
            "budget_epoch": 1,
            "plan_revision_no": 1,
            "monthly_budget": 1000000.0,
            "carryover_budget": 500000.0,
            "monthly_spent": 0.0,
            "accounted_buy_order_uuids": [],
            "pending_buy_orders": [],
            "budget_plan_revisions": [{"revision_no": 1}],
        },
    }
    ledger_rows = []

    mock_db = MagicMock()

    def _table_router(name):
        t = MagicMock()
        if name == "strategy_templates":
            t.select.return_value.eq.return_value.execute_async = AsyncMock(
                return_value=MagicMock(data=[tpl_state])
            )

            async def _update_async():
                return MagicMock(data=[tpl_state])

            def _update(payload):
                if "params" in payload:
                    tpl_state["params"] = payload["params"]
                u = MagicMock()
                u.eq.return_value.execute_async = _update_async
                u.eq.return_value.execute = _update_async
                return u

            t.update.side_effect = _update
        elif name == "budget_ledger":
            def _insert(row):
                ledger_rows.append(dict(row))
                ins = MagicMock()
                ins.execute_async = AsyncMock(return_value=MagicMock(data=[row]))
                ins.execute = AsyncMock(return_value=MagicMock(data=[row]))
                return ins

            t.insert.side_effect = _insert
            t.select.return_value.eq.return_value.execute = AsyncMock(
                return_value=MagicMock(data=ledger_rows)
            )
            t.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute = AsyncMock(
                return_value=MagicMock(data=[r for r in ledger_rows if r.get("entry_type") == "ORDER_CANCEL_REFUND"])
            )
        elif name == "orders":
            t.select.return_value.eq.return_value.execute = AsyncMock(
                return_value=MagicMock(data=[{
                    "uuid": "dca-ord-1",
                    "ticker": "005930",
                    "side": "bid",
                    "price": 70000.0,
                    "volume": 2.0,
                    "filled_volume": 0.0,
                    "status": "wait",
                    "group_no": 1,
                    "reorder_of": None,
                }])
            )
        elif name == "trade_logs":
            t.select.return_value.eq.return_value.execute = AsyncMock(
                return_value=MagicMock(data=[])
            )
        return t

    mock_db.table.side_effect = _table_router

    with patch("core.budget_ledger.is_db_available", return_value=True), \
         patch("core.budget_ledger.get_db", return_value=mock_db), \
         patch("manager.backend.services.budget_manager.get_db", return_value=mock_db):
        res1 = await budget_ledger.record_budget_spend(
            user_id="u1",
            template_id=77,
            cost_krw=140000.0,
            ticker="005930",
            qty=2.0,
            group_no=1,
            order_uuid="dca-ord-1",
        )
        assert res1["carryover_budget"] == 360000.0
        assert "dca-ord-1" in tpl_state["params"]["accounted_buy_order_uuids"]

        # 매니저 sync_single_strategy_budget_events 실행 시 이중 차감되지 않아야 함
        synced_params = await budget_manager.sync_single_strategy_budget_events(tpl_state, persist=True)
        assert synced_params["carryover_budget"] == 360000.0
        assert synced_params["monthly_spent"] == 140000.0
        spend_entries = [r for r in ledger_rows if r.get("entry_type") == "BUY_ORDER_SPEND"]
        assert len(spend_entries) == 1


@pytest.mark.asyncio
async def test_refund_cancelled_orders_skips_already_refunded_in_ledger():
    """이미 budget_ledger에 ORDER_CANCEL_REFUND가 기록된 주문은 refund_cancelled_orders에서 중복 가산하지 않는다."""
    from manager.backend.services import budget_manager

    tpl = {
        "id": 88,
        "user_id": "u1",
        "budget": 500000.0,
        "params": {
            "budget_epoch": 1,
            "plan_revision_no": 1,
            "monthly_budget": 500000.0,
            "carryover_budget": 400000.0,
            "monthly_spent": 100000.0,
        },
    }
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{"order_uuid": "ord-already-refunded"}])
    )

    with patch("manager.backend.services.budget_manager.get_db", return_value=mock_db):
        updated = await budget_manager.refund_cancelled_orders(
            tpl,
            [{"uuid": "ord-already-refunded", "ticker": "005930", "price": 50000.0, "volume": 2.0, "filled_volume": 0.0, "budget_epoch": 1}],
        )
        assert updated["carryover_budget"] == 400000.0
        assert updated["monthly_spent"] == 100000.0


@pytest.mark.asyncio
async def test_db_sync_trade_logs_fallback_strips_missing_columns():
    """db_sync._process_queue에서 trade_logs insert 실패 시 template_id/group_no 제거 폴백 동작 검증."""
    from core import db_sync

    inserted_payloads = []
    mock_db = MagicMock()

    def _table(name):
        t = MagicMock()
        t.select.return_value.eq.return_value.execute_async = AsyncMock(return_value=MagicMock(data=[]))

        def _insert(payload):
            m = MagicMock()
            if "template_id" in payload or "group_no" in payload:
                m.execute_async = AsyncMock(side_effect=RuntimeError("column template_id does not exist"))
            else:
                inserted_payloads.append(dict(payload))
                m.execute_async = AsyncMock(return_value=MagicMock(data=[payload]))
            return m

        t.insert.side_effect = _insert
        return t

    mock_db.table.side_effect = _table

    orig_queue = list(db_sync._queue)
    try:
        db_sync._queue = [{
            "action": "insert",
            "table": "trade_logs",
            "key_col": "uuid",
            "key_val": "u-fallback-1",
            "data": {"uuid": "u-fallback-1", "user_id": "1", "ticker": "KRW-BTC", "template_id": 10, "group_no": 2},
        }]
        with patch("core.db_sync.test_db_connection", new=AsyncMock(return_value=True)), \
             patch("core.db_sync.get_db", return_value=mock_db), \
             patch("core.db_sync._save_queue"):
            await db_sync._process_queue()
        assert len(inserted_payloads) == 1
        assert "template_id" not in inserted_payloads[0]
        assert "group_no" not in inserted_payloads[0]
        assert len(db_sync._queue) == 0
    finally:
        db_sync._queue = orig_queue
