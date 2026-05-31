import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import supabase_sign_in
from .routers import sysconfig, users

app = FastAPI(title="supabot manager")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "change-me-in-production"),
    max_age=86400,
)

templates = Jinja2Templates(directory="frontend/templates")

app.include_router(users.router)
app.include_router(sysconfig.router)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if not request.session.get("user_email"):
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/admin/users", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_email"):
        return RedirectResponse("/admin/users", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    result = supabase_sign_in(email, password)
    if result and result.get("access_token"):
        request.session["user_email"] = email
        request.session["access_token"] = result["access_token"]
        return RedirectResponse("/admin/users", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "이메일 또는 비밀번호가 올바르지 않습니다."},
        status_code=401,
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
