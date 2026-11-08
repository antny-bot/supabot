"""전략 예산 원장(budget_ledger) 및 가용 예산 차감/정산 공용 모듈 (budget_ledger.py).

봇 컨테이너(src/)와 웹 매니저(manager/) 간 아키텍처 분리 원칙을 준수하며,
Supabase의 budget_ledger 테이블 감사 원장 기록과 strategy_templates.params
(carryover_budget, monthly_spent)의 안전한 갱신을 수행합니다.
"""
from datetime import datetime, timezone, timedelta
import logging

from core.db import get_db, is_db_available

_log = logging.getLogger("budget_ledger")
KST = timezone(timedelta(hours=9))


async def record_budget_spend(
    user_id: str,
    template_id: int,
    cost_krw: float,
    ticker: str,
    qty: float,
    group_no: int | None = None,
    order_uuid: str | None = None,
    description: str | None = None,
) -> dict | None:
    """매수 주문 접수 시 가용 예산(carryover_budget) 차감 및 BUY_ORDER_SPEND 원장 행 기록.

    최신 params를 다시 읽어 다른 키를 보존하고 필요한 키만 갱신합니다 (원자성 확보).
    """
    if not is_db_available() or template_id is None or cost_krw <= 0:
        return None

    cost_krw = float(cost_krw)
    try:
        db = get_db()
        tpl_res = await db.table("strategy_templates").select("params,budget,user_id").eq("id", int(template_id)).execute_async()
        if not tpl_res or not tpl_res.data:
            _log.error("Template %s not found for budget spend", template_id)
            return None

        tpl = tpl_res.data[0]
        params = dict(tpl.get("params") or {})
        b_mode = str(params.get("budget_mode") or "").lower()
        if b_mode == "unlimited" or "carryover_budget" not in params:
            # 예산 관리 대상이 아님
            return None

        budget_epoch = int(params.get("budget_epoch", 1))
        plan_rev = int(params.get("plan_revision_no", 1))
        monthly_budget = float(params.get("monthly_budget", tpl.get("budget", 3000000.0) or 3000000.0))

        carryover = float(params.get("carryover_budget", 0.0))
        monthly_spent = float(params.get("monthly_spent", 0.0))

        new_carryover = max(0.0, carryover - cost_krw)
        new_monthly_spent = monthly_spent + cost_krw
        monthly_rem = max(0.0, monthly_budget - new_monthly_spent)

        desc = description or f"DCA 매수 주문 예약 차감: {ticker} {qty:g}주 ({cost_krw:,.0f}원)"

        entry = {
            "user_id": str(tpl.get("user_id") or user_id),
            "template_id": int(template_id),
            "budget_epoch": budget_epoch,
            "plan_revision_no": plan_rev,
            "group_no": int(group_no) if group_no is not None else None,
            "credit_date": datetime.now(KST).strftime("%Y-%m-%d"),
            "entry_type": "BUY_ORDER_SPEND",
            "delta_krw": -cost_krw,
            "balance_after_krw": new_carryover,
            "monthly_spent_after_krw": new_monthly_spent,
            "monthly_remaining_after_krw": monthly_rem,
            "ticker": ticker,
            "order_uuid": order_uuid,
            "description": desc,
            "created_at": datetime.now(KST).isoformat(),
        }

        try:
            await db.table("budget_ledger").insert(entry).execute_async()
        except Exception as le:
            _log.error("Failed to insert budget_ledger entry (BUY_ORDER_SPEND) for template %s: %s", template_id, le)

        # 차감 대상 키만 갱신
        params["carryover_budget"] = new_carryover
        params["monthly_spent"] = new_monthly_spent
        await db.table("strategy_templates").update({"params": params}).eq("id", int(template_id)).execute_async()

        return {"carryover_budget": new_carryover, "monthly_spent": new_monthly_spent}
    except Exception as e:
        _log.error("Failed to record budget spend for template %s: %s", template_id, e, exc_info=True)
        raise e


async def record_budget_adjust(
    user_id: str,
    template_id: int,
    diff_krw: float,
    ticker: str,
    qty: float,
    group_no: int | None = None,
    order_uuid: str | None = None,
    description: str | None = None,
) -> dict | None:
    """시장가 체결 후 실제 소요 금액과 당초 차감액의 차이(diff_krw = 실제 - 추정)를 정산하고 BUY_ORDER_ADJUST 기록.

    diff_krw > 0: 실제 체결액이 더 커서 추가 차감 필요 (delta = -diff_krw)
    diff_krw < 0: 실제 체결액이 더 적어 환원 필요 (delta = +abs(diff_krw))
    """
    if not is_db_available() or template_id is None or round(diff_krw) == 0:
        return None

    diff_krw = float(diff_krw)
    delta_krw = -diff_krw

    try:
        db = get_db()
        tpl_res = await db.table("strategy_templates").select("params,budget,user_id").eq("id", int(template_id)).execute_async()
        if not tpl_res or not tpl_res.data:
            _log.error("Template %s not found for budget adjust", template_id)
            return None

        tpl = tpl_res.data[0]
        params = dict(tpl.get("params") or {})
        b_mode = str(params.get("budget_mode") or "").lower()
        if b_mode == "unlimited" or "carryover_budget" not in params:
            return None

        budget_epoch = int(params.get("budget_epoch", 1))
        plan_rev = int(params.get("plan_revision_no", 1))
        monthly_budget = float(params.get("monthly_budget", tpl.get("budget", 3000000.0) or 3000000.0))

        carryover = float(params.get("carryover_budget", 0.0))
        monthly_spent = float(params.get("monthly_spent", 0.0))

        new_carryover = max(0.0, carryover + delta_krw)
        new_monthly_spent = max(0.0, monthly_spent - delta_krw)
        monthly_rem = max(0.0, monthly_budget - new_monthly_spent)

        action_str = "추가 차감" if diff_krw > 0 else "잔액 환원"
        desc = description or f"DCA 시장가 체결 정산 ({action_str}): {ticker} {qty:g}주 (차액 {abs(diff_krw):,.0f}원)"

        entry = {
            "user_id": str(tpl.get("user_id") or user_id),
            "template_id": int(template_id),
            "budget_epoch": budget_epoch,
            "plan_revision_no": plan_rev,
            "group_no": int(group_no) if group_no is not None else None,
            "credit_date": datetime.now(KST).strftime("%Y-%m-%d"),
            "entry_type": "BUY_ORDER_ADJUST",
            "delta_krw": delta_krw,
            "balance_after_krw": new_carryover,
            "monthly_spent_after_krw": new_monthly_spent,
            "monthly_remaining_after_krw": monthly_rem,
            "ticker": ticker,
            "order_uuid": order_uuid,
            "description": desc,
            "created_at": datetime.now(KST).isoformat(),
        }

        try:
            await db.table("budget_ledger").insert(entry).execute_async()
        except Exception as le:
            _log.error("Failed to insert budget_ledger entry (BUY_ORDER_ADJUST) for template %s: %s", template_id, le)

        params["carryover_budget"] = new_carryover
        params["monthly_spent"] = new_monthly_spent
        await db.table("strategy_templates").update({"params": params}).eq("id", int(template_id)).execute_async()

        return {"carryover_budget": new_carryover, "monthly_spent": new_monthly_spent}
    except Exception as e:
        _log.error("Failed to record budget adjust for template %s: %s", template_id, e, exc_info=True)
        raise e
