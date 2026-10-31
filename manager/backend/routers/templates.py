# -*- coding: utf-8 -*-
import inspect
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import get_db
from ._auth import get_current_user
from ..bot_client import execute_grid, execute_sgrid, execute_rsitrade, execute_dca
from ..services import progression_manager, budget_manager

router = APIRouter()


def _normalize_ticker(exchange: str, ticker: str) -> str:
    t = ticker.strip().upper()
    if exchange in ("upbit", "bithumb") and "-" not in t:
        return f"KRW-{t}"
    if exchange in ("kis", "toss"):
        return t.replace("KRW-", "")
    return t


class TemplateCreate(BaseModel):
    name: str
    exchange: str
    ticker: str
    start_price: float = 0.0
    end_price: float = 0.0
    count: int = 10
    budget: float = 3000000.0
    strategy_type: str = 'grid'
    params: dict = {}

class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    exchange: Optional[str] = None
    ticker: Optional[str] = None
    start_price: Optional[float] = None
    end_price: Optional[float] = None
    count: Optional[int] = None
    budget: Optional[float] = None
    strategy_type: Optional[str] = None
    params: Optional[dict] = None

class HoldingRequest(BaseModel):
    is_holding: bool

class StopRequest(BaseModel):
    mode: str = "pause"  # pause | stop_and_cancel | terminate_and_liquidate

class BudgetPlanRequest(BaseModel):
    new_plan_config: dict
    apply_today_diff: bool = False
    memo: str = ""

class BudgetResetRequest(BaseModel):
    new_config: dict = {}
    initial_carryover: float = 0.0
    reset_cycle: bool = True
    cancel_pending: bool = True
    memo: str = ""


# ── 통합 예수금 Health Check ──────────────────────────────────────────────────

@router.get("/api/templates/budget-health")
async def api_get_budget_health(
    exchange: str = Query("toss"),
    user: dict = Depends(get_current_user),
):
    """거래소별 Active 멀티 전략 필요 예산 및 실계좌 순수 현금 예수금 대조."""
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]
    db = get_db()

    try:
        q = db.table("strategy_templates").select("*")
        if not is_admin and bot_user_id:
            q._params["user_id"] = f"eq.{bot_user_id}"
        templates = (await q.execute()).data or []

        # 실계좌 순수 현금 예수금 조회 (미수 제외 100% 현금)
        # 봇 또는 거래소 API와 연동하거나 기본값 활용
        actual_cash_krw = 5000000.0
        try:
            from ..bot_client import get_bot_status
            bot_st = await get_bot_status()
            if bot_st and isinstance(bot_st, dict):
                balances = bot_st.get("balances", {}).get(exchange.lower(), {})
                if "cash" in balances:
                    actual_cash_krw = float(balances["cash"])
                elif "krw" in balances:
                    actual_cash_krw = float(balances["krw"])
        except Exception:
            pass

        health = budget_manager.check_exchange_budget_health(
            exchange=exchange,
            templates=templates,
            actual_cash_krw=actual_cash_krw,
        )
        return JSONResponse({"ok": True, "data": health})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── 템플릿 목록 및 상세 ─────────────────────────────────────────────────────────

@router.get("/api/templates")
async def api_list_templates(user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    try:
        q = get_db().table("strategy_templates").select("*").order("created_at", desc=True)
        if not is_admin:
            if not bot_user_id:
                return JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)
            q._params["user_id"] = f"eq.{bot_user_id}"

        rows = (await q.execute()).data or []
        return JSONResponse(rows)
    except Exception as e:
        return JSONResponse({"error": "Internal error"}, status_code=500)


@router.post("/api/templates")
async def api_create_template(payload: TemplateCreate, user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    target_user_id = bot_user_id
    if not target_user_id and not is_admin:
        return JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)
    if not target_user_id:
        target_user_id = "admin"

    try:
        norm_ticker = _normalize_ticker(payload.exchange, payload.ticker)
        params = dict(payload.params)
        
        # kospi_top_dca 초기 파라미터 세팅
        if payload.strategy_type == "kospi_top_dca":
            if "budget_epoch" not in params: params["budget_epoch"] = 1
            if "plan_revision_no" not in params: params["plan_revision_no"] = 1
            if "cycle_no" not in params: params["cycle_no"] = 1
            if "current_cycle_bought" not in params: params["current_cycle_bought"] = []
            if "strategy_status" not in params: params["strategy_status"] = "active"
            if "schedule_enabled" not in params: params["schedule_enabled"] = True
            if "monthly_budget" not in params: params["monthly_budget"] = float(payload.budget)
            if "budget_mode" not in params: params["budget_mode"] = "monthly"
            if "carryover_budget" not in params: params["carryover_budget"] = 0.0
            if "monthly_spent" not in params: params["monthly_spent"] = 0.0

        data = {
            "user_id": target_user_id,
            "name": payload.name,
            "exchange": payload.exchange,
            "ticker": norm_ticker,
            "start_price": payload.start_price,
            "end_price": payload.end_price,
            "count": payload.count,
            "budget": payload.budget,
            "strategy_type": payload.strategy_type,
            "params": params,
        }
        res = await get_db().table("strategy_templates").insert(data).execute()
        return JSONResponse({"ok": True, "data": res.data})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/templates/{template_id}")
async def api_get_template(template_id: int, user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    try:
        q = get_db().table("strategy_templates").select("*").eq("id", template_id)
        if not is_admin:
            if not bot_user_id:
                return JSONResponse({"error": "권한이 없습니다."}, status_code=403)
            q._params["user_id"] = f"eq.{bot_user_id}"

        rows = (await q.execute()).data
        if not rows:
            return JSONResponse({"error": "템플릿을 찾을 수 없습니다."}, status_code=404)
        return JSONResponse({"ok": True, "data": rows[0]})
    except Exception as e:
        return JSONResponse({"error": "Internal error"}, status_code=500)


@router.put("/api/templates/{template_id}")
@router.patch("/api/templates/{template_id}")
async def api_update_template(template_id: int, payload: TemplateUpdate, user: dict = Depends(get_current_user)):
    """[불변식 5] 설정 키(CONFIG_KEYS)만 부분 병합(Partial Merge)하며 RUNTIME_STATE_KEYS는 보존."""
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]
    db = get_db()

    # 기존 템플릿 로드
    q = db.table("strategy_templates").select("*").eq("id", template_id)
    if not is_admin:
        if not bot_user_id:
            return JSONResponse({"error": "권한이 없습니다."}, status_code=403)
        q._params["user_id"] = f"eq.{bot_user_id}"

    rows = (await q.execute()).data
    if not rows:
        return JSONResponse({"error": "템플릿을 찾을 수 없거나 권한이 없습니다."}, status_code=404)
    old_tpl = rows[0]
    old_params = dict(old_tpl.get("params") or {})

    update_data = {}
    if payload.name is not None: update_data["name"] = payload.name
    if payload.exchange is not None: update_data["exchange"] = payload.exchange
    if payload.ticker is not None:
        ex = payload.exchange or old_tpl["exchange"]
        update_data["ticker"] = _normalize_ticker(ex, payload.ticker)
    if payload.start_price is not None: update_data["start_price"] = payload.start_price
    if payload.end_price is not None: update_data["end_price"] = payload.end_price
    if payload.count is not None: update_data["count"] = payload.count
    if payload.budget is not None: update_data["budget"] = payload.budget
    if payload.strategy_type is not None: update_data["strategy_type"] = payload.strategy_type

    if payload.params is not None:
        # [불변식 5 격리 병합] 오직 CONFIG_KEYS만 업데이트
        for k, v in payload.params.items():
            if k in progression_manager.CONFIG_KEYS:
                old_params[k] = v
        update_data["params"] = old_params

    if not update_data:
        return JSONResponse({"error": "변경할 내용이 없습니다."}, status_code=400)

    try:
        res = await db.table("strategy_templates").update(update_data).eq("id", template_id).execute()
        return JSONResponse({"ok": True, "data": res.data})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/api/templates/{template_id}")
async def api_delete_template(template_id: int, user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    try:
        q = get_db().table("strategy_templates").delete().eq("id", template_id)
        if not is_admin:
            if not bot_user_id:
                return JSONResponse({"error": "권한이 없습니다."}, status_code=403)
            q._params["user_id"] = f"eq.{bot_user_id}"

        await q.execute()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": "Internal error"}, status_code=500)


@router.post("/api/templates/{template_id}/duplicate")
async def api_duplicate_template(template_id: int, user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    try:
        q = get_db().table("strategy_templates").select("*").eq("id", template_id)
        if not is_admin:
            if not bot_user_id:
                return JSONResponse({"error": "권한이 없습니다."}, status_code=403)
            q._params["user_id"] = f"eq.{bot_user_id}"

        rows = (await q.execute()).data
        if not rows:
            return JSONResponse({"error": "템플릿을 찾을 수 없거나 권한이 없습니다."}, status_code=404)

        tpl = rows[0]
        new_data = {k: v for k, v in tpl.items() if k not in ("id", "created_at")}
        new_data["name"] = f"Copy of {tpl['name']}"

        res = await get_db().table("strategy_templates").insert(new_data).execute()
        return JSONResponse({"ok": True, "data": res.data})
    except Exception as e:
        return JSONResponse({"error": "Internal error"}, status_code=500)


# ── 실행, 보류(Holding), 중지(Stop), 예산 플랜/원장 제어 ────────────────────────

@router.post("/api/templates/{template_id}/execute")
async def api_execute_template(template_id: int, user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    try:
        q = get_db().table("strategy_templates").select("*").eq("id", template_id)
        if not is_admin:
            if not bot_user_id:
                return JSONResponse({"error": "권한이 없습니다."}, status_code=403)
            q._params["user_id"] = f"eq.{bot_user_id}"
        
        rows = (await q.execute()).data
        if not rows:
            return JSONResponse({"error": "템플릿을 찾을 수 없거나 권한이 없습니다."}, status_code=404)
        
        tpl = rows[0]
        stype = tpl.get("strategy_type", "grid")

        if stype == "kospi_top_dca":
            res = await progression_manager.run_strategy_progression(template_id)
            return JSONResponse({
                "ok": True,
                "message": f"TOP N 회전 배치 #{res['group_no']}가 실행되었습니다. (매수 {res['buy_orders_count']}건, 매도 {res['sell_orders_count']}건)",
                "data": res,
            })
        
        elif stype == "grid":
            res = execute_grid(
                user_id=tpl["user_id"],
                exchange=tpl["exchange"],
                ticker=tpl["ticker"],
                start_price=tpl["start_price"],
                end_price=tpl["end_price"],
                count=tpl["count"],
                budget=tpl["budget"]
            )
            success, err_msg = (await res) if inspect.isawaitable(res) else res
            msg = "거미줄 분할 매수 전략이 가동되었습니다."
        elif stype == "sgrid":
            res = execute_sgrid(
                user_id=tpl["user_id"],
                exchange=tpl["exchange"],
                ticker=tpl["ticker"],
                start_price=tpl["start_price"],
                end_price=tpl["end_price"],
                count=tpl["count"],
                total_volume=tpl["budget"],
            )
            success, err_msg = (await res) if inspect.isawaitable(res) else res
            msg = "거미줄 분할 매도 전략이 가동되었습니다."
        elif stype in ("rsitrade", "rsi"):
            params = tpl.get("params") or {}
            res = execute_rsitrade(
                user_id=tpl["user_id"],
                exchange=tpl["exchange"],
                ticker=tpl["ticker"],
                buy_rsi_range=params.get("buy_rsi_range", "25-30"),
                sell_rsi_range=params.get("sell_rsi_range", "65-75"),
                count=tpl["count"],
                budget=tpl["budget"],
                weighted=params.get("weighted", False)
            )
            success, err_msg = (await res) if inspect.isawaitable(res) else res
            msg = "RSI 순환 매매 전략이 가동되었습니다."
        elif stype in ("dca", "sdca"):
            params = tpl.get("params") or {}
            side = "ask" if stype == "sdca" or params.get("side") == "ask" else "bid"
            max_runs = params.get("max_runs")
            if max_runs is None and int(tpl.get("count") or 0) > 0:
                max_runs = int(tpl["count"])
            res = execute_dca(
                user_id=tpl["user_id"],
                exchange=tpl["exchange"],
                ticker=tpl["ticker"],
                side=side,
                schedule=params.get("schedule", "매일"),
                amount_type=params.get("amount_type", "budget"),
                amount=float(tpl["budget"]),
                exec_time=params.get("exec_time", "09:05"),
                max_runs=max_runs,
            )
            success, err_msg = (await res) if inspect.isawaitable(res) else res
            msg = "정기 적립식 매수 전략이 등록되었습니다." if side == "bid" else "정기 분할 매도 전략이 등록되었습니다."
        else:
            return JSONResponse({"error": f"지원하지 않는 전략 유형입니다: {stype}"}, status_code=400)

        if not success:
            return JSONResponse({"error": f"봇 주문 가동 실패: {err_msg}"}, status_code=500)
            
        return JSONResponse({"ok": True, "message": msg})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/templates/{template_id}/holding")
async def api_toggle_holding(template_id: int, payload: HoldingRequest, user: dict = Depends(get_current_user)):
    """전략 Active ↔ Holding (일시보류) 토글."""
    try:
        res = await progression_manager.set_strategy_holding(template_id, payload.is_holding)
        return JSONResponse({"ok": True, "data": res})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/templates/{template_id}/stop")
async def api_stop_strategy(template_id: int, payload: StopRequest, user: dict = Depends(get_current_user)):
    """전략 중지 3단계 제어 (pause | stop_and_cancel | terminate_and_liquidate)."""
    try:
        res = await progression_manager.stop_strategy(template_id, payload.mode)
        return JSONResponse({"ok": True, "data": res})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/templates/{template_id}/budget-plan")
async def api_update_budget_plan(template_id: int, payload: BudgetPlanRequest, user: dict = Depends(get_current_user)):
    """Budget Plan 수정 및 버전(revision_no) 기록, 당일 차액 즉시 보정 지원."""
    db = get_db()
    t_res = await db.table("strategy_templates").select("*").eq("id", template_id).execute()
    if not t_res.data:
        return JSONResponse({"error": "Template not found"}, status_code=404)

    template = t_res.data[0]
    try:
        new_params = await budget_manager.apply_plan_change(
            template=template,
            new_plan_config=payload.new_plan_config,
            apply_today_diff=payload.apply_today_diff,
            memo=payload.memo,
        )
        await db.table("strategy_templates").update({"params": new_params}).eq("id", template_id).execute()
        return JSONResponse({"ok": True, "data": new_params})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/templates/{template_id}/budget-reset")
async def api_reset_budget_plan(template_id: int, payload: BudgetResetRequest, user: dict = Depends(get_current_user)):
    """Budget Plan 초기화 (새 세대 budget_epoch += 1 생성)."""
    db = get_db()
    t_res = await db.table("strategy_templates").select("*").eq("id", template_id).execute()
    if not t_res.data:
        return JSONResponse({"error": "Template not found"}, status_code=404)

    template = t_res.data[0]
    try:
        new_params = await budget_manager.reset_budget_plan(
            template=template,
            new_config=payload.new_config,
            initial_carryover=payload.initial_carryover,
            reset_cycle=payload.reset_cycle,
            cancel_pending=payload.cancel_pending,
            memo=payload.memo,
        )
        await db.table("strategy_templates").update({"params": new_params}).eq("id", template_id).execute()
        return JSONResponse({"ok": True, "data": new_params})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/templates/{template_id}/budget-ledger")
async def api_get_budget_ledger(
    template_id: int,
    budget_epoch: Optional[int] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Budget Plan 변경 이력 및 통장 거래내역 방식의 +/- 감사 원장 조회."""
    db = get_db()
    try:
        t_res = await db.table("strategy_templates").select("params").eq("id", template_id).execute()
        if not t_res.data:
            return JSONResponse({"error": "Template not found"}, status_code=404)

        params = t_res.data[0].get("params") or {}
        revisions = params.get("budget_plan_revisions", [])

        q = db.table("budget_ledger").select("*").eq("template_id", template_id).order("id", desc=True)
        if budget_epoch is not None:
            q._params["budget_epoch"] = f"eq.{budget_epoch}"
        rows = (await q.execute()).data or []

        return JSONResponse({
            "ok": True,
            "template_id": template_id,
            "current_epoch": params.get("budget_epoch", 1),
            "carryover_budget": params.get("carryover_budget", 0.0),
            "monthly_spent": params.get("monthly_spent", 0.0),
            "revisions": revisions,
            "ledger": rows,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
