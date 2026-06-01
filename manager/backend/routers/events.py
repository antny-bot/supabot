from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import _require_admin

router = APIRouter()

_LEVELS = ["error", "warning", "info"]


@router.get("/api/events")
async def api_list_events(request: Request, level: str | None = None):
    guard = _require_admin(request)
    if guard:
        return guard
    try:
        q = get_db().table("operational_events").select("*").order("id", desc=True).limit(200)
        if level in _LEVELS:
            q._params["level"] = f"eq.{level}"
        return JSONResponse(q.execute().data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
