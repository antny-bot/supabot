"""전략 진행 관리, 순수 상태 전이 함수 및 Supabase 주문 업로드 엔진 (progression_manager.py).

실전 스케줄러 배치와 백테스트 시뮬레이터가 100% 동일한 step_single_day 순수 함수를 공유하여
동작 차이 및 버그를 원천 차단한다.
"""
import asyncio
import math
import time
import uuid
import logging
from datetime import datetime, timedelta, timezone

from ..db import get_db
from ..bot_client import notify
from . import universe_resolver
from . import budget_manager

logger = logging.getLogger("progression_manager")
KST = timezone(timedelta(hours=9))

# 템플릿별 동시 실행 방지 Lock (불변식 보장)
_template_locks: dict[int, asyncio.Lock] = {}

# [불변식 5] 설정 키 vs 런타임 상태 키 정의
CONFIG_KEYS = {
    "market", "rank_start", "rank_end", "top_n", "upper_exit_mode",
    "exit_rank_buffer", "exit_confirm_days", "exclude_preferred",
    "sell_split_days", "cycle_alloc_mode", "cycle_target_krw",
    "sell_proceeds_mode", "is_dry_run", "budget_mode", "monthly_budget",
    "daily_fixed_budget", "trading_days_per_month", "order_price_mode",
    "schedule_enabled", "strategy_status", "schedule_time", "custom_tickers",
}

RUNTIME_STATE_KEYS = {
    "budget_epoch", "plan_revision_no", "budget_plan_revisions",
    "last_run_date", "daily_batch_state", "allowance_credited_date",
    "retry_after_ts", "last_group_no", "current_month", "monthly_spent",
    "cycle_no", "carryover_budget", "current_cycle_bought", "skipped_untradable",
    "exit_candidate_streaks", "next_target_ticker", "last_status_message",
    "pending_buy_orders", "pending_sell_orders", "last_top_tickers",
    "exit_progress", "history", "holdings",
}


def get_template_lock(template_id: int) -> asyncio.Lock:
    if template_id not in _template_locks:
        _template_locks[template_id] = asyncio.Lock()
    return _template_locks[template_id]


async def get_template_holdings(user_id: str, template_id: int) -> dict[str, dict]:
    """Supabase trade_logs 테이블을 기준으로 전략 전용 보유 수량 및 평단가 산출."""
    db = get_db()
    holdings = {}
    try:
        res = (
            await db.table("trade_logs")
            .select("ticker,side,price,volume,fee_amount")
            .eq("template_id", template_id)
            .execute()
        )
        trades = res.data or []
        for tr in trades:
            ticker = tr["ticker"]
            side = tr["side"]
            price = float(tr["price"])
            vol = float(tr["volume"])
            fee = float(tr.get("fee_amount") or 0.0)

            if ticker not in holdings:
                holdings[ticker] = {"qty": 0.0, "total_cost": 0.0, "avg_price": 0.0}

            h = holdings[ticker]
            if side == "bid":
                h["total_cost"] += (price * vol) + fee
                h["qty"] += vol
            else:
                if h["qty"] > 0:
                    unit_cost = h["total_cost"] / h["qty"]
                    h["qty"] = max(0.0, h["qty"] - vol)
                    h["total_cost"] = max(0.0, h["qty"] * unit_cost)

        for ticker, h in list(holdings.items()):
            if h["qty"] <= 1e-6:
                holdings.pop(ticker, None)
            else:
                h["avg_price"] = h["total_cost"] / h["qty"] if h["qty"] > 0 else 0.0
    except Exception as e:
        logger.warning(f"Failed to fetch template holdings from trade_logs: {e}")

    return holdings


def step_single_day(
    state: dict,
    date_str: str,
    target_list: list[dict],
    master_items: list[dict] = None,
    price_map: dict[str, float] = None,
    is_dry_run: bool = False,
) -> tuple[dict, list[dict], list[dict]]:
    """순수 상태 전이 함수 (Pure State Transition Function).

    실전 일일 배치와 백테스트 시뮬레이터 모두 이 함수를 동일하게 호출한다.
    반환값: (갱신된 state, 당일 매수 주문 리스트, 당일 매도 주문 리스트)
    """
    if price_map is None:
        price_map = {}
    if master_items is None:
        master_items = target_list

    master_rank_map = {item["code"]: item["rank"] for item in master_items}
    for item in target_list:
        if item["code"] not in price_map:
            price_map[item["code"]] = float(item["price"])

    # 설정값 추출
    rank_start = int(state.get("rank_start", 1))
    rank_end = int(state.get("rank_end", state.get("top_n", 10)))
    upper_exit_mode = state.get("upper_exit_mode", "sell_on_any_exit")
    exit_rank_buffer = int(state.get("exit_rank_buffer", 2))
    exit_confirm_days = int(state.get("exit_confirm_days", 2))
    sell_split_days = int(state.get("sell_split_days", 5))
    cycle_alloc_mode = state.get("cycle_alloc_mode", "one_share")
    cycle_target_krw = float(state.get("cycle_target_krw", 300000.0))

    # 런타임 상태 추출
    group_no = int(state.get("last_group_no", 0)) + 1
    cycle_no = int(state.get("cycle_no", 1))
    carryover_budget = float(state.get("carryover_budget", 0.0))
    monthly_spent = float(state.get("monthly_spent", 0.0))
    current_cycle_bought = list(state.get("current_cycle_bought", []))
    skipped_untradable = list(state.get("skipped_untradable", []))
    exit_candidate_streaks = dict(state.get("exit_candidate_streaks", {}))
    exit_progress = dict(state.get("exit_progress", {}))
    holdings = dict(state.get("holdings", {}))  # {ticker: {"qty": ..., "avg_price": ...}}

    target_codes = [t["code"] for t in target_list]
    target_code_set = set(target_codes)

    sell_orders = []
    buy_orders = []

    # =========================================================================
    # [1단계: 나눠 팔기] 이탈 종목 판별 및 N일 분할 매도
    # =========================================================================
    held_tickers = [t for t, h in holdings.items() if h.get("qty", 0) > 0]
    
    for code in held_tickers:
        cur_rank = master_rank_map.get(code, 9999)
        net_qty = holdings[code]["qty"]
        cur_price = price_map.get(code, holdings[code].get("avg_price", 1000.0))

        # 1-1. 타겟 구간 내부로 복귀한 경우 -> 분할 매도 즉시 해제
        if code in target_code_set:
            if code in exit_progress:
                exit_progress.pop(code, None)
            if code in exit_candidate_streaks:
                exit_candidate_streaks.pop(code, None)
            continue

        # 1-2. 상위 승격(rank < rank_start) 시 hold_on_promotion 옵션 적용
        if cur_rank < rank_start and upper_exit_mode == "hold_on_promotion":
            # 상위 순위 승격 시 매도하지 않고 보유 유지
            if code in exit_progress:
                exit_progress.pop(code, None)
            if code in exit_candidate_streaks:
                exit_candidate_streaks.pop(code, None)
            continue

        # 1-3. 휩쏘 방지: 유예 순위 버퍼 (rank <= rank_end + exit_rank_buffer)
        if cur_rank <= (rank_end + exit_rank_buffer) and cur_rank >= rank_start:
            # 유예 범위 내 체류 -> 매도 보류, 스트릭 리셋
            if code in exit_candidate_streaks:
                exit_candidate_streaks.pop(code, None)
            continue

        # 1-4. 유예 범위 밖 이탈 확정 검사
        if code not in exit_progress:
            streak = exit_candidate_streaks.get(code, 0) + 1
            exit_candidate_streaks[code] = streak
            if streak >= exit_confirm_days:
                # 분할 매도 큐 등록
                exit_progress[code] = {
                    "total_days": sell_split_days,
                    "remaining_days": sell_split_days,
                    "initial_qty": net_qty,
                    "first_exit_date": date_str,
                    "last_sell_date": date_str,
                }
                exit_candidate_streaks.pop(code, None)

        # 1-5. 분할 매도 발주
        if code in exit_progress:
            prog = exit_progress[code]
            rem_days = max(1, prog.get("remaining_days", 1))
            # 당일 매도 수량 = min(net_qty, max(1, ceil(net_qty / remaining_days)))
            sell_qty = min(net_qty, max(1.0, math.ceil(net_qty / rem_days)))
            if sell_qty > 0:
                sell_ord = {
                    "uuid": str(uuid.uuid4()),
                    "code": code,
                    "ticker": code,
                    "side": "ask",
                    "price": cur_price,
                    "volume": sell_qty,
                    "group_no": group_no,
                    "cycle_no": cycle_no,
                    "remaining_days": rem_days - 1,
                    "total_days": prog.get("total_days", sell_split_days),
                    "created_at": time.time(),
                }
                sell_orders.append(sell_ord)

                # 상태 갱신
                prog["remaining_days"] = rem_days - 1
                prog["last_sell_date"] = date_str
                holdings[code]["qty"] = max(0.0, net_qty - sell_qty)
                
                # 가상 실행이면 현금 회수
                if is_dry_run and state.get("sell_proceeds_mode") == "recycle_to_budget":
                    carryover_budget += sell_qty * cur_price

                if holdings[code]["qty"] <= 1e-6 or prog["remaining_days"] <= 0:
                    exit_progress.pop(code, None)

    # =========================================================================
    # [2단계: 모으기] 프리징 TOP N 순차 사이클 매수
    # =========================================================================
    waiting_next = None
    status_summary = ""

    # 타겟 구간 순회 (예산이 허용하는 한 연속 사이클 회전)
    max_loops = 50  # 무한루프 방지
    loop_count = 0

    while loop_count < max_loops:
        loop_count += 1

        for t_item in target_list:
            code = t_item["code"]
            price = price_map.get(code, float(t_item["price"]))
            rank = t_item["rank"]
            name = t_item.get("name", code)

            if code in current_cycle_bought:
                continue

            # 목표 매수 수량 산출
            if cycle_alloc_mode == "target_amount":
                target_qty = max(1.0, round(cycle_target_krw / max(1.0, price)))
            else:
                target_qty = 1.0  # one_share 기본

            cost = target_qty * price
            if carryover_budget + 1e-6 >= cost:
                # 매수 발주 가능
                buy_ord = {
                    "uuid": str(uuid.uuid4()),
                    "code": code,
                    "ticker": code,
                    "name": name,
                    "rank": rank,
                    "side": "bid",
                    "price": price,
                    "volume": target_qty,
                    "group_no": group_no,
                    "cycle_no": cycle_no,
                    "cost": cost,
                    "created_at": time.time(),
                }
                buy_orders.append(buy_ord)
                carryover_budget -= cost
                monthly_spent += cost
                current_cycle_bought.append(code)

                # holdings 갱신
                if code not in holdings:
                    holdings[code] = {"qty": 0.0, "total_cost": 0.0, "avg_price": 0.0}
                h = holdings[code]
                h["total_cost"] += cost
                h["qty"] += target_qty
                h["avg_price"] = h["total_cost"] / h["qty"]
            else:
                # [Head-of-Line 대기 원칙]: 가용 예산 부족 종목 도달 시 즉시 Break 후 이월
                shortfall = cost - carryover_budget
                waiting_next = {
                    "rank": rank,
                    "code": code,
                    "name": name,
                    "price": price,
                    "target_qty": target_qty,
                    "required_krw": cost,
                    "carryover": carryover_budget,
                    "shortfall": shortfall,
                }
                status_summary = f"Cycle #{cycle_no}: {rank}위 {name}({cost:,.0f}원) 예산 부족 대기 (가용잔액 {carryover_budget:,.0f}원, 부족액 {shortfall:,.0f}원)"
                break  # for loop break

        if waiting_next:
            break  # while loop break

        # 사이클 완주 여부 확인
        target_codes = [t["code"] for t in target_list if t["code"] not in skipped_untradable]
        if target_codes and all(c in current_cycle_bought for c in target_codes):
            # 1사이클 완주! 다음 사이클로 즉시 이어서 회전
            cycle_no += 1
            current_cycle_bought = []
            skipped_untradable = []
            if carryover_budget <= 1000.0:
                break
        else:
            break

    if not waiting_next and buy_orders:
        status_summary = f"Cycle #{cycle_no}: {len(buy_orders)}개 종목 매수 완료 후 사이클 순항 중 (가용잔액 {carryover_budget:,.0f}원)"
    elif not waiting_next and not buy_orders:
        status_summary = f"Cycle #{cycle_no}: 매수 대기 중 (가용잔액 {carryover_budget:,.0f}원)"

    # 갱신된 상태 구성
    state["last_group_no"] = group_no
    state["cycle_no"] = cycle_no
    state["carryover_budget"] = carryover_budget
    state["monthly_spent"] = monthly_spent
    state["current_cycle_bought"] = current_cycle_bought
    state["skipped_untradable"] = skipped_untradable
    state["exit_candidate_streaks"] = exit_candidate_streaks
    state["exit_progress"] = exit_progress
    state["holdings"] = holdings
    state["next_target_ticker"] = waiting_next
    state["last_status_message"] = status_summary
    state["last_run_date"] = date_str

    return state, buy_orders, sell_orders


async def run_strategy_progression(
    template_id: int,
    is_dry_run: bool = False,
    force_today: str = None,
) -> dict:
    """매니저 백엔드 일일 스케줄러 및 즉시 실행 API 진입점."""
    lock = get_template_lock(template_id)
    if lock.locked():
        raise RuntimeError("이미 해당 전략의 배치가 실행 중입니다 (동시 실행 방지).")

    async with lock:
        db = get_db()
        t_res = await db.table("strategy_templates").select("*").eq("id", template_id).execute()
        if not t_res.data:
            raise ValueError(f"Template #{template_id} not found")

        template = t_res.data[0]
        params = template.get("params") or {}
        today_str = force_today or budget_manager.get_current_kst_date_str()

        # 1. 대상 시장 TOP 50 프리징 확보
        market = params.get("market", "KOSPI")
        master_items = await universe_resolver.freeze_or_get_master_top(market, date_str=today_str, max_n=50)

        # 2. 전략 타겟 구간 종목 슬라이싱
        targets = await universe_resolver.resolve_strategy_targets(params, date_str=today_str, master_items=master_items)

        # 3. 실보유 수량 동기화
        holdings = await get_template_holdings(template["user_id"], template_id)
        params["holdings"] = holdings

        # 4. 직전 배치 미체결 취소 주문 정산 (Reconciliation)
        pending_buys = params.get("pending_buy_orders", [])
        if pending_buys:
            # orders 테이블에서 실제 상태 확인
            order_uuids = [o["uuid"] for o in pending_buys if "uuid" in o]
            if order_uuids:
                ord_res = await db.table("orders").select("uuid,status,filled_volume,price,volume").in_("uuid", order_uuids).execute()
                status_map = {o["uuid"]: o for o in (ord_res.data or [])}
                cancelled = []
                for pb in pending_buys:
                    s_info = status_map.get(pb["uuid"])
                    if s_info and s_info.get("status") == "cancel":
                        pb["filled_volume"] = s_info.get("filled_volume", 0.0)
                        cancelled.append(pb)
                if cancelled:
                    await budget_manager.refund_cancelled_orders(template, cancelled)

        # 5. 일일 예산 충전 (1일 1회 불변식 2 보장)
        rem_days = budget_manager.calculate_remaining_trading_days(today_str)
        group_no = int(params.get("last_group_no", 0)) + 1
        daily_allowance, params = await budget_manager.credit_daily_allowance(
            template=template,
            date_str=today_str,
            remaining_trading_days=rem_days,
            group_no=group_no,
        )

        # 6. 순수 상태 전이 함수 실행 (step_single_day)
        prev_carryover = float(params.get("carryover_budget", 0.0))
        new_params, buy_orders, sell_orders = step_single_day(
            state=params,
            date_str=today_str,
            target_list=targets,
            master_items=master_items,
            is_dry_run=is_dry_run or params.get("is_dry_run", False),
        )

        # 7. 결정된 매수/매도 주문을 Supabase orders 테이블에 업로드 (status='reserved')
        # [불변식 3] 당일 주문 멱등성 보장
        created_orders = []
        user_id = str(template["user_id"])
        exchange = str(template.get("exchange", "toss")).lower()
        now_ts = time.time()
        cur_epoch = int(new_params.get("budget_epoch", 1))

        # 매도 주문 업로드
        for s_ord in sell_orders:
            db_ord = {
                "uuid": s_ord["uuid"],
                "user_id": user_id,
                "exchange": exchange,
                "ticker": s_ord["code"],
                "price": float(s_ord["price"]),
                "volume": float(s_ord["volume"]),
                "filled_volume": 0.0,
                "side": "ask",
                "strategy": "kospi_top_dca",
                "template_id": template_id,
                "group_no": group_no,
                "status": "reserved",
                "created_at": now_ts,
            }
            if not is_dry_run and not params.get("is_dry_run", False):
                await db.table("orders").upsert(db_ord).execute()
            created_orders.append(db_ord)

        # 매수 주문 업로드 및 원장 차감
        for b_ord in buy_orders:
            db_ord = {
                "uuid": b_ord["uuid"],
                "user_id": user_id,
                "exchange": exchange,
                "ticker": b_ord["code"],
                "price": float(b_ord["price"]),
                "volume": float(b_ord["volume"]),
                "filled_volume": 0.0,
                "side": "bid",
                "strategy": "kospi_top_dca",
                "template_id": template_id,
                "group_no": group_no,
                "status": "reserved",
                "created_at": now_ts,
            }
            if not is_dry_run and not params.get("is_dry_run", False):
                await db.table("orders").upsert(db_ord).execute()
                await budget_manager.spend_for_buy(
                    template=template,
                    cost_krw=b_ord["cost"],
                    ticker=b_ord["code"],
                    qty=b_ord["volume"],
                    group_no=group_no,
                    cycle_no=b_ord["cycle_no"],
                    order_uuid=b_ord["uuid"],
                    rank=b_ord.get("rank"),
                )
            created_orders.append(db_ord)

        # 8. 런타임 상태 히스토리 스냅샷 추가 (최근 90회)
        history = new_params.get("history", [])
        history.append({
            "date": today_str,
            "group_no": group_no,
            "cycle_no": new_params.get("cycle_no", 1),
            "prev_carryover": prev_carryover,
            "daily_allowance": daily_allowance,
            "available_budget": prev_carryover + daily_allowance,
            "spent_today": sum(b["cost"] for b in buy_orders),
            "end_carryover": new_params.get("carryover_budget", 0.0),
            "monthly_budget": float(new_params.get("monthly_budget", template.get("budget", 3000000.0))),
            "monthly_spent_after": new_params.get("monthly_spent", 0.0),
            "status_summary": new_params.get("last_status_message", ""),
            "top_list": targets[:10],
            "buys": buy_orders,
            "sells": sell_orders,
            "waiting_next": new_params.get("next_target_ticker"),
        })
        new_params["history"] = history[-90:]
        new_params["pending_buy_orders"] = [
            {"uuid": b["uuid"], "code": b["code"], "price": b["price"], "volume": b["volume"], "group_no": group_no, "budget_epoch": cur_epoch}
            for b in buy_orders
        ]
        new_params["pending_sell_orders"] = [
            {"uuid": s["uuid"], "code": s["code"], "price": s["price"], "volume": s["volume"], "group_no": group_no, "budget_epoch": cur_epoch}
            for s in sell_orders
        ]

        # 9. strategy_templates 테이블에 params 원자적 저장
        await db.table("strategy_templates").update({"params": new_params}).eq("id", template_id).execute()

        # 10. 봇 알림 발송
        msg_lines = [
            f"📊 [{template.get('name', 'TOP N 전략')}] Batch #{group_no} 실행 완료",
            f"• 영업일: {today_str} | Cycle #{new_params.get('cycle_no', 1)}",
            f"• 당일 충전: +{daily_allowance:,.0f}원 | 잔여 가용: {new_params.get('carryover_budget', 0.0):,.0f}원",
            f"• 매수 주문: {len(buy_orders)}건 | 매도 주문: {len(sell_orders)}건",
            f"• 상태: {new_params.get('last_status_message', '')}",
        ]
        await notify(user_id, "\n".join(msg_lines))

        return {
            "template_id": template_id,
            "group_no": group_no,
            "daily_allowance": daily_allowance,
            "buy_orders_count": len(buy_orders),
            "sell_orders_count": len(sell_orders),
            "orders": created_orders,
            "params": new_params,
        }


async def set_strategy_holding(template_id: int, is_holding: bool) -> dict:
    """전략 Active ↔ Holding (일시보류) 토글."""
    db = get_db()
    t_res = await db.table("strategy_templates").select("params").eq("id", template_id).execute()
    if not t_res.data:
        raise ValueError(f"Template #{template_id} not found")

    params = t_res.data[0].get("params") or {}
    new_status = "paused" if is_holding else "active"
    new_sched = not is_holding

    params["strategy_status"] = new_status
    params["schedule_enabled"] = new_sched

    await db.table("strategy_templates").update({"params": params}).eq("id", template_id).execute()
    return {"template_id": template_id, "strategy_status": new_status, "schedule_enabled": new_sched}


async def stop_strategy(template_id: int, mode: str) -> dict:
    """전략 중지 3단계 제어 (pause | stop_and_cancel | terminate_and_liquidate)."""
    db = get_db()
    t_res = await db.table("strategy_templates").select("*").eq("id", template_id).execute()
    if not t_res.data:
        raise ValueError(f"Template #{template_id} not found")

    template = t_res.data[0]
    params = template.get("params") or {}

    params["schedule_enabled"] = False

    if mode == "pause":
        params["strategy_status"] = "paused"
    elif mode == "stop_and_cancel":
        params["strategy_status"] = "stopped"
        params["exit_progress"] = {}
        # 미체결 주문 취소
        await (
            db.table("orders")
            .update({"status": "cancel"})
            .eq("template_id", template_id)
            .in_("status", ["wait", "reserved", "partial"])
            .execute()
        )
    elif mode == "terminate_and_liquidate":
        params["strategy_status"] = "liquidating"
        params["exit_progress"] = {}
        # 1. 미체결 매수/매도 전량 취소
        await (
            db.table("orders")
            .update({"status": "cancel"})
            .eq("template_id", template_id)
            .in_("status", ["wait", "reserved", "partial"])
            .execute()
        )
        # 2. 기보유 물량 즉시 청산 매도 주문 발주
        holdings = await get_template_holdings(template["user_id"], template_id)
        now_ts = time.time()
        for ticker, h in holdings.items():
            qty = h.get("qty", 0.0)
            if qty > 0:
                liq_ord = {
                    "uuid": str(uuid.uuid4()),
                    "user_id": str(template["user_id"]),
                    "exchange": str(template.get("exchange", "toss")).lower(),
                    "ticker": ticker,
                    "price": float(h.get("avg_price", 1000.0)),
                    "volume": float(qty),
                    "filled_volume": 0.0,
                    "side": "ask",
                    "strategy": "kospi_top_dca",
                    "template_id": template_id,
                    "status": "reserved",
                    "created_at": now_ts,
                }
                await db.table("orders").upsert(liq_ord).execute()

    await db.table("strategy_templates").update({"params": params}).eq("id", template_id).execute()
    return {"template_id": template_id, "strategy_status": params["strategy_status"], "mode": mode}
