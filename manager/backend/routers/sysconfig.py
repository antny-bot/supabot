from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import get_admin_user

router = APIRouter()

_CONFIG_METADATA = {
    "poll_active_interval": {
        "label": "주문 감시 간격 (활성)",
        "desc": "활성 주문이 있을 때 거래소를 확인하는 주기입니다.",
    },
    "poll_no_order_interval": {
        "label": "주문 감시 간격 (대기)",
        "desc": "활성 주문이 없을 때 거래소를 확인하는 주기입니다.",
    },
    "signal_analysis_interval": {
        "label": "신호 분석 간격",
        "desc": "기술적 지표 및 전략 신호를 분석하는 주기입니다.",
    },
}


@router.get("/api/sysconfig")
async def api_get_sysconfig(_=Depends(get_admin_user)):
    try:
        rows = (await get_db().table("system_config").select("key,value,updated_at").execute()).data
        
        # 프론트엔드가 ConfigItem[] 타입을 기대하므로 배열 형태로 반환
        config_list = []
        for r in rows:
            key = r["key"]
            meta = _CONFIG_METADATA.get(key, {"label": key, "desc": ""})
            config_list.append({
                "key": key,
                "value": str(r["value"]),
                "updated_at": r["updated_at"],
                "label": meta["label"],
                "desc": meta["desc"]
            })
            
        return JSONResponse(config_list)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/sysconfig")
async def api_save_sysconfig(request: Request, _=Depends(get_admin_user)):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            return JSONResponse({"error": "Invalid payload"}, status_code=400)

        db = get_db()
        for key, val in payload.items():
            if key and val is not None:
                await db.table("system_config").upsert({"key": key, "value": val}).execute()

        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
