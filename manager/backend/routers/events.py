from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

_LEVELS = ["error", "warning", "info"]


def _require_login(request: Request):
    return request.session.get("user_email")


@router.get("/admin/events", response_class=HTMLResponse)
async def list_events(request: Request, level: str | None = None):
    if not _require_login(request):
        return RedirectResponse("/login", status_code=303)
    events = []
    error = None
    try:
        q = get_db().table("operational_events").select("*").order("id", desc=True).limit(200)
        if level in _LEVELS:
            q._params["level"] = f"eq.{level}"
        events = q.execute().data
    except Exception as e:
        error = str(e)
    return templates.TemplateResponse(
        request,
        "events.html",
        {
            "events": events,
            "level_filter": level or "",
            "levels": _LEVELS,
            "error": error,
        },
    )
