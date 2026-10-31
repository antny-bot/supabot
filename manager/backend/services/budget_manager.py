"""예산 플랜 관리, 감사 원장(budget_ledger) 및 거래소별 예수금 Health Check 전담 엔진 (budget_manager.py).

5대 불변식 중 [불변식 1] 원장-잔액 항등식과 [불변식 2] 일일 예산 충전 멱등성을 DB 및 코드 레벨에서 보장한다.
"""
import logging
import math
from datetime import datetime, timedelta, timezone

from ..db import get_db

logger = logging.getLogger("budget_manager")
KST = timezone(timedelta(hours=9))


def get_current_kst_date_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def compute_daily_allowance(
    budget_mode: str,
    monthly_budget: float,
    daily_fixed_budget: float,
    monthly_spent: float,
    carryover_budget: float,
    remaining_trading_days: int,
) -> float:
    """당일 충전액(daily_allowance) 산출 공식 (동적 재할당)."""
    if budget_mode == "daily":
        allowance = max(0.0, float(daily_fixed_budget))
        # 월간 최대 상한(monthly_budget) 캡이 설정된 경우 검증
        if monthly_budget > 0:
            unallocated_cap = max(0.0, monthly_budget - monthly_spent - carryover_budget)
            allowance = min(allowance, unallocated_cap)
        return float(allowance)

    # 기본: monthly 모드
    rem_days = max(1, int(remaining_trading_days))
    unallocated = max(0.0, float(monthly_budget) - float(monthly_spent) - float(carryover_budget))
    daily_allowance = math.floor(unallocated / rem_days)
    return float(daily_allowance)


async def record_ledger_entry(
    user_id: str,
    template_id: int,
    budget_epoch: int,
    plan_revision_no: int,
    entry_type: str,
    delta_krw: float,
    balance_after_krw: float,
    monthly_spent_after_krw: float,
    monthly_remaining_after_krw: float,
    description: str = "",
    credit_date: str = None,
    group_no: int = None,
    ticker: str = None,
    order_uuid: str = None,
) -> dict:
    """budget_ledger 테이블에 불변 감사 원장 행을 기록한다."""
    db = get_db()
    entry = {
        "user_id": str(user_id),
        "template_id": int(template_id),
        "budget_epoch": int(budget_epoch),
        "plan_revision_no": int(plan_revision_no),
        "group_no": int(group_no) if group_no is not None else None,
        "credit_date": credit_date,
        "entry_type": entry_type,
        "delta_krw": float(delta_krw),
        "balance_after_krw": float(balance_after_krw),
        "monthly_spent_after_krw": float(monthly_spent_after_krw),
        "monthly_remaining_after_krw": float(monthly_remaining_after_krw),
        "ticker": ticker,
        "order_uuid": order_uuid,
        "description": description or "",
        "created_at": datetime.now(KST).isoformat(),
    }
    try:
        await db.table("budget_ledger").insert(entry).execute()
    except Exception as e:
        logger.warning(f"Failed to insert budget_ledger entry ({entry_type}): {e}")
    return entry


async def credit_daily_allowance(
    template: dict,
    date_str: str = None,
    remaining_trading_days: int = None,
    group_no: int = None,
) -> tuple[float, dict]:
    """[불변식 2] 영업일 기준 1일 1회 일일 예산 자동 충전. 이미 충전되었으면 0원 반환."""
    if not date_str:
        date_str = get_current_kst_date_str()

    params = template.get("params") or {}
    last_credited_date = params.get("allowance_credited_date")
    budget_epoch = int(params.get("budget_epoch", 1))
    plan_rev = int(params.get("plan_revision_no", 1))

    # 이미 오늘자 충전이 완료되었는지 확인 (인메모리 + DB 유니크 방어)
    if last_credited_date == date_str:
        logger.info(f"Daily allowance already credited today ({date_str}) for template #{template['id']}")
        return 0.0, params

    # 잔여 영업일 수 산출 (미지정 시 당월 말일까지 대략의 평일 수 계산)
    if remaining_trading_days is None:
        remaining_trading_days = calculate_remaining_trading_days(date_str)

    budget_mode = params.get("budget_mode", "monthly")
    monthly_budget = float(params.get("monthly_budget", template.get("budget", 3000000.0)))
    daily_fixed = float(params.get("daily_fixed_budget", 150000.0))
    monthly_spent = float(params.get("monthly_spent", 0.0))
    carryover = float(params.get("carryover_budget", 0.0))

    # 월이 바뀌었으면 monthly_spent 리셋
    cur_month = date_str[:7]
    tracked_month = params.get("current_month")
    if tracked_month != cur_month:
        monthly_spent = 0.0
        params["current_month"] = cur_month
        params["monthly_spent"] = 0.0

    daily_allowance = compute_daily_allowance(
        budget_mode=budget_mode,
        monthly_budget=monthly_budget,
        daily_fixed_budget=daily_fixed,
        monthly_spent=monthly_spent,
        carryover_budget=carryover,
        remaining_trading_days=remaining_trading_days,
    )

    new_carryover = carryover + daily_allowance
    monthly_rem = max(0.0, monthly_budget - monthly_spent)

    desc = f"일일 영업일 예산 자동 충전 (플랜 v{plan_rev}, {budget_mode} 모드, 잔여 {remaining_trading_days}영업일 기준)"
    await record_ledger_entry(
        user_id=template["user_id"],
        template_id=template["id"],
        budget_epoch=budget_epoch,
        plan_revision_no=plan_rev,
        group_no=group_no,
        credit_date=date_str,
        entry_type="DAILY_CREDIT",
        delta_krw=daily_allowance,
        balance_after_krw=new_carryover,
        monthly_spent_after_krw=monthly_spent,
        monthly_remaining_after_krw=monthly_rem,
        description=desc,
    )

    params["carryover_budget"] = new_carryover
    params["allowance_credited_date"] = date_str
    return daily_allowance, params


async def spend_for_buy(
    template: dict,
    cost_krw: float,
    ticker: str,
    qty: float,
    group_no: int,
    cycle_no: int,
    order_uuid: str,
    rank: int = None,
    carryover_before: float | None = None,
    monthly_spent_before: float | None = None,
    mutate_params: bool = True,
) -> dict:
    """매수 주문 발주 시 가용 예산 차감 및 원장 기록.

    step_single_day가 이미 params의 예산을 차감한 경우 이중 차감을 막기 위해
    mutate_params=False와 차감 직전 잔액(carryover_before/monthly_spent_before)을 넘긴다.
    반환 dict에는 차감 후 잔액이 담긴다.
    """
    params = template.get("params") or {}
    budget_epoch = int(params.get("budget_epoch", 1))
    plan_rev = int(params.get("plan_revision_no", 1))
    monthly_budget = float(params.get("monthly_budget", template.get("budget", 3000000.0)))

    carryover = float(params.get("carryover_budget", 0.0)) if carryover_before is None else float(carryover_before)
    monthly_spent = float(params.get("monthly_spent", 0.0)) if monthly_spent_before is None else float(monthly_spent_before)

    new_carryover = max(0.0, carryover - cost_krw)
    new_monthly_spent = monthly_spent + cost_krw
    monthly_rem = max(0.0, monthly_budget - new_monthly_spent)

    rank_str = f"{rank}위 " if rank else ""
    desc = f"Batch #{group_no} Cycle #{cycle_no}: {rank_str}{ticker} {qty:g}주 매수 주문 예약 차감"

    await record_ledger_entry(
        user_id=template["user_id"],
        template_id=template["id"],
        budget_epoch=budget_epoch,
        plan_revision_no=plan_rev,
        group_no=group_no,
        entry_type="BUY_ORDER_SPEND",
        delta_krw=-cost_krw,
        balance_after_krw=new_carryover,
        monthly_spent_after_krw=new_monthly_spent,
        monthly_remaining_after_krw=monthly_rem,
        ticker=ticker,
        order_uuid=order_uuid,
        description=desc,
    )

    if mutate_params:
        params["carryover_budget"] = new_carryover
        params["monthly_spent"] = new_monthly_spent
    return {"carryover_budget": new_carryover, "monthly_spent": new_monthly_spent}


async def refund_cancelled_orders(
    template: dict,
    cancelled_orders: list[dict],
) -> dict:
    """미체결 취소된 매수 주문 환원 처리 (구 세대 epoch 오염 방지 적용)."""
    params = template.get("params") or {}
    cur_epoch = int(params.get("budget_epoch", 1))
    plan_rev = int(params.get("plan_revision_no", 1))
    monthly_budget = float(params.get("monthly_budget", template.get("budget", 3000000.0)))

    carryover = float(params.get("carryover_budget", 0.0))
    monthly_spent = float(params.get("monthly_spent", 0.0))

    for ord in cancelled_orders:
        ord_epoch = int(ord.get("budget_epoch", 1))
        uuid = ord.get("uuid", "")
        ticker = ord.get("ticker") or ord.get("code")
        price = float(ord.get("price", 0.0))
        vol = float(ord.get("volume", 0.0))
        filled = float(ord.get("filled_volume", 0.0))
        unfilled_vol = max(0.0, vol - filled)
        refund_amount = price * unfilled_vol

        if refund_amount <= 0:
            continue

        # 이전 세대 주문인 경우: 새 세대 carryover_budget에 합산하지 않고 격리 기록
        if ord_epoch < cur_epoch:
            desc = f"이전 세대(Epoch #{ord_epoch}) 미체결 취소 주문 환원 스킵 (새 세대 오염 차단, 대상 금액: {refund_amount:,.0f}원)"
            await record_ledger_entry(
                user_id=template["user_id"],
                template_id=template["id"],
                budget_epoch=cur_epoch,
                plan_revision_no=plan_rev,
                entry_type="IGNORED_PREV_EPOCH",
                delta_krw=0.0,
                balance_after_krw=carryover,
                monthly_spent_after_krw=monthly_spent,
                monthly_remaining_after_krw=max(0.0, monthly_budget - monthly_spent),
                ticker=ticker,
                order_uuid=uuid,
                description=desc,
            )
            continue

        # 현재 세대 주문 환원
        carryover += refund_amount
        monthly_spent = max(0.0, monthly_spent - refund_amount)
        monthly_rem = max(0.0, monthly_budget - monthly_spent)

        desc = f"미체결 취소 매수 주문 환원 ({ticker} {unfilled_vol:g}주 × {price:,.0f}원)"
        await record_ledger_entry(
            user_id=template["user_id"],
            template_id=template["id"],
            budget_epoch=cur_epoch,
            plan_revision_no=plan_rev,
            group_no=ord.get("group_no"),
            entry_type="ORDER_CANCEL_REFUND",
            delta_krw=refund_amount,
            balance_after_krw=carryover,
            monthly_spent_after_krw=monthly_spent,
            monthly_remaining_after_krw=monthly_rem,
            ticker=ticker,
            order_uuid=uuid,
            description=desc,
        )

    params["carryover_budget"] = carryover
    params["monthly_spent"] = monthly_spent
    return params


async def recycle_sell_proceeds(
    template: dict,
    proceeds_krw: float,
    ticker: str,
    order_uuid: str = None,
    group_no: int = None,
) -> dict:
    """이탈 종목 매도 대금 전략 예산 재투입 (recycle_to_budget 모드 시)."""
    params = template.get("params") or {}
    if params.get("sell_proceeds_mode") != "recycle_to_budget" or proceeds_krw <= 0:
        return params

    cur_epoch = int(params.get("budget_epoch", 1))
    plan_rev = int(params.get("plan_revision_no", 1))
    monthly_budget = float(params.get("monthly_budget", template.get("budget", 3000000.0)))

    carryover = float(params.get("carryover_budget", 0.0)) + proceeds_krw
    monthly_spent = float(params.get("monthly_spent", 0.0))
    monthly_rem = max(0.0, monthly_budget - monthly_spent)

    desc = f"이탈 종목({ticker}) 분할매도 체결 대금 전략 가용 예산 재투입 (+{proceeds_krw:,.0f}원)"
    await record_ledger_entry(
        user_id=template["user_id"],
        template_id=template["id"],
        budget_epoch=cur_epoch,
        plan_revision_no=plan_rev,
        group_no=group_no,
        entry_type="SELL_PROCEEDS_RECYCLE",
        delta_krw=proceeds_krw,
        balance_after_krw=carryover,
        monthly_spent_after_krw=monthly_spent,
        monthly_remaining_after_krw=monthly_rem,
        ticker=ticker,
        order_uuid=order_uuid,
        description=desc,
    )

    params["carryover_budget"] = carryover
    return params


async def apply_plan_change(
    template: dict,
    new_plan_config: dict,
    apply_today_diff: bool = False,
    memo: str = "",
) -> dict:
    """Budget Plan 수정 및 버전(revision_no) 기록, 당일 차액 보정 지원."""
    params = template.get("params") or {}
    budget_epoch = int(params.get("budget_epoch", 1))
    current_rev = int(params.get("plan_revision_no", 1))
    new_rev = current_rev + 1

    old_budget_mode = params.get("budget_mode", "monthly")
    new_budget_mode = new_plan_config.get("budget_mode", old_budget_mode)

    old_monthly_budget = float(params.get("monthly_budget", template.get("budget", 3000000.0)))
    new_monthly_budget = float(new_plan_config.get("monthly_budget", old_monthly_budget))

    old_daily_fixed = float(params.get("daily_fixed_budget", 150000.0))
    new_daily_fixed = float(new_plan_config.get("daily_fixed_budget", old_daily_fixed))

    carryover = float(params.get("carryover_budget", 0.0))
    monthly_spent = float(params.get("monthly_spent", 0.0))

    today_str = get_current_kst_date_str()
    rem_days = calculate_remaining_trading_days(today_str)

    # 신규 플랜 기준 예상 일일 충전액
    est_allowance = compute_daily_allowance(
        budget_mode=new_budget_mode,
        monthly_budget=new_monthly_budget,
        daily_fixed_budget=new_daily_fixed,
        monthly_spent=monthly_spent,
        carryover_budget=carryover,
        remaining_trading_days=rem_days,
    )

    # 1. 당일 차액 즉시 반영 옵션
    if apply_today_diff and params.get("allowance_credited_date") == today_str:
        old_est = compute_daily_allowance(
            budget_mode=old_budget_mode,
            monthly_budget=old_monthly_budget,
            daily_fixed_budget=old_daily_fixed,
            monthly_spent=monthly_spent,
            carryover_budget=carryover,
            remaining_trading_days=rem_days,
        )
        diff = est_allowance - old_est
        if diff != 0:
            carryover = max(0.0, carryover + diff)
            entry_type = "PLAN_CHANGE_DIFF" if diff > 0 else "PLAN_CAP_ADJUST"
            desc = f"플랜 변경 당일 충전액 차액 즉시 보정 (v{current_rev}→v{new_rev}, {diff:+,.0f}원)"
            await record_ledger_entry(
                user_id=template["user_id"],
                template_id=template["id"],
                budget_epoch=budget_epoch,
                plan_revision_no=new_rev,
                entry_type=entry_type,
                delta_krw=diff,
                balance_after_krw=carryover,
                monthly_spent_after_krw=monthly_spent,
                monthly_remaining_after_krw=max(0.0, new_monthly_budget - monthly_spent),
                description=desc,
            )

    # 2. 월 예산 대폭 감액 캡 조정 (monthly_spent > new_monthly_budget)
    if new_budget_mode == "monthly" and monthly_spent >= new_monthly_budget:
        if carryover > 0:
            cut_amount = carryover
            carryover = 0.0
            desc = f"월 예산 대폭 감액으로 인한 기소진 초과 이월금 전액 동결/차감 (-{cut_amount:,.0f}원)"
            await record_ledger_entry(
                user_id=template["user_id"],
                template_id=template["id"],
                budget_epoch=budget_epoch,
                plan_revision_no=new_rev,
                entry_type="PLAN_CAP_ADJUST",
                delta_krw=-cut_amount,
                balance_after_krw=carryover,
                monthly_spent_after_krw=monthly_spent,
                monthly_remaining_after_krw=0.0,
                description=desc,
            )

    # 3. 플랜 리비전 이력 기록
    revisions = params.get("budget_plan_revisions", [])
    revisions.append({
        "revision_no": new_rev,
        "budget_epoch": budget_epoch,
        "effective_from": datetime.now(KST).isoformat(),
        "budget_mode": new_budget_mode,
        "monthly_budget": new_monthly_budget,
        "daily_fixed_budget": new_daily_fixed,
        "daily_allowance_est": est_allowance,
        "carryover_at_change": carryover,
        "monthly_spent_at_change": monthly_spent,
        "remaining_days_at_change": rem_days,
        "memo": memo or f"플랜 변경 (v{current_rev} → v{new_rev})",
    })

    params["plan_revision_no"] = new_rev
    params["budget_mode"] = new_budget_mode
    params["monthly_budget"] = new_monthly_budget
    params["daily_fixed_budget"] = new_daily_fixed
    params["carryover_budget"] = carryover
    params["budget_plan_revisions"] = revisions[-50:]  # 최근 50회 보관

    return params


async def manual_topup(
    template: dict,
    amount_krw: float,
    memo: str = "",
) -> dict:
    """사용자 수동 가용 예산 추가 투입 (특별 추경)."""
    params = template.get("params") or {}
    budget_epoch = int(params.get("budget_epoch", 1))
    plan_rev = int(params.get("plan_revision_no", 1))
    monthly_budget = float(params.get("monthly_budget", template.get("budget", 3000000.0)))

    carryover = float(params.get("carryover_budget", 0.0)) + amount_krw
    monthly_spent = float(params.get("monthly_spent", 0.0))
    monthly_rem = max(0.0, monthly_budget - monthly_spent)

    desc = f"사용자 수동 가용 예산 추가 충전: {memo}" if memo else f"사용자 수동 예산 투입 (+{amount_krw:,.0f}원)"
    await record_ledger_entry(
        user_id=template["user_id"],
        template_id=template["id"],
        budget_epoch=budget_epoch,
        plan_revision_no=plan_rev,
        entry_type="MANUAL_TOPUP",
        delta_krw=amount_krw,
        balance_after_krw=carryover,
        monthly_spent_after_krw=monthly_spent,
        monthly_remaining_after_krw=monthly_rem,
        description=desc,
    )

    params["carryover_budget"] = carryover
    return params


async def reset_budget_plan(
    template: dict,
    new_config: dict,
    initial_carryover: float = 0.0,
    reset_cycle: bool = True,
    cancel_pending: bool = True,
    memo: str = "",
) -> dict:
    """Budget Plan 초기화 (새 세대 budget_epoch += 1 격리 생성)."""
    params = template.get("params") or {}
    cur_epoch = int(params.get("budget_epoch", 1))
    new_epoch = cur_epoch + 1

    budget_mode = new_config.get("budget_mode", params.get("budget_mode", "monthly"))
    monthly_budget = float(new_config.get("monthly_budget", params.get("monthly_budget", template.get("budget", 3000000.0))))
    daily_fixed = float(new_config.get("daily_fixed_budget", params.get("daily_fixed_budget", 150000.0)))

    params["budget_epoch"] = new_epoch
    params["plan_revision_no"] = 1
    params["budget_mode"] = budget_mode
    params["monthly_budget"] = monthly_budget
    params["daily_fixed_budget"] = daily_fixed
    params["carryover_budget"] = float(initial_carryover)
    params["monthly_spent"] = 0.0
    params["allowance_credited_date"] = None

    if reset_cycle:
        params["cycle_no"] = 1
        params["current_cycle_bought"] = []
        params["skipped_untradable"] = []

    # 기존 미체결 매수 주문 취소 요청
    if cancel_pending:
        db = get_db()
        try:
            await (
                db.table("orders")
                .update({"status": "cancel"})
                .eq("template_id", template["id"])
                .eq("side", "bid")
                .in_("status", ["wait", "reserved", "partial"])
                .execute()
            )
        except Exception as e:
            logger.warning(f"Failed to cancel pending orders on budget reset: {e}")

    # 리셋 마커 감사 원장 기록
    desc = f"Budget Plan 초기화 (새 세대 Epoch #{new_epoch} 시작): {memo or '새 플랜으로 재시작'}"
    await record_ledger_entry(
        user_id=template["user_id"],
        template_id=template["id"],
        budget_epoch=new_epoch,
        plan_revision_no=1,
        entry_type="RESET",
        delta_krw=float(initial_carryover),
        balance_after_krw=float(initial_carryover),
        monthly_spent_after_krw=0.0,
        monthly_remaining_after_krw=monthly_budget,
        description=desc,
    )

    revisions = params.get("budget_plan_revisions", [])
    revisions.append({
        "revision_no": 1,
        "budget_epoch": new_epoch,
        "effective_from": datetime.now(KST).isoformat(),
        "budget_mode": budget_mode,
        "monthly_budget": monthly_budget,
        "daily_fixed_budget": daily_fixed,
        "carryover_at_change": float(initial_carryover),
        "monthly_spent_at_change": 0.0,
        "memo": f"Epoch #{new_epoch} 초기화 리셋",
    })
    params["budget_plan_revisions"] = revisions[-50:]

    return params


def check_exchange_budget_health(
    exchange: str,
    templates: list[dict],
    actual_cash_krw: float,
) -> dict:
    """거래소별 Active 멀티 전략 통합 필요 예산 집계 및 실계좌 순수 현금 예수금 대조."""
    ex_upper = exchange.upper()
    active_templates = []
    holding_templates = []

    for t in templates:
        t_ex = str(t.get("exchange", "")).upper()
        if t_ex != ex_upper:
            continue
        params = t.get("params") or {}
        status = params.get("strategy_status", "active")
        sched_enabled = params.get("schedule_enabled", True)
        if status == "active" and sched_enabled:
            active_templates.append(t)
        else:
            holding_templates.append(t)

    today_str = get_current_kst_date_str()
    rem_days = calculate_remaining_trading_days(today_str)

    daily_req_total = 0.0
    monthly_rem_req_total = 0.0
    active_details = []

    for t in active_templates:
        p = t.get("params") or {}
        b_mode = p.get("budget_mode", "monthly")
        m_budget = float(p.get("monthly_budget", t.get("budget", 3000000.0)))
        d_fixed = float(p.get("daily_fixed_budget", 150000.0))
        m_spent = float(p.get("monthly_spent", 0.0))
        c_budget = float(p.get("carryover_budget", 0.0))

        est_daily = compute_daily_allowance(
            budget_mode=b_mode,
            monthly_budget=m_budget,
            daily_fixed_budget=d_fixed,
            monthly_spent=m_spent,
            carryover_budget=c_budget,
            remaining_trading_days=rem_days,
        )

        daily_req = c_budget + est_daily
        unallocated = max(0.0, m_budget - m_spent - c_budget)
        monthly_rem_req = c_budget + unallocated

        daily_req_total += daily_req
        monthly_rem_req_total += monthly_rem_req

        active_details.append({
            "template_id": t["id"],
            "name": t.get("name", f"전략 #{t['id']}"),
            "status": "active",
            "carryover_budget": c_budget,
            "daily_allowance_est": est_daily,
            "daily_required": daily_req,
            "monthly_remaining_required": monthly_rem_req,
        })

    holding_details = []
    holding_daily_req_total = 0.0
    for t in holding_templates:
        p = t.get("params") or {}
        c_budget = float(p.get("carryover_budget", 0.0))
        holding_daily_req_total += c_budget
        holding_details.append({
            "template_id": t["id"],
            "name": t.get("name", f"전략 #{t['id']}"),
            "status": "holding",
            "carryover_budget": c_budget,
        })

    daily_shortfall = max(0.0, daily_req_total - actual_cash_krw)
    monthly_shortfall = max(0.0, monthly_rem_req_total - actual_cash_krw)

    if daily_shortfall > 0:
        health_grade = "SHORTAGE"
        health_message = f"🚨 당일 실행 위해 최소 +{daily_shortfall:,.0f}원 즉시 입금 필요"
    elif monthly_shortfall > 0:
        health_grade = "WARNING"
        health_message = f"당일 가능 · 월말 완주 위해 +{monthly_shortfall:,.0f}원 추가 입금 필요"
    else:
        health_grade = "HEALTHY"
        surplus = actual_cash_krw - monthly_rem_req_total
        health_message = f"충분 (여유 +{surplus:,.0f}원)"

    return {
        "exchange": ex_upper,
        "actual_cash_krw": actual_cash_krw,
        "health_grade": health_grade,
        "health_message": health_message,
        "daily_required_krw": daily_req_total,
        "monthly_remaining_required_krw": monthly_rem_req_total,
        "daily_deposit_needed_krw": daily_shortfall,
        "monthly_deposit_needed_krw": monthly_shortfall,
        "active_templates_count": len(active_templates),
        "holding_templates_count": len(holding_templates),
        "active_templates": active_details,
        "holding_templates": holding_details,
        "holding_daily_required_krw": holding_daily_req_total,
    }


def calculate_remaining_trading_days(from_date_str: str) -> int:
    """당월 말일까지의 남은 영업일(평일) 수를 산출한다 (오늘 포함)."""
    try:
        cur_dt = datetime.strptime(from_date_str, "%Y-%m-%d").date()
    except Exception:
        cur_dt = datetime.now(KST).date()

    year = cur_dt.year
    month = cur_dt.month
    if month == 12:
        next_month_first = cur_dt.replace(year=year + 1, month=1, day=1)
    else:
        next_month_first = cur_dt.replace(month=month + 1, day=1)
    last_day = (next_month_first - timedelta(days=1)).day

    count = 0
    d = cur_dt.day
    while d <= last_day:
        check_dt = cur_dt.replace(day=d)
        if check_dt.weekday() < 5:  # 월~금
            count += 1
        d += 1

    return max(1, count)
