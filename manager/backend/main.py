import os
import asyncio
import hmac
import logging
import time
from collections import defaultdict
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, Depends
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import supabase_sign_in, generate_pkce_pair, build_oauth_url, exchange_pkce_code
from .routers import dashboard, events, orders, reports, sysconfig, stock_cache, trades, users, templates, mfa, analytics, feedbacks
from .routers._auth import get_current_user

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("manager")
KST = timezone(timedelta(hours=9))


async def _run_top_strategy_safe(template_id: int):
    from .services import progression_manager
    try:
        await progression_manager.run_strategy_progression(template_id)
    except Exception as e:
        logger.error(f"Scheduled TOP N strategy #{template_id} failed: {e}")


async def _top_strategy_scheduler_loop():
    logger.info("Started TOP N strategy background scheduler loop")
    attempted: set[tuple[int, str]] = set()  # (template_id, date) 하루 1회만 시도
    while True:
        try:
            await asyncio.sleep(60)
            now_kst = datetime.now(KST)
            cur_time_str = now_kst.strftime("%H:%M")
            today_str = now_kst.strftime("%Y-%m-%d")

            if now_kst.weekday() >= 5:
                continue
            attempted = {k for k in attempted if k[1] == today_str}

            from .db import get_db
            from .services import progression_manager
            db = get_db()
            res = await db.table("strategy_templates").select("id,name,strategy_type,params").eq("strategy_type", "kospi_top_dca").execute()
            templates = res.data or []

            for tpl in templates:
                params = tpl.get("params") or {}
                if params.get("strategy_status") != "active" or not params.get("schedule_enabled", True):
                    continue

                sched_time = params.get("schedule_time", "09:10")
                last_run = params.get("last_run_date")

                # sleep(60) 드리프트로 해당 분을 건너뛰어도 실행되도록 '>=' 사용 (장 마감 15:30 이전까지)
                key = (tpl["id"], today_str)
                if sched_time <= cur_time_str < "15:30" and last_run != today_str and key not in attempted:
                    attempted.add(key)
                    logger.info(f"Triggering scheduled TOP N strategy #{tpl['id']} ({tpl.get('name')}) at {cur_time_str}")
                    asyncio.create_task(_run_top_strategy_safe(tpl["id"]))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Error in TOP N scheduler loop: {e}")


_scheduler_lock_fh = None


def _acquire_scheduler_lock() -> bool:
    """다중 워커 환경에서 스케줄러가 한 프로세스에서만 돌도록 OS 파일 락을 획득한다.

    락은 프로세스 종료 시 OS가 자동 해제하므로 stale lock이 남지 않는다.
    """
    global _scheduler_lock_fh
    import tempfile
    path = os.path.join(tempfile.gettempdir(), "supabot_manager_top_scheduler.lock")
    try:
        fh = open(path, "a+")
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _scheduler_lock_fh = fh  # 참조 유지 (GC 시 락 해제 방지)
        return True
    except OSError:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler_task = None
    if _acquire_scheduler_lock():
        scheduler_task = asyncio.create_task(_top_strategy_scheduler_loop())
    else:
        logger.info("TOP N scheduler already running in another worker; skipping in this process")
    try:
        yield
    finally:
        if scheduler_task:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass


session_secret = os.environ.get("SESSION_SECRET", "").strip()
if not session_secret or session_secret == "change-me-in-production":
    raise RuntimeError("SESSION_SECRET must be set and cannot be the default insecure placeholder")

app = FastAPI(title="supabot manager", lifespan=lifespan)

https_only = os.environ.get("SESSION_HTTPS_ONLY", "true").lower() in ("1", "true", "yes")

app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    same_site="lax",
    https_only=https_only,
    max_age=86400,
)


@app.middleware("http")
async def csrf_origin_validation(request: Request, call_next):
    # 상태 변경 요청(POST/PUT/PATCH/DELETE, /api/*)에 대해 Origin/Referer 검증
    # 단, /api/realtime/trigger (API Key 인증)는 예외
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
        if request.url.path != "/api/realtime/trigger":
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")
            source = origin or referer
            if source:
                parsed_source = urlparse(source)
                source_origin = f"{parsed_source.scheme}://{parsed_source.netloc}".rstrip("/")

                raw_allowed = os.environ.get("MANAGER_ALLOWED_ORIGINS", "").strip()
                allowed_origins = [o.strip().rstrip("/") for o in raw_allowed.split(",") if o.strip()]
                # 기본적으로 현재 호스트(자신)는 항상 허용
                parsed_base = urlparse(str(request.base_url))
                self_origin = f"{parsed_base.scheme}://{parsed_base.netloc}".rstrip("/")
                if self_origin:
                    allowed_origins.append(self_origin)
                # 리버스 프록시(TLS 종단) 뒤에서는 scheme이 http로 보일 수 있으므로 전달된 호스트/프로토콜도 허용
                fwd_host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
                fwd_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
                if fwd_host:
                    for scheme in ([fwd_proto] if fwd_proto else ["https", "http"]):
                        allowed_origins.append(f"{scheme}://{fwd_host}")

                if source_origin not in allowed_origins:
                    return JSONResponse({"error": "Forbidden: invalid origin"}, status_code=403)

    return await call_next(request)


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers["Cache-Control"] = "no-cache"
    return response

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
app.include_router(stock_cache.router)
app.include_router(feedbacks.router)


class RealtimeBroadcastManager:
    def __init__(self):
        self.active_connections = set()

    async def subscribe(self):
        queue = asyncio.Queue(maxsize=100)
        self.active_connections.add(queue)
        try:
            while True:
                event = await queue.get()
                yield f"data: {event}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.active_connections.discard(queue)

    def trigger(self, event_data: str):
        for queue in list(self.active_connections):
            try:
                queue.put_nowait(event_data)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(event_data)
                except Exception:
                    pass

realtime_manager = RealtimeBroadcastManager()


@app.get("/api/realtime/stream")
async def realtime_stream(_=Depends(get_current_user)):
    return StreamingResponse(realtime_manager.subscribe(), media_type="text/event-stream")


@app.post("/api/realtime/trigger")
async def realtime_trigger(request: Request):
    api_key = os.environ.get("MANAGER_API_KEY", "")
    provided = request.headers.get("X-API-Key") or ""
    if not api_key or not hmac.compare_digest(provided.encode("utf-8"), api_key.encode("utf-8")):
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
    username = ""
    user_id = user["bot_user_id"]
    if user_id:
        try:
            from .db import get_db
            rows = (await get_db().table("users").select("mfa_enabled,username").eq("user_id", user_id).execute()).data
            if rows:
                mfa_enabled = bool(rows[0].get("mfa_enabled", False))
                username = rows[0].get("username", "")
        except Exception:
            pass

    return JSONResponse({
        **user,
        "mfa_enabled": mfa_enabled,
        "username": username,
    })


@app.patch("/api/me/profile")
async def api_update_profile(request: Request, user: dict = Depends(get_current_user)):
    user_id = user["bot_user_id"]
    if not user_id:
        return JSONResponse({"error": "대시보드와 연결된 봇 계정이 없습니다."}, status_code=403)
    try:
        body = await request.json()
        username = body.get("username", "").strip()
        from .db import get_db
        await get_db().table("users").update({"username": username}).eq("user_id", user_id).execute()
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("Profile update error: %s", e, exc_info=True)
        return JSONResponse({"error": "Internal error"}, status_code=500)


async def _create_session_for_email(request: Request, email: str, access_token: str) -> str:
    """
    Looks up the bot user by manager_email, handles MFA check, and populates the session.
    Returns: 'ok' | 'mfa_required' | 'no_access'
    """
    from .db import get_db
    from .crypto import verify_trusted_token

    try:
        rows = (
            await get_db()
            .table("users")
            .select("user_id,is_admin,mfa_enabled")
            .eq("manager_email", email)
            .execute()
        ).data
    except Exception:
        rows = []

    if rows:
        bot_user = rows[0]
        if bool(bot_user.get("mfa_enabled", False)):
            trusted_token = request.cookies.get("trusted_device_token")
            trusted_user_id = verify_trusted_token(trusted_token)
            if trusted_user_id != bot_user["user_id"]:
                request.session["mfa_pending_email"] = email
                request.session["mfa_pending_user_id"] = bot_user["user_id"]
                request.session["mfa_pending_is_admin"] = bool(bot_user.get("is_admin", False))
                request.session["mfa_pending_access_token"] = access_token
                return "mfa_required"

        request.session["user_email"] = email
        request.session["access_token"] = access_token
        request.session["is_admin"] = bool(bot_user.get("is_admin", False))
        request.session["bot_user_id"] = bot_user["user_id"]
        return "ok"

    # MANAGER_SUPER_ADMIN_EMAIL: 봇 유저 없이도 어드민 접근 허용 (최초 설정/비상용)
    super_admin = os.environ.get("MANAGER_SUPER_ADMIN_EMAIL", "").strip().lower()
    if super_admin and email == super_admin:
        request.session["user_email"] = email
        request.session["access_token"] = access_token
        request.session["is_admin"] = True
        request.session["bot_user_id"] = None
        return "ok"

    return "no_access"


# 로그인 Rate Limit: IP + 이메일 기준 5분(300초) 내 10회 제한
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 300
_MAX_LOGIN_ATTEMPTS = 10


def _is_rate_limited(client_ip: str, email: str) -> bool:
    now = time.time()
    key = f"{client_ip}:{email}"
    attempts = [t for t in _login_attempts[key] if now - t < _RATE_LIMIT_WINDOW]
    _login_attempts[key] = attempts
    if len(attempts) >= _MAX_LOGIN_ATTEMPTS:
        return True
    _login_attempts[key].append(now)
    return False


def _reset_rate_limit(client_ip: str, email: str):
    key = f"{client_ip}:{email}"
    _login_attempts.pop(key, None)


@app.post("/api/login")
async def api_login(request: Request):
    try:
        body = await request.json()
        email = body.get("email", "").strip().lower()
        password = body.get("password", "")
    except Exception:
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip, email):
        return JSONResponse(
            {"error": "로그인 시도가 너무 많습니다. 5분 후에 다시 시도해 주세요."},
            status_code=429,
        )

    result = supabase_sign_in(email, password)
    if not result or not result.get("access_token"):
        return JSONResponse({"error": "이메일 또는 비밀번호가 올바르지 않습니다."}, status_code=401)

    _reset_rate_limit(client_ip, email)

    outcome = await _create_session_for_email(request, email, result["access_token"])
    if outcome == "ok":
        return JSONResponse({"ok": True})
    if outcome == "mfa_required":
        return JSONResponse({"mfa_required": True})
    return JSONResponse({"error": "대시보드 접근 권한이 없습니다."}, status_code=403)


@app.get("/api/auth/google")
async def api_auth_google(request: Request):
    """Google OAuth PKCE 플로우 시작."""
    code_verifier, code_challenge = generate_pkce_pair()
    request.session["oauth_code_verifier"] = code_verifier

    base_url = os.environ.get("MANAGER_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/auth/callback"
    request.session["oauth_redirect_uri"] = redirect_uri

    return RedirectResponse(build_oauth_url(redirect_uri, code_challenge), status_code=302)


@app.get("/api/auth/callback")
async def api_auth_callback(request: Request, code: str | None = None, error: str | None = None):
    """Supabase Google OAuth 콜백 처리."""
    if error or not code:
        return RedirectResponse("/login?error=oauth_failed", status_code=302)

    code_verifier = request.session.pop("oauth_code_verifier", None)
    request.session.pop("oauth_redirect_uri", None)

    if not code_verifier:
        return RedirectResponse("/login?error=oauth_failed", status_code=302)

    token_data = await exchange_pkce_code(code, code_verifier)
    if not token_data or not token_data.get("access_token"):
        return RedirectResponse("/login?error=oauth_failed", status_code=302)

    email = (token_data.get("user") or {}).get("email", "").strip().lower()
    if not email:
        return RedirectResponse("/login?error=oauth_failed", status_code=302)

    outcome = await _create_session_for_email(request, email, token_data["access_token"])
    if outcome == "ok":
        return RedirectResponse("/dashboard", status_code=302)
    if outcome == "mfa_required":
        return RedirectResponse("/login?oauth_mfa=1", status_code=302)
    return RedirectResponse("/login?error=no_access", status_code=302)


@app.post("/api/logout")
async def api_logout(request: Request):
    request.session.clear()
    return JSONResponse({"ok": True})


# SPA: serve React app for all non-/api paths.
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
