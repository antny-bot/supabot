import os
import asyncio

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, Depends
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import supabase_sign_in
from .routers import dashboard, events, orders, reports, sysconfig, trades, users, templates, mfa, analytics
from .routers._auth import get_current_user

app = FastAPI(title="supabot manager")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "change-me-in-production"),
    max_age=86400,
)

# /api/* routes — registered first so they take priority over static file mount
app.include_router(dashboard.router)
app.include_router(orders.router)
app.include_router(trades.router)
app.include_router(events.router)
app.include_router(users.router)
app.include_router(sysconfig.router)
app.include_router(reports.router)
app.include_router(templates.router)
app.include_router(mfa.router)
app.include_router(analytics.router)


class RealtimeBroadcastManager:
    def __init__(self):
        self.active_connections = set()

    async def subscribe(self):
        queue = asyncio.Queue()
        self.active_connections.add(queue)
        try:
            while True:
                event = await queue.get()
                yield f"data: {event}\n\n"
        except asyncio.CancelledError:
            self.active_connections.remove(queue)

    def trigger(self, event_data: str):
        for queue in self.active_connections:
            queue.put_nowait(event_data)

realtime_manager = RealtimeBroadcastManager()


@app.get("/api/realtime/stream")
async def realtime_stream(_=Depends(get_current_user)):
    return StreamingResponse(realtime_manager.subscribe(), media_type="text/event-stream")


@app.post("/api/realtime/trigger")
async def realtime_trigger(request: Request):
    api_key = os.environ.get("MANAGER_API_KEY", "")
    if not api_key or request.headers.get("X-API-Key") != api_key:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
        event_name = body.get("event", "refresh")
    except Exception:
        event_name = "refresh"
    realtime_manager.trigger(event_name)
    return {"ok": True}


@app.get("/api/me")
async def api_me(user: dict = Depends(get_current_user)):
    mfa_enabled = False
    user_id = user["bot_user_id"]
    if user_id:
        try:
            from .db import get_db
            rows = (await get_db().table("users").select("mfa_enabled").eq("user_id", user_id).execute()).data
            if rows:
                mfa_enabled = bool(rows[0].get("mfa_enabled", False))
        except Exception:
            pass

    return JSONResponse({
        **user,
        "mfa_enabled": mfa_enabled,
    })


@app.post("/api/login")
async def api_login(request: Request):
    try:
        body = await request.json()
        email = body.get("email", "").strip().lower()
        password = body.get("password", "")
    except Exception:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    result = supabase_sign_in(email, password)
    if not result or not result.get("access_token"):
        return JSONResponse({"error": "이메일 또는 비밀번호가 올바르지 않습니다."}, status_code=401)

    # users 테이블에서 manager_email로 봇 유저 조회 (mfa_enabled도 함께 select)
    try:
        from .db import get_db
        rows = (await get_db().table("users").select("user_id,is_admin,mfa_enabled").eq("manager_email", email).execute()).data
    except Exception:
        rows = []

    if rows:
        bot_user = rows[0]
        # 만약 MFA가 활성화되어 있으면, 2차 인증 필요 여부 확인
        if bool(bot_user.get("mfa_enabled", False)):
            # "신뢰할 수 있는 기기" 쿠키 확인
            from .crypto import verify_trusted_token
            trusted_token = request.cookies.get("trusted_device_token")
            trusted_user_id = verify_trusted_token(trusted_token)
            
            if trusted_user_id != bot_user["user_id"]:
                # 신뢰 토큰이 없거나 다른 유저인 경우 MFA 대기 세션 설정
                request.session["mfa_pending_email"] = email
                request.session["mfa_pending_user_id"] = bot_user["user_id"]
                request.session["mfa_pending_is_admin"] = bool(bot_user.get("is_admin", False))
                request.session["mfa_pending_access_token"] = result["access_token"]
                return JSONResponse({"mfa_required": True})
            
            # 신뢰 토큰이 유효하면 MFA 패스 (로그에 남길 수 있음)

        request.session["user_email"] = email
        request.session["access_token"] = result["access_token"]
        request.session["is_admin"] = bool(bot_user.get("is_admin", False))
        request.session["bot_user_id"] = bot_user["user_id"]
        return JSONResponse({"ok": True})

    # MANAGER_SUPER_ADMIN_EMAIL: 봇 유저 없이도 어드민 접근 허용 (최초 설정/비상용)
    super_admin = os.environ.get("MANAGER_SUPER_ADMIN_EMAIL", "").strip().lower()
    if super_admin and email == super_admin:
        request.session["user_email"] = email
        request.session["access_token"] = result["access_token"]
        request.session["is_admin"] = True
        request.session["bot_user_id"] = None
        return JSONResponse({"ok": True})

    return JSONResponse({"error": "매니저 사용 권한이 없습니다."}, status_code=403)


@app.post("/api/logout")
async def api_logout(request: Request):
    request.session.clear()
    return JSONResponse({"ok": True})


# SPA: serve React app for all non-/api paths.
# /assets mount handles hashed JS/CSS files; catch-all route serves index.html
# for any SPA route (e.g. /dashboard, /orders) so BrowserRouter works on direct load.
_DIST = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))

if os.path.isdir(_DIST):
    _assets_dir = os.path.join(_DIST, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_index(full_path: str):  # noqa: ARG001
        file_path = os.path.normpath(os.path.join(_DIST, full_path))
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_DIST, "index.html"))
else:
    @app.get("/{full_path:path}", include_in_schema=False)
    async def no_frontend(full_path: str):  # noqa: ARG001
        return JSONResponse(
            {"error": "Frontend not built. Run: cd manager/frontend && npm run build"},
            status_code=503,
        )
