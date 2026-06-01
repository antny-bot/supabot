from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import get_db

router = APIRouter()

_LEVELS = ["error", "warning", "info"]


def _require_login(request: Request):
    return request.session.get("user_email")


@router.get("/api/events")
async def api_list_events(request: Request, level: str | None = None):
    if not _require_login(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        q = get_db().table("operational_events").select("*").order("id", desc=True).limit(200)
        if level in _LEVELS:
            q._params["level"] = f"eq.{level}"
        return JSONResponse(q.execute().data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
