import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
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


# Legacy HTML login (redirect to SPA)
@app.get("/login")
@app.get("/")
async def root_redirect(request: Request):
    if request.session.get("user_email"):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


# Serve React SPA — must be registered last
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
