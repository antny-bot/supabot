import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import supabase_sign_in
from .routers import dashboard, events, orders, sysconfig, trades, users

app = FastAPI(title="supabot manager")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "change-me-in-production"),
    max_age=86400,
)

templates = Jinja2Templates(directory="frontend/templates")

app.include_router(dashboard.router)
app.include_router(orders.router)
app.include_router(trades.router)
app.include_router(events.router)
app.include_router(users.router)
app.include_router(sysconfig.router)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if not request.session.get("user_email"):
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/admin/dashboard", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_email"):
        return RedirectResponse("/admin/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    result = supabase_sign_in(email, password)
    if result and result.get("access_token"):
        request.session["user_email"] = email
        request.session["access_token"] = result["access_token"]
        return RedirectResponse("/admin/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "이메일 또는 비밀번호가 올바르지 않습니다."},
        status_code=401,
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
