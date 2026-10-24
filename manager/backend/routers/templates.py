# -*- coding: utf-8 -*-
import inspect
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import get_db
from ._auth import get_current_user
from ..bot_client import execute_grid, execute_sgrid, execute_rsitrade

router = APIRouter()


def _normalize_ticker(exchange: str, ticker: str) -> str:
    t = ticker.strip().upper()
    if exchange in ("upbit", "bithumb") and "-" not in t:
        return f"KRW-{t}"
    if exchange == "kis":
        return t.replace("KRW-", "")
    return t


class TemplateCreate(BaseModel):
    name: str
    exchange: str
    ticker: str
    start_price: float = 0.0
    end_price: float = 0.0
    count: int
    budget: float
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

        rows = (await q.execute()).data
        return JSONResponse({"ok": True, "data": rows})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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
            "params": payload.params
        }
        res = await get_db().table("strategy_templates").insert(data).execute()
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
        return JSONResponse({"error": str(e)}, status_code=500)


@router.put("/api/templates/{template_id}")
async def api_update_template(template_id: int, payload: TemplateUpdate, user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    update_data = {}
    if payload.name is not None: update_data["name"] = payload.name
    if payload.exchange is not None: update_data["exchange"] = payload.exchange
    if payload.ticker is not None:
        ex = payload.exchange or "upbit"
        update_data["ticker"] = _normalize_ticker(ex, payload.ticker)
    if payload.start_price is not None: update_data["start_price"] = payload.start_price
    if payload.end_price is not None: update_data["end_price"] = payload.end_price
    if payload.count is not None: update_data["count"] = payload.count
    if payload.budget is not None: update_data["budget"] = payload.budget
    if payload.strategy_type is not None: update_data["strategy_type"] = payload.strategy_type
    if payload.params is not None: update_data["params"] = payload.params

    if not update_data:
        return JSONResponse({"error": "변경할 내용이 없습니다."}, status_code=400)

    try:
        q = get_db().table("strategy_templates").update(update_data).eq("id", template_id)
        if not is_admin:
            if not bot_user_id:
                return JSONResponse({"error": "권한이 없습니다."}, status_code=403)
            q._params["user_id"] = f"eq.{bot_user_id}"

        res = await q.execute()
        if not res.data:
            return JSONResponse({"error": "템플릿을 찾을 수 없거나 권한이 없습니다."}, status_code=404)
        return JSONResponse({"ok": True, "data": res.data})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/templates/{template_id}/execute")
async def api_execute_template(template_id: int, user: dict = Depends(get_current_user)):
    is_admin = user["is_admin"]
    bot_user_id = user["bot_user_id"]

    try:
        # 템플릿 로드
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
        
        if stype == "grid":
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
        elif stype == "rsitrade":
            # 봇에게 RSITrade 실행 요청 전송
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
        else:
            return JSONResponse({"error": f"지원하지 않는 전략 유형입니다: {stype}"}, status_code=400)

        if not success:
            return JSONResponse({"error": f"봇 주문 가동 실패: {err_msg}"}, status_code=500)
            
        return JSONResponse({"ok": True, "message": msg})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
