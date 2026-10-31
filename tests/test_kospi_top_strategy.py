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
