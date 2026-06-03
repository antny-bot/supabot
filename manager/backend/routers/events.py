from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..db import get_db
from ._auth import get_admin_user

router = APIRouter()

_LEVELS = ["error", "warning", "info"]
_STATES = ["unread", "read", "archived", "all"]


def _apply_state_filter(query, state: str | None):
    if state == "unread":
        query._params["read_at"] = "is.null"
        query._params["archived_at"] = "is.null"
    elif state == "read":
        query._params["read_at"] = "not.is.null"
        query._params["archived_at"] = "is.null"
    elif state == "archived":
        query._params["archived_at"] = "not.is.null"
    return query


async def _fetch_event(event_id: int) -> dict | None:
    rows = (await get_db().table("operational_events").select("*").eq("id", event_id).execute()).data
    return rows[0] if rows else None


async def _update_event(event_id: int, payload: dict) -> JSONResponse:
    try:
        await get_db().table("operational_events").update(payload).eq("id", event_id).execute()
        row = await _fetch_event(event_id)
        if not row:
            return JSONResponse({"error": "Event not found"}, status_code=404)
        return JSONResponse(row)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/events")
async def api_list_events(level: str | None = None, state: str | None = None, _=Depends(get_admin_user)):
    try:
        q = get_db().table("operational_events").select("*").order("id", desc=True).limit(200)
        if level in _LEVELS:
            q._params["level"] = f"eq.{level}"
        if state in _STATES and state != "all":
            q = _apply_state_filter(q, state)
        return JSONResponse((await q.execute()).data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.patch("/api/events/{event_id}/read")
async def api_mark_event_read(event_id: int, _=Depends(get_admin_user)):
    now = datetime.now(timezone.utc).isoformat()
    return await _update_event(event_id, {"read_at": now})


@router.patch("/api/events/{event_id}/unread")
async def api_mark_event_unread(event_id: int, _=Depends(get_admin_user)):
    return await _update_event(event_id, {"read_at": None})


@router.patch("/api/events/{event_id}/archive")
async def api_archive_event(event_id: int, _=Depends(get_admin_user)):
    now = datetime.now(timezone.utc).isoformat()
    return await _update_event(event_id, {"archived_at": now, "read_at": now})


@router.patch("/api/events/{event_id}/unarchive")
async def api_unarchive_event(event_id: int, _=Depends(get_admin_user)):
    return await _update_event(event_id, {"archived_at": None})
