import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import supabase_sign_in
from .routers import dashboard, events, orders, sysconfig, trades, users

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


@app.get("/api/me")
async def api_me(request: Request):
    email = request.session.get("user_email")
    if not email:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return JSONResponse({"email": email})


@app.post("/api/login")
async def api_login(request: Request):
    try:
        body = await request.json()
        email = body.get("email", "")
        password = body.get("password", "")
    except Exception:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    result = supabase_sign_in(email, password)
    if result and result.get("access_token"):
        request.session["user_email"] = email
        request.session["access_token"] = result["access_token"]
        return JSONResponse({"ok": True})
    return JSONResponse({"error": "이메일 또는 비밀번호가 올바르지 않습니다."}, status_code=401)


@app.post("/api/logout")
async def api_logout(request: Request):
    request.session.clear()
    return JSONResponse({"ok": True})


# SPA: serve React app for all non-/api paths.
# StaticFiles(html=True) serves index.html for any path that doesn't match a file,
# enabling client-side React Router to handle routes like /dashboard, /login, etc.
_DIST = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))

if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")
else:
    _INDEX_FALLBACK = os.path.join(os.path.dirname(__file__), "_no_frontend.html")

    @app.get("/{full_path:path}")
    async def no_frontend(full_path: str):  # noqa: ARG001
        return JSONResponse(
            {"error": "Frontend not built. Run: cd manager/frontend && npm run build"},
            status_code=503,
        )
