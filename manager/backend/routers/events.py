from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import get_admin_user

router = APIRouter()

_LEVELS = ["error", "warning", "info"]


@router.get("/api/events")
async def api_list_events(level: str | None = None, _=Depends(get_admin_user)):
    try:
        q = get_db().table("operational_events").select("*").order("id", desc=True).limit(200)
        if level in _LEVELS:
            q._params["level"] = f"eq.{level}"
        return JSONResponse((await q.execute()).data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
