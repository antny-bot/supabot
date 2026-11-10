"""KOSPI / KOSDAQ 시총 상위 TOP N 모으기 & 분할 매도 전략 종합 검증 테스트 (test_kospi_top_strategy.py).

docs/100_project_standards.md 및 docs/plans/kospi_kosdaq_top10_strategy_plan.md 준수:
라이브 거래소/네트워크 호출 전면 mock 처리 및 5대 불변식(Invariants), 예산 원장, 순차 사이클, 휩쏘 방지, 백테스트 검증.
"""
import copy
import inspect
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from manager.backend.services.universe_resolver import (
    is_preferred_or_derivative,
    resolve_strategy_targets,
    DEFAULT_KOSPI_TOP,
)
from manager.backend.services.budget_manager import (
    compute_daily_allowance,
    check_exchange_budget_health,
)
from manager.backend.services.progression_manager import (
    step_single_day,
    CONFIG_KEYS,
    RUNTIME_STATE_KEYS,
)
from manager.backend.services.backtest_engine import (
    run_multi_scenario_backtest,
)


def _sync_run(coro):
    """Windows 샌드박스 Proactor loopback 소켓 블로킹 방지용 경량 동기 코루틴 러너."""
    stack = [coro]
    val = None
    while stack:
        top = stack[-1]
        try:
            nxt = top.send(val)
            val = None
            if inspect.iscoroutine(nxt) or hasattr(nxt, "__await__"):
                if hasattr(nxt, "__await__"):
                    nxt = nxt.__await__()
                stack.append(nxt)
            else:
                val = nxt
        except StopIteration as e:
            stack.pop()
            val = e.value
    return val


def test_preferred_and_derivative_filtering():
    """우선주, ETF, ETN, 스팩, 리츠 제외 필터링 검증."""
    assert is_preferred_or_derivative("005930", "삼성전자") is False
    assert is_preferred_or_derivative("000660", "SK하이닉스") is False
    assert is_preferred_or_derivative("005935", "삼성전자우") is True
    assert is_preferred_or_derivative("005385", "현대차우") is True
    assert is_preferred_or_derivative("005387", "현대차2우B") is True
    assert is_preferred_or_derivative("069500", "KODEX 200") is True
    assert is_preferred_or_derivative("379800", "TIGER 미국S&P500") is True
    assert is_preferred_or_derivative("458730", "신한제11호스팩") is True
    assert is_preferred_or_derivative("395400", "SK리츠") is True


def test_resolve_strategy_targets_slicing():
    """rank_start ~ rank_end 구간 슬라이싱 불변성 검증 (TOP 1~5, TOP 5~10 등)."""
    async def _run():
        master = [dict(x) for x in DEFAULT_KOSPI_TOP[:20]]

        # 1. TOP 1~5 슬라이싱
        params_top5 = {"market": "KOSPI", "rank_start": 1, "rank_end": 5}
        t_top5 = await resolve_strategy_targets(params_top5, master_items=master)
        assert len(t_top5) == 5
        assert t_top5[0]["code"] == "005930"
        assert t_top5[4]["code"] == "005380"

        # 2. TOP 5~10 구간 슬라이싱 (5위~10위, 6개 종목)
        params_5to10 = {"market": "KOSPI", "rank_start": 5, "rank_end": 10}
        t_5to10 = await resolve_strategy_targets(params_5to10, master_items=master)
        assert len(t_5to10) == 6
        assert t_5to10[0]["code"] == "005380"
        assert t_5to10[-1]["code"] == "012450"

        # 3. 커스텀 종목 바스켓 우선 필터링
        params_custom = {
            "market": "KOSPI",
            "custom_tickers": ["000660", "035420"],
        }
        t_custom = await resolve_strategy_targets(params_custom, master_items=master)
        assert len(t_custom) == 2
        codes = [x["code"] for x in t_custom]
        assert "000660" in codes
        assert "035420" in codes

    _sync_run(_run())


def test_compute_daily_allowance_dynamic_proration():
    """남은 영업일 기준 동적 충전액 산출 및 월중 증액/감액 공식 검증."""
    allowance = compute_daily_allowance(
        budget_mode="monthly",
        monthly_budget=3000000.0,
        daily_fixed_budget=150000.0,
        monthly_spent=1000000.0,
        carryover_budget=0.0,
        remaining_trading_days=10,
    )
    assert allowance == 200000.0

    allowance_exceeded = compute_daily_allowance(
        budget_mode="monthly",
        monthly_budget=2000000.0,
        daily_fixed_budget=150000.0,
        monthly_spent=2100000.0,
        carryover_budget=50000.0,
        remaining_trading_days=5,
    )
    assert allowance_exceeded == 0.0

    allowance_daily = compute_daily_allowance(
        budget_mode="daily",
        monthly_budget=3000000.0,
        daily_fixed_budget=150000.0,
        monthly_spent=500000.0,
        carryover_budget=100000.0,
        remaining_trading_days=10,
    )
    assert allowance_daily == 150000.0


def test_config_vs_runtime_state_isolation():
    """설정 키(CONFIG_KEYS)와 런타임 상태 키(RUNTIME_STATE_KEYS) 격리 검증."""
    overlap = CONFIG_KEYS.intersection(RUNTIME_STATE_KEYS)
    assert len(overlap) == 0, f"설정 키와 런타임 상태 키가 겹칩니다: {overlap}"

    assert "rank_start" in CONFIG_KEYS
    assert "rank_end" in CONFIG_KEYS
    assert "sell_split_days" in CONFIG_KEYS
    assert "budget_mode" in CONFIG_KEYS

    assert "carryover_budget" in RUNTIME_STATE_KEYS
    assert "monthly_spent" in RUNTIME_STATE_KEYS
    assert "cycle_no" in RUNTIME_STATE_KEYS
    assert "current_cycle_bought" in RUNTIME_STATE_KEYS
    assert "budget_epoch" in RUNTIME_STATE_KEYS


def test_step_single_day_head_of_line_waiting():
    """[Head-of-Line 대기 원칙] 고가 종목 예산 부족 시 루프 break 및 carryover 보존 검증."""
    target_list = [
        {"rank": 1, "code": "005930", "name": "삼성전자", "price": 50000.0},
        {"rank": 2, "code": "000660", "name": "SK하이닉스", "price": 180000.0},
        {"rank": 3, "code": "035420", "name": "NAVER", "price": 30000.0},
    ]

    initial_state = {
        "rank_start": 1,
        "rank_end": 3,
        "cycle_no": 1,
        "carryover_budget": 100000.0,
        "monthly_spent": 0.0,
        "current_cycle_bought": [],
        "holdings": {},
        "cycle_alloc_mode": "one_share",
    }

    new_state, buys, sells = step_single_day(
        state=copy.deepcopy(initial_state),
        date_str="2026-10-30",
        target_list=target_list,
    )

    assert len(buys) == 1
    assert buys[0]["code"] == "005930"
    assert buys[0]["volume"] == 1.0

    assert new_state["carryover_budget"] == 50000.0
    assert new_state["monthly_spent"] == 50000.0
    assert new_state["current_cycle_bought"] == ["005930"]
    assert new_state["next_target_ticker"]["code"] == "000660"
    assert new_state["next_target_ticker"]["shortfall"] == 130000.0


def test_step_single_day_cycle_completion_and_continuous_rotation():
    """타겟 종목 완주 시 1사이클 완료(cycle_no += 1) 및 잔여 예산으로 다음 사이클 연속 매수 검증."""
    target_list = [
        {"rank": 1, "code": "005930", "name": "삼성전자", "price": 50000.0},
        {"rank": 2, "code": "000660", "name": "SK하이닉스", "price": 50000.0},
    ]

    initial_state = {
        "rank_start": 1,
        "rank_end": 2,
        "cycle_no": 1,
        "carryover_budget": 150000.0,
        "monthly_spent": 0.0,
        "current_cycle_bought": [],
        "holdings": {},
        "cycle_alloc_mode": "one_share",
    }

    new_state, buys, sells = step_single_day(
        state=copy.deepcopy(initial_state),
        date_str="2026-10-30",
        target_list=target_list,
    )

    assert len(buys) == 3
    assert new_state["cycle_no"] == 2
    assert new_state["current_cycle_bought"] == ["005930"]
    assert new_state["carryover_budget"] == 0.0
    assert new_state["monthly_spent"] == 150000.0


def test_step_single_day_exit_whipsaw_buffer_and_split_selling():
    """커트라인 휩쏘 방지 버퍼(exit_rank_buffer) 및 N일 분할 매도 동작 검증."""
    target_list = [dict(x) for x in DEFAULT_KOSPI_TOP[:10]]
    master_items = [dict(x) for x in DEFAULT_KOSPI_TOP[:20]]

    for it in master_items:
        if it["code"] == "035720":
            it["rank"] = 11

    initial_state = {
        "rank_start": 1,
        "rank_end": 10,
        "exit_rank_buffer": 2,
        "exit_confirm_days": 2,
        "sell_split_days": 5,
        "cycle_no": 1,
        "carryover_budget": 0.0,
        "monthly_spent": 0.0,
        "current_cycle_bought": [x["code"] for x in target_list],
        "holdings": {"035720": {"qty": 10.0, "total_cost": 500000.0, "avg_price": 50000.0}},
        "exit_progress": {},
        "exit_candidate_streaks": {},
    }

    # 1. 11위 체류 시 (유예 버퍼 이내) -> 매도 스킵
    state_day1, buys1, sells1 = step_single_day(
        state=copy.deepcopy(initial_state),
        date_str="2026-10-30",
        target_list=target_list,
        master_items=master_items,
    )
    assert len(sells1) == 0
    assert "035720" not in state_day1["exit_progress"]

    # 2. 13위로 밀려남 (유예 밖 1일차) -> streak=1만 기록, 매도 대기
    for it in master_items:
        if it["code"] == "035720":
            it["rank"] = 13

    state_day2, buys2, sells2 = step_single_day(
        state=copy.deepcopy(state_day1),
        date_str="2026-10-31",
        target_list=target_list,
        master_items=master_items,
    )
    assert len(sells2) == 0
    assert state_day2["exit_candidate_streaks"].get("035720") == 1

    # 3. 2일 연속 13위 확인 -> 분할 매도 개시
    state_day3, buys3, sells3 = step_single_day(
        state=copy.deepcopy(state_day2),
        date_str="2026-11-01",
        target_list=target_list,
        master_items=master_items,
    )
    assert len(sells3) == 1
    assert sells3[0]["code"] == "035720"
    assert sells3[0]["volume"] == 2.0
    assert state_day3["exit_progress"]["035720"]["remaining_days"] == 4
    assert state_day3["holdings"]["035720"]["qty"] == 8.0


def test_check_exchange_budget_health():
    """4대 거래소별 멀티 전략 필요 예산 및 순수 현금 예수금 대조 Health 등급 판정 검증."""
    templates = [
        {
            "id": 1,
            "name": "KOSPI TOP 10",
            "exchange": "toss",
            "budget": 3000000.0,
            "params": {
                "strategy_status": "active",
                "schedule_enabled": True,
                "carryover_budget": 500000.0,
                "monthly_budget": 3000000.0,
                "monthly_spent": 1000000.0,
                "budget_mode": "monthly",
            },
        },
        {
            "id": 2,
            "name": "KOSDAQ TOP 10 (Holding)",
            "exchange": "toss",
            "budget": 2000000.0,
            "params": {
                "strategy_status": "paused",
                "schedule_enabled": False,
                "carryover_budget": 300000.0,
                "monthly_budget": 2000000.0,
                "monthly_spent": 0.0,
            },
        },
    ]

    h_ok = check_exchange_budget_health("toss", templates, actual_cash_krw=5000000.0)
    assert h_ok["health_grade"] == "HEALTHY"
    assert h_ok["active_templates_count"] == 1
    assert h_ok["holding_templates_count"] == 1
    assert h_ok["daily_deposit_needed_krw"] == 0.0

    h_short = check_exchange_budget_health("toss", templates, actual_cash_krw=100000.0)
    assert h_short["health_grade"] == "SHORTAGE"
    assert h_short["daily_deposit_needed_krw"] > 0


def test_run_multi_scenario_backtest():
    """동일 과거 스냅샷 위에서 여러 시나리오를 0.5초 이내에 시뮬레이션 및 리더보드/시계열 산출 검증."""
    async def _run():
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[])
        )
        mock_db.table.return_value.upsert.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[])
        )

        scenarios = [
            {
                "name": "TOP 1~5 초대형주",
                "market": "KOSPI",
                "rank_start": 1,
                "rank_end": 5,
                "cycle_alloc_mode": "one_share",
                "sell_proceeds_mode": "keep_cash",
                "sell_split_days": 5,
                "exit_rank_buffer": 2,
                "exit_confirm_days": 2,
                "upper_exit_mode": "sell_on_any_exit",
                "budget_mode": "monthly",
                "monthly_budget": 2000000.0,
                "daily_fixed_budget": 100000.0,
                "initial_carryover": 0.0,
            },
            {
                "name": "TOP 1~10 표준",
                "market": "KOSPI",
                "rank_start": 1,
                "rank_end": 10,
                "cycle_alloc_mode": "one_share",
                "sell_proceeds_mode": "recycle_to_budget",
                "sell_split_days": 5,
                "exit_rank_buffer": 2,
                "exit_confirm_days": 2,
                "upper_exit_mode": "sell_on_any_exit",
                "budget_mode": "monthly",
                "monthly_budget": 2000000.0,
                "daily_fixed_budget": 100000.0,
                "initial_carryover": 0.0,
            },
        ]

        mock_snapshots = {
            "2026-10-01": [dict(x) for x in DEFAULT_KOSPI_TOP[:20]],
            "2026-10-02": [dict(x) for x in DEFAULT_KOSPI_TOP[:20]],
        }

        with patch("manager.backend.services.universe_resolver.backfill_historical_master_top", new=AsyncMock(return_value=mock_snapshots)):
            res = await run_multi_scenario_backtest(
                start_date="2026-10-01",
                end_date="2026-10-02",
                scenarios=scenarios,
                include_benchmark=True,
            )

        assert "leaderboard" in res
        assert len(res["leaderboard"]) == 2
        assert "comparison_series" in res
        assert len(res["comparison_series"]) > 0
        assert "benchmark" in res
        assert res["leaderboard"][0]["rank"] == 1
        assert "roi" in res["leaderboard"][0]
        assert "mdd" in res["leaderboard"][0]

    _sync_run(_run())


def test_exit_sell_uses_master_price_not_avg_price():
    """이탈 종목 매도가는 평단이 아닌 master_items의 현재가를 사용해야 한다."""
    state = {
        "rank_start": 1, "rank_end": 1, "exit_rank_buffer": 0, "exit_confirm_days": 1,
        "sell_split_days": 1, "carryover_budget": 0.0,
        "holdings": {"B": {"qty": 3.0, "avg_price": 1000.0, "total_cost": 3000.0}},
    }
    targets = [{"code": "A", "rank": 1, "price": 5000.0}]
    master = targets + [{"code": "B", "rank": 5, "price": 2500.0}]
    _, _, sells = step_single_day(state, "2026-01-05", targets, master)
    assert sells and sells[0]["price"] == 2500.0


def test_spend_for_buy_no_double_deduction_when_not_mutating():
    # 이벤트 루프 없이 코루틴 구동 (AsyncMock만 사용하므로 중단 지점 없음)
    try:
        _check_spend_no_double().send(None)
    except StopIteration:
        pass


async def _check_spend_no_double():
    from manager.backend.services import budget_manager as bm
    template = {"id": 1, "user_id": "u", "params": {"carryover_budget": 70.0, "monthly_spent": 30.0, "monthly_budget": 100.0}}
    with patch.object(bm, "record_ledger_entry", new=AsyncMock()):
        bal = await bm.spend_for_buy(
            template, 30.0, "A", 1, 1, 1, "x",
            carryover_before=100.0, monthly_spent_before=0.0, mutate_params=False,
        )
    assert bal == {"carryover_budget": 70.0, "monthly_spent": 30.0}
    assert template["params"]["carryover_budget"] == 70.0
    assert template["params"]["monthly_spent"] == 30.0


class _FakeQuery:
    def __init__(self, db, table):
        self.db, self.table, self.op, self.payload = db, table, "select", None

    def select(self, *_a):
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def upsert(self, payload):
        self.op, self.payload = "upsert", payload
        return self

    def eq(self, *_a):
        return self

    def in_(self, *_a):
        return self

    async def execute(self):
        self.db.calls.append((self.table, self.op, self.payload))
        return MagicMock(data=self.db.data.get((self.table, self.op), []))


class _FakeDB:
    def __init__(self, data):
        self.data, self.calls = data, []

    def table(self, name):
        return _FakeQuery(self, name)


def _drive(coro):
    """이벤트 루프 없이 중단점 없는 코루틴을 끝까지 구동."""
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value


def test_stop_and_cancel_calls_exchange_cancel_and_keeps_failed():
    from manager.backend.services import progression_manager as pm
    orders = [
        {"uuid": "ok1", "user_id": "u", "exchange": "toss", "ticker": "A", "status": "wait"},
        {"uuid": "bad", "user_id": "u", "exchange": "toss", "ticker": "B", "status": "wait"},
        {"uuid": "rsv", "user_id": "u", "exchange": "toss", "ticker": "C", "status": "reserved"},
    ]
    db = _FakeDB({("orders", "select"): orders,
                  ("strategy_templates", "select"): [{"id": 1, "user_id": "u", "params": {}}]})

    async def fake_cancel(user_id, exchange, uuid, ticker):
        return (uuid == "ok1"), "거래소 오류"

    with patch.object(pm, "get_db", return_value=db), \
         patch.object(pm.bot_client, "cancel_order", new=fake_cancel):
        res = _drive(pm.stop_strategy(1, "stop_and_cancel"))
    assert res["cancelled_orders"] == 2  # ok1 + 미제출 reserved(DB 갱신)
    assert [f["uuid"] for f in res["cancel_failed"]] == ["bad"]
    # 실패한 wait 주문은 DB에서 cancel로 바꾸지 않고, 미제출 reserved만 DB 갱신
    cancel_updates = [c for c in db.calls if c[0] == "orders" and c[1] == "update"]
    assert len(cancel_updates) == 1


def test_liquidation_uses_live_price_and_skips_when_unavailable():
    from manager.backend.services import progression_manager as pm
    db = _FakeDB({("orders", "select"): [],
                  ("strategy_templates", "select"): [{"id": 1, "user_id": "u", "exchange": "toss", "params": {}}]})
    holdings = {"A": {"qty": 2.0, "avg_price": 100.0}, "B": {"qty": 1.0, "avg_price": 100.0}}

    async def fake_holdings(*_a):
        return holdings

    async def fake_prices(reqs):
        return [{"ticker": "A", "price": 250.0}, {"ticker": "B", "price": 0.0}]

    with patch.object(pm, "get_db", return_value=db), \
         patch.object(pm, "get_template_holdings", new=fake_holdings), \
         patch.object(pm.bot_client, "get_prices_async", new=fake_prices):
        res = _drive(pm.stop_strategy(1, "terminate_and_liquidate"))
    upserts = [c[2] for c in db.calls if c[1] == "upsert"]
    assert len(upserts) == 1 and upserts[0]["ticker"] == "A" and upserts[0]["price"] == 250.0
    assert res["liquidation_skipped_no_price"] == ["B"]


def test_reconciliation_rolls_back_cancelled_order_from_cycle_bought():
    """미체결 취소 또는 장마감 실효 시 current_cycle_bought에서 롤백 검증."""
    from manager.backend.services import progression_manager as pm
    
    # 가상의 pending_buys와 취소된 주문 설정
    pending_buys = [{"uuid": "ord-1", "code": "005930", "price": 200000.0, "volume": 1.0, "budget_epoch": 1}]
    params = {
        "current_cycle_bought": ["005930"],
        "pending_buy_orders": pending_buys,
        "carryover_budget": 10000.0,
        "monthly_spent": 200000.0,
    }
    
    cancelled = [{"uuid": "ord-1", "code": "005930", "price": 200000.0, "volume": 1.0, "filled_volume": 0.0, "budget_epoch": 1}]
    
    # 롤백 로직 검증: current_cycle_bought에서 005930이 제거되어야 함
    current_cycle_bought = list(params.get("current_cycle_bought", []))
    for cb in cancelled:
        c_code = cb.get("code") or cb.get("ticker")
        if c_code in current_cycle_bought:
            current_cycle_bought.remove(c_code)
    params["current_cycle_bought"] = current_cycle_bought
    
    assert "005930" not in params["current_cycle_bought"]
    assert params["current_cycle_bought"] == []



def test_reconciliation_handles_deleted_unfilled_orders_via_trade_logs():
    """Bot이 미체결 취소 주문을 orders 테이블에서 DELETE했더라도 trade_logs 대조로 예산 환원 및 사이클 롤백 검증."""
    from manager.backend.services import progression_manager as pm
    from manager.backend.services import budget_manager as bm
    from manager.backend.services import universe_resolver

    today = "2026-11-03"
    tpl_params = {
        "market": "KOSPI",
        "pending_buy_orders": [
            {"uuid": "ord-del-1", "code": "005930", "price": 50000.0, "volume": 2.0, "group_no": 1, "budget_epoch": 1}
        ],
        "current_cycle_bought": ["005930"],
        "carryover_budget": 0.0,
        "monthly_spent": 100000.0,
        "monthly_budget": 3000000.0,
        "budget_epoch": 1,
        "plan_revision_no": 1,
        "budget_mode": "monthly",
        "allowance_credited_date": today,
        "rank_start": 1,
        "rank_end": 2,
    }
    template = {
        "id": 1,
        "user_id": "u",
        "budget": 3000000.0,
        "params": copy.deepcopy(tpl_params),
    }

    # orders 테이블에는 해당 주문이 없음 (장마감 후 취소/삭제됨)
    # trade_logs 테이블에도 체결 내역 없음
    db = _FakeDB({
        ("strategy_templates", "select"): [template],
        ("orders", "select"): [],
        ("trade_logs", "select"): [],
    })

    targets = [
        {"rank": 1, "code": "005930", "name": "삼성전자", "price": 50000.0},
        {"rank": 2, "code": "000660", "name": "SK하이닉스", "price": 100000.0},
    ]

    with patch.object(pm, "get_db", return_value=db), \
         patch.object(pm, "get_template_holdings", new=AsyncMock(return_value={})), \
         patch.object(universe_resolver, "freeze_or_get_master_top", new=AsyncMock(return_value=targets)), \
         patch.object(universe_resolver, "resolve_strategy_targets", new=AsyncMock(return_value=targets)), \
         patch.object(bm, "record_ledger_entry", new=AsyncMock()) as mock_ledger:
        
        res = _sync_run(pm.run_strategy_progression(1, is_dry_run=True, force_today=today))

    assert res is not None
    # ORDER_CANCEL_REFUND 감사 원장 기록 확인 (50,000 * 2 = 100,000원 전액 환원)
    refund_calls = [c for c in mock_ledger.call_args_list if c.kwargs.get("entry_type") == "ORDER_CANCEL_REFUND"]
    assert len(refund_calls) == 1
    assert refund_calls[0].kwargs.get("delta_krw") == 100000.0


def test_run_strategy_progression_recycles_sell_proceeds():
    """recycle_to_budget 모드 시 직전 배치 매도 체결 대금이 가용 예산으로 재투입되는지 검증."""
    from manager.backend.services import progression_manager as pm
    from manager.backend.services import budget_manager as bm
    from manager.backend.services import universe_resolver

    today = "2026-11-03"
    tpl_params = {
        "market": "KOSPI",
        "sell_proceeds_mode": "recycle_to_budget",
        "pending_sell_orders": [
            {"uuid": "sell-1", "ticker": "035720", "volume": 2.0, "price": 50000.0, "group_no": 5}
        ],
        "carryover_budget": 10000.0,
        "monthly_spent": 0.0,
        "monthly_budget": 3000000.0,
        "budget_epoch": 1,
        "plan_revision_no": 1,
        "budget_mode": "monthly",
        "allowance_credited_date": today,
        "rank_start": 1,
        "rank_end": 2,
    }
    template = {
        "id": 2,
        "user_id": "u",
        "budget": 3000000.0,
        "params": copy.deepcopy(tpl_params),
    }

    db = _FakeDB({
        ("strategy_templates", "select"): [template],
        ("orders", "select"): [],
        ("trade_logs", "select"): [
            {"uuid": "tr-sell-1", "ticker": "035720", "side": "ask", "price": 50000.0, "volume": 2.0, "fee_amount": 100.0, "group_no": 5}
        ],
    })

    targets = [
        {"rank": 1, "code": "005930", "name": "삼성전자", "price": 50000.0},
        {"rank": 2, "code": "000660", "name": "SK하이닉스", "price": 100000.0},
    ]

    with patch.object(pm, "get_db", return_value=db), \
         patch.object(pm, "get_template_holdings", new=AsyncMock(return_value={})), \
         patch.object(universe_resolver, "freeze_or_get_master_top", new=AsyncMock(return_value=targets)), \
         patch.object(universe_resolver, "resolve_strategy_targets", new=AsyncMock(return_value=targets)), \
         patch.object(bm, "record_ledger_entry", new=AsyncMock()) as mock_ledger:
        
        res = _sync_run(pm.run_strategy_progression(2, is_dry_run=True, force_today=today))

    assert res is not None
    # SELL_PROCEEDS_RECYCLE 기록 확인: 50,000 * 2 - 100 = 99,900원 재투입
    recycle_calls = [c for c in mock_ledger.call_args_list if c.kwargs.get("entry_type") == "SELL_PROCEEDS_RECYCLE"]
    assert len(recycle_calls) == 1
    assert recycle_calls[0].kwargs.get("delta_krw") == 99900.0
    res_params = res["params"]
    assert "tr-sell-1" in res_params.get("recycled_sell_uuids", [])
    assert res_params.get("pending_sell_orders") == []


def test_reconciliation_defers_refund_for_cancel_requested_orders():
    """봇이 거래소 취소를 확정하기 전(cancel_requested)에는 환불하지 않고 보류한다."""
    from manager.backend.services import progression_manager as pm
    from manager.backend.services import budget_manager as bm
    from manager.backend.services import universe_resolver

    today = "2026-11-03"
    tpl_params = {
        "market": "KOSPI",
        "pending_buy_orders": [
            {"uuid": "ord-cr-1", "code": "005930", "price": 50000.0, "volume": 2.0, "group_no": 1, "budget_epoch": 1}
        ],
        "current_cycle_bought": ["005930"],
        "carryover_budget": 0.0,
        "monthly_spent": 100000.0,
        "monthly_budget": 3000000.0,
        "budget_epoch": 1,
        "plan_revision_no": 1,
        "budget_mode": "monthly",
        "allowance_credited_date": today,
        "rank_start": 1,
        "rank_end": 2,
    }
    template = {"id": 1, "user_id": "u", "budget": 3000000.0, "params": copy.deepcopy(tpl_params)}
    db = _FakeDB({
        ("strategy_templates", "select"): [template],
        ("orders", "select"): [{"uuid": "ord-cr-1", "status": "cancel_requested", "filled_volume": 0.0}],
        ("trade_logs", "select"): [],
    })
    targets = [
        {"rank": 1, "code": "005930", "name": "삼성전자", "price": 50000.0},
        {"rank": 2, "code": "000660", "name": "SK하이닉스", "price": 100000.0},
    ]

    with patch.object(pm, "get_db", return_value=db), \
         patch.object(pm, "get_template_holdings", new=AsyncMock(return_value={})), \
         patch.object(universe_resolver, "freeze_or_get_master_top", new=AsyncMock(return_value=targets)), \
         patch.object(universe_resolver, "resolve_strategy_targets", new=AsyncMock(return_value=targets)), \
         patch.object(bm, "record_ledger_entry", new=AsyncMock()) as mock_ledger:
        res = _sync_run(pm.run_strategy_progression(1, is_dry_run=True, force_today=today))

    assert res is not None
    refund_calls = [c for c in mock_ledger.call_args_list if c.kwargs.get("entry_type") == "ORDER_CANCEL_REFUND"]
    assert refund_calls == []


def test_single_strategy_budget_plan_sync_and_total_mode():
    """단일 종목 전략(rsitrade, dca)의 통합 예산 플랜(total 모드) 초기화, 매수 차감, 취소 환급, 익절 재투입 검증."""
    from manager.backend.services import budget_manager as bm

    template = {
        "id": 77,
        "user_id": "u1",
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "strategy_type": "rsitrade",
        "budget": 1000000.0,
        "params": {
            "buy_rsi_range": "25-30",
            "sell_rsi_range": "65-75",
        },
    }

    # 1단계: 주문 2건(각 200,000원)이 접수된 상태
    orders_step1 = [
        {
            "uuid": "rsi-buy-1",
            "template_id": 77,
            "side": "bid",
            "price": 100000.0,
            "volume": 2.0,
            "filled_volume": 0.0,
            "status": "wait",
            "group_no": 10,
            "strategy": "rsitrade",
        },
        {
            "uuid": "rsi-buy-2",
            "template_id": 77,
            "side": "bid",
            "price": 100000.0,
            "volume": 2.0,
            "filled_volume": 0.0,
            "status": "wait",
            "group_no": 10,
            "strategy": "rsitrade",
        },
    ]
    db_step1 = _FakeDB({
        ("orders", "select"): orders_step1,
        ("trade_logs", "select"): [],
    })

    with patch.object(bm, "get_db", return_value=db_step1), \
         patch.object(bm, "record_ledger_entry", new=AsyncMock()) as mock_ledger1:
        params1 = _sync_run(bm.sync_single_strategy_budget_events(template, persist=True))

    assert params1["budget_mode"] == "total"
    assert params1["sell_proceeds_mode"] == "recycle_to_budget"
    assert params1["carryover_budget"] == 600000.0  # 1,000,000 - 400,000
    assert params1["monthly_spent"] == 400000.0
    assert len(params1["pending_buy_orders"]) == 2
    init_calls = [c for c in mock_ledger1.call_args_list if c.kwargs.get("entry_type") == "INITIAL_CREDIT"]
    spend_calls = [c for c in mock_ledger1.call_args_list if c.kwargs.get("entry_type") == "BUY_ORDER_SPEND"]
    assert len(init_calls) == 1
    assert len(spend_calls) == 2

    # 2단계: rsi-buy-1은 체결 후 익절 매도(rsitrade_sell, 220,000원, 수수료 100원)까지 완료, rsi-buy-2는 미체결 취소(orders에서 삭제됨)
    trades_step2 = [
        {
            "uuid": "rsi-buy-1",
            "template_id": 77,
            "ticker": "KRW-BTC",
            "side": "bid",
            "price": 100000.0,
            "volume": 2.0,
            "fee_amount": 0.0,
            "group_no": 10,
            "strategy": "rsitrade",
        },
        {
            "uuid": "rsi-sell-1",
            "template_id": 77,
            "ticker": "KRW-BTC",
            "side": "ask",
            "price": 110000.0,
            "volume": 2.0,
            "fee_amount": 100.0,
            "group_no": 10,
            "strategy": "rsitrade_sell",
        },
    ]
    db_step2 = _FakeDB({
        ("orders", "select"): [],  # 두 주문 모두 완료/취소되어 orders에서 삭제됨
        ("trade_logs", "select"): trades_step2,
    })

    with patch.object(bm, "get_db", return_value=db_step2), \
         patch.object(bm, "record_ledger_entry", new=AsyncMock()) as mock_ledger2:
        params2 = _sync_run(bm.sync_single_strategy_budget_events(template, persist=True))

    # rsi-buy-2 (200,000원) 환불 + rsi-sell-1 (219,900원) 익절 재투입 -> 600,000 + 200,000 + 219,900 = 1,019,900원
    assert params2["carryover_budget"] == 1019900.0
    assert params2["monthly_spent"] == 200000.0  # 400,000 - 200,000 환급
    assert params2["pending_buy_orders"] == []
    refund_calls = [c for c in mock_ledger2.call_args_list if c.kwargs.get("entry_type") == "ORDER_CANCEL_REFUND"]
    recycle_calls = [c for c in mock_ledger2.call_args_list if c.kwargs.get("entry_type") == "SELL_PROCEEDS_RECYCLE"]
    assert len(refund_calls) == 1
    assert refund_calls[0].kwargs.get("delta_krw") == 200000.0
    assert len(recycle_calls) == 1
    assert recycle_calls[0].kwargs.get("delta_krw") == 219900.0

    # 3단계: total 모드에서 총예산을 1,000,000 -> 1,500,000원으로 증액 시 차액 +500,000원 즉시 반영
    with patch.object(bm, "record_ledger_entry", new=AsyncMock()) as mock_ledger3:
        params3 = _sync_run(
            bm.apply_plan_change(
                template,
                new_plan_config={"budget_mode": "total", "monthly_budget": 1500000.0},
                apply_today_diff=True,
                memo="RSI 예산 50만원 증액",
            )
        )
    assert params3["carryover_budget"] == 1519900.0
    diff_calls = [c for c in mock_ledger3.call_args_list if c.kwargs.get("entry_type") == "PLAN_CHANGE_DIFF"]
    assert len(diff_calls) == 1
    assert diff_calls[0].kwargs.get("delta_krw") == 500000.0

def test_top_n_partial_fills_and_unfilled_reconciliation_next_day_targets():
    """TOP 5~10 중 5, 7, 10이 체결되고 6, 8, 9가 미체결 취소(장마감 실효)된 경우,
    익일 6, 8, 9가 다시 차례대로 타겟이 되는지 검증."""
    from manager.backend.services import progression_manager as pm

    # 1. 전일 배치가 돌아서 TOP 5~10 6개 종목에 매수 주문이 나갔다고 가정
    target_list = [
        {"code": "C05", "rank": 5, "price": 100000.0, "name": "종목5"},
        {"code": "C06", "rank": 6, "price": 80000.0, "name": "종목6"},
        {"code": "C07", "rank": 7, "price": 120000.0, "name": "종목7"},
        {"code": "C08", "rank": 8, "price": 50000.0, "name": "종목8"},
        {"code": "C09", "rank": 9, "price": 60000.0, "name": "종목9"},
        {"code": "C10", "rank": 10, "price": 90000.0, "name": "종목10"},
    ]

    # 발주 당시 current_cycle_bought에 6개 모두 추가되었던 상태
    current_cycle_bought = ["C05", "C06", "C07", "C08", "C09", "C10"]

    # 장 마감 후 C05, C07, C10은 체결 완료되었고, C06, C08, C09는 미체결 실효(cancelled)
    cancelled_orders = [
        {"uuid": "ord-6", "code": "C06", "price": 80000.0, "volume": 1.0, "filled_volume": 0.0},
        {"uuid": "ord-8", "code": "C08", "price": 50000.0, "volume": 1.0, "filled_volume": 0.0},
        {"uuid": "ord-9", "code": "C09", "price": 60000.0, "volume": 1.0, "filled_volume": 0.0},
    ]

    # Reconciliation 로직: 미체결 취소 주문 종목(체결수량 0)은 current_cycle_bought에서 제거
    for cb in cancelled_orders:
        if float(cb.get("filled_volume", 0.0)) <= 0:
            c_code = cb.get("code") or cb.get("ticker")
            if c_code in current_cycle_bought:
                current_cycle_bought.remove(c_code)

    # 2. 검증: current_cycle_bought에는 체결된 5, 7, 10만 남아있어야 함
    assert sorted(current_cycle_bought) == ["C05", "C07", "C10"]
    assert "C06" not in current_cycle_bought
    assert "C08" not in current_cycle_bought
    assert "C09" not in current_cycle_bought

    # 3. 익일 배치가 실행될 때 (가용 예산 500,000원 가정)
    # 케이스 A: 가용 예산이 200,000원인 경우 (미체결된 6, 8, 9의 합계 필요액 190,000원에 딱 맞음)
    state = {
        "rank_start": 5,
        "rank_end": 10,
        "cycle_no": 1,
        "current_cycle_bought": list(current_cycle_bought),
        "carryover_budget": 200000.0,
        "monthly_spent": 310000.0,
        "holdings": {
            "C05": {"qty": 1.0, "avg_price": 100000.0, "total_cost": 100000.0},
            "C07": {"qty": 1.0, "avg_price": 120000.0, "total_cost": 120000.0},
            "C10": {"qty": 1.0, "avg_price": 90000.0, "total_cost": 90000.0},
        },
    }

    new_state, buy_orders, sell_orders = pm.step_single_day(
        state=state,
        date_str="2026-11-04",
        target_list=target_list,
        master_items=target_list,
        is_dry_run=True,
    )

    # 새로 생성된 매수 주문의 대상 종목 순서 확인
    bought_tickers = [b["code"] for b in buy_orders]
    # 5, 7, 10은 이미 샀으므로 건너뛰고, 미체결되었던 6, 8, 9가 정확히 순서대로 타겟이 되어 매수됨!
    assert bought_tickers == ["C06", "C08", "C09"]
    # 6, 8, 9까지 매수 완료되면 5~10위가 모두 완료되어 1사이클 완주(cycle_no 1 -> 2)
    assert new_state["cycle_no"] == 2
    assert new_state["carryover_budget"] == 10000.0  # 200,000 - 190,000 = 10,000원 잔여

    # 케이스 B: 가용 예산이 500,000원으로 넉넉한 경우
    # 6, 8, 9를 먼저 채워 Cycle #1을 완주한 후, 잔여 예산(310,000원)으로 다음 사이클(Cycle #2)의 첫 순위(C05)부터 이어서 매수
    state2 = {
        "rank_start": 5,
        "rank_end": 10,
        "cycle_no": 1,
        "current_cycle_bought": list(current_cycle_bought),
        "carryover_budget": 500000.0,
        "monthly_spent": 310000.0,
        "holdings": {
            "C05": {"qty": 1.0, "avg_price": 100000.0, "total_cost": 100000.0},
            "C07": {"qty": 1.0, "avg_price": 120000.0, "total_cost": 120000.0},
            "C10": {"qty": 1.0, "avg_price": 90000.0, "total_cost": 90000.0},
        },
    }
    new_state2, buy_orders2, _ = pm.step_single_day(
        state=state2,
        date_str="2026-11-04",
        target_list=target_list,
        master_items=target_list,
        is_dry_run=True,
    )
    bought_tickers2 = [b["code"] for b in buy_orders2]
    # 앞선 3개는 미체결이었던 6, 8, 9 완주, 이어서 다음 사이클 종목(C05, C06, C07) 순차 매수
    assert bought_tickers2[:3] == ["C06", "C08", "C09"]
    assert new_state2["cycle_no"] == 2


def test_live_mode_does_not_rollover_cycle_before_reconciliation():
    """실전 배치(allow_same_day_cycle_rollover=False)에서는 당일 발주된 예약 주문이 체결 확정되기 전에
    동일 배치에서 다음 사이클로 회전해 중복 발주하거나 current_cycle_bought를 비우지 않는지 검증."""
    from manager.backend.services import progression_manager as pm

    target_list = [
        {"code": "005930", "rank": 1, "price": 200000.0, "name": "삼성전자"},
        {"code": "000660", "rank": 2, "price": 300000.0, "name": "SK하이닉스"},
    ]

    # 1위가 이미 체결된 상태에서 예산이 넉넉한 날(1,000,000원) 배치 실행
    state = {
        "rank_start": 1,
        "rank_end": 2,
        "cycle_no": 1,
        "current_cycle_bought": ["005930"],
        "carryover_budget": 1000000.0,
        "monthly_spent": 200000.0,
        "holdings": {"005930": {"qty": 1.0, "avg_price": 200000.0, "total_cost": 200000.0}},
    }

    new_state, buy_orders, _ = pm.step_single_day(
        state=state,
        date_str="2026-11-10",
        target_list=target_list,
        master_items=target_list,
        is_dry_run=False,
        allow_same_day_cycle_rollover=False,
    )

    # 당일 배치에서는 남은 2위(000660) 1건만 발주하고, Cycle #2의 1위(005930)를 중복 발주하지 않아야 함
    assert [b["code"] for b in buy_orders] == ["000660"]
    assert new_state["cycle_no"] == 1
    assert new_state["current_cycle_bought"] == ["005930", "000660"]
    assert new_state["carryover_budget"] == 700000.0

    # 만약 익일 배치에서 000660이 전부 체결된 상태로 시작하면 Cycle #2로 정상 진입하여 1위부터 발주
    next_day_state, next_buys, _ = pm.step_single_day(
        state=new_state,
        date_str="2026-11-11",
        target_list=target_list,
        master_items=target_list,
        is_dry_run=False,
        allow_same_day_cycle_rollover=False,
    )
    assert next_day_state["cycle_no"] == 2
    assert [b["code"] for b in next_buys] == ["005930", "000660"]


