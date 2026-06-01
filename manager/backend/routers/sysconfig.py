from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import get_db

router = APIRouter()

_CONFIG_LABELS = {
    "poll_active_interval": ("주문 활성 폴링 간격", "초 — 미체결 주문이 있을 때 거래소 조회 주기"),
    "poll_no_order_interval": ("대기 폴링 간격", "초 — 주문 없을 때 조회 주기"),
    "signal_analysis_interval": ("시그널 분석 간격", "초 — RSI/BB 시그널 계산 주기"),
}


def _require_login(request: Request):
    return request.session.get("user_email")


def _get_config() -> list[dict]:
    rows = get_db().table("system_config").select("key,value,updated_at").execute().data
    result = []
    for row in rows:
        label, desc = _CONFIG_LABELS.get(row["key"], (row["key"], ""))
        result.append({**row, "label": label, "desc": desc})
    return result


@router.get("/api/config")
async def api_get_config(request: Request):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        return JSONResponse(_get_config())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/config")
async def api_save_config(request: Request):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
        db = get_db()
        for key in _CONFIG_LABELS:
            val = str(body.get(key, "")).strip()
            if val:
                db.table("system_config").upsert({"key": key, "value": val}).execute()
        return JSONResponse({"saved": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
