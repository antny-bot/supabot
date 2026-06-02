from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import get_admin_user

router = APIRouter()


@router.get("/api/sysconfig")
async def api_get_sysconfig(_=Depends(get_admin_user)):
    try:
        rows = (await get_db().table("system_config").select("key,value,updated_at").execute()).data
        config = {r["key"]: r["value"] for r in rows}
        return JSONResponse(config)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/sysconfig")
async def api_save_sysconfig(request: Request, _=Depends(get_admin_user)):
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            return JSONResponse({"error": "Invalid payload"}, status_code=400)

        db = get_db()
        # 키별로 upsert (현재 Supabase 간이 클라이언트는 단건 처리에 최적화됨)
        for key, val in payload.items():
            if key and val is not None:
                await db.table("system_config").upsert({"key": key, "value": val}).execute()

        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
