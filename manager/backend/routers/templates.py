# -*- coding: utf-8 -*-
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import get_db
from ._auth import _require_login, get_session_user
from ..bot_client import execute_grid, execute_rsitrade

router = APIRouter()

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


@router.get("/api/templates")
async def api_list_templates(request: Request):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    session_user = get_session_user(request)
    is_admin = session_user["is_admin"]
    bot_user_id = session_user["bot_user_id"]

    if not is_admin and not bot_user_id:
        return JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)

    try:
        q = get_db().table("strategy_templates").select("*").order("created_at", desc=True)
        if not is_admin:
            q._params["user_id"] = f"eq.{bot_user_id}"
        templates = q.execute().data
        return JSONResponse(templates)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.post("/api/templates")
async def api_create_template(request: Request, payload: TemplateCreate):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    session_user = get_session_user(request)
    is_admin = session_user["is_admin"]
    bot_user_id = session_user["bot_user_id"]

    # 어드민이라도 user_id가 필요하므로 본인 bot_user_id가 없으면 생성 불가하게 처리하거나,
    # 세션 정보를 기반으로 bot_user_id를 강제 할당합니다.
    user_id = bot_user_id
    if is_admin and not user_id:
        # 어드민인데 봇 유저 ID가 없으면 'admin' 또는 test용 ID로 세팅
        user_id = "admin"

    if not user_id:
        return JSONResponse({"error": "연결된 봇 계정이 없습니다."}, status_code=403)

    if payload.count <= 0:
        return JSONResponse({"error": "주문 개수는 1개 이상이어야 합니다."}, status_code=400)
    if payload.budget <= 0:
        return JSONResponse({"error": "총 예산은 0보다 커야 합니다."}, status_code=400)

    try:
        template_data = {
            "user_id": user_id,
            "name": payload.name,
            "exchange": payload.exchange.lower(),
            "ticker": payload.ticker.upper(),
            "start_price": payload.start_price,
            "end_price": payload.end_price,
            "count": payload.count,
            "budget": payload.budget,
            "strategy_type": payload.strategy_type,
            "params": payload.params,
        }
        res = get_db().table("strategy_templates").insert(template_data).execute()
        return JSONResponse({"ok": True, "data": res.data})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.delete("/api/templates/{template_id}")
async def api_delete_template(request: Request, template_id: int):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    session_user = get_session_user(request)
    is_admin = session_user["is_admin"]
    bot_user_id = session_user["bot_user_id"]

    try:
        q = get_db().table("strategy_templates").delete().eq("id", template_id)
        if not is_admin:
            if not bot_user_id:
                return JSONResponse({"error": "권한이 없습니다."}, status_code=403)
            q._params["user_id"] = f"eq.{bot_user_id}"
        
        q.execute()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.post("/api/templates/{template_id}/execute")
async def api_execute_template(request: Request, template_id: int):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    session_user = get_session_user(request)
    is_admin = session_user["is_admin"]
    bot_user_id = session_user["bot_user_id"]

    try:
        # 템플릿 로드
        q = get_db().table("strategy_templates").select("*").eq("id", template_id)
        if not is_admin:
            if not bot_user_id:
                return JSONResponse({"error": "권한이 없습니다."}, status_code=403)
            q._params["user_id"] = f"eq.{bot_user_id}"
        
        rows = q.execute().data
        if not rows:
            return JSONResponse({"error": "템플릿을 찾을 수 없거나 권한이 없습니다."}, status_code=404)
        
        tpl = rows[0]
        stype = tpl.get("strategy_type", "grid")
        
        if stype == "grid":
            # 봇에게 거미줄 실행 요청 전송
            success = execute_grid(
                user_id=tpl["user_id"],
                exchange=tpl["exchange"],
                ticker=tpl["ticker"],
                start_price=tpl["start_price"],
                end_price=tpl["end_price"],
                count=tpl["count"],
                budget=tpl["budget"]
            )
            msg = "거미줄 전략이 가동되었습니다."
        elif stype == "rsitrade":
            # 봇에게 RSITrade 실행 요청 전송
            params = tpl.get("params") or {}
            success = execute_rsitrade(
                user_id=tpl["user_id"],
                exchange=tpl["exchange"],
                ticker=tpl["ticker"],
                buy_rsi_range=params.get("buy_rsi_range", "25-30"),
                sell_rsi_range=params.get("sell_rsi_range", "65-75"),
                count=tpl["count"],
                budget=tpl["budget"]
            )
            msg = "RSI 순환 매매 전략이 가동되었습니다."
        else:
            return JSONResponse({"error": f"지원하지 않는 전략 유형입니다: {stype}"}, status_code=400)

        if not success:
            return JSONResponse({"error": "봇 백엔드로의 주문 실행 요청 전송에 실패했습니다."}, status_code=500)
            
        return JSONResponse({"ok": True, "message": msg})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
