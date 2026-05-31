from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

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


@router.get("/admin/config", response_class=HTMLResponse)
async def config_page(request: Request):
    if not _require_login(request):
        return RedirectResponse("/login", status_code=303)
    try:
        config = _get_config()
        error = None
        saved = False
    except Exception as e:
        config = []
        error = str(e)
        saved = False
    return templates.TemplateResponse(
        "sysconfig.html",
        {"request": request, "config": config, "error": error, "saved": saved},
    )


@router.post("/admin/config", response_class=HTMLResponse)
async def config_save(request: Request):
    if not _require_login(request):
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    db = get_db()
    error = None
    try:
        for key in _CONFIG_LABELS:
            val = form.get(key, "").strip()
            if val:
                db.table("system_config").upsert({"key": key, "value": val}).execute()
    except Exception as e:
        error = str(e)
    try:
        config = _get_config()
    except Exception as e:
        config = []
        error = str(e)
    return templates.TemplateResponse(
        "sysconfig.html",
        {"request": request, "config": config, "error": error, "saved": not error},
    )
