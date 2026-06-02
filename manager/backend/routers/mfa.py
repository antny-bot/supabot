import pyotp
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import get_db
from ..crypto import encrypt_mfa_secret, decrypt_mfa_secret
from ._auth import _require_login

router = APIRouter()

@router.post("/api/login/mfa")
async def api_login_mfa(request: Request):
    try:
        body = await request.json()
        code = body.get("code", "").strip()
    except Exception:
        return JSONResponse({"error": "올바르지 않은 요청입니다."}, status_code=400)

    if not code:
        return JSONResponse({"error": "인증 코드를 입력해주세요."}, status_code=400)

    # 1차 로그인 정보 세션 검증
    email = request.session.get("mfa_pending_email")
    user_id = request.session.get("mfa_pending_user_id")
    is_admin = request.session.get("mfa_pending_is_admin")
    access_token = request.session.get("mfa_pending_access_token")

    if not email or not user_id or not access_token:
        return JSONResponse({"error": "세션이 만료되었거나 올바르지 않은 접근입니다. 다시 로그인해주세요."}, status_code=401)

    # DB에서 유저의 mfa_secret 조회
    try:
        db = get_db()
        rows = db.table("users").select("mfa_secret,mfa_enabled").eq("user_id", user_id).execute().data
    except Exception as e:
        return JSONResponse({"error": f"데이터베이스 연결 실패: {str(e)}"}, status_code=500)

    if not rows or not rows[0].get("mfa_secret") or not rows[0].get("mfa_enabled"):
        return JSONResponse({"error": "MFA 설정을 찾을 수 없습니다."}, status_code=400)

    # 복호화 및 TOTP 검증
    try:
        mfa_secret = decrypt_mfa_secret(rows[0]["mfa_secret"])
    except Exception:
        return JSONResponse({"error": "MFA 비밀키 복호화에 실패했습니다. 관리자에게 문의하세요."}, status_code=500)

    totp = pyotp.TOTP(mfa_secret)
    if not totp.verify(code):
        return JSONResponse({"error": "인증 코드가 올바르지 않습니다."}, status_code=401)

    # 최종 로그인 세션 발급 및 임시 세션 정리
    request.session.pop("mfa_pending_email", None)
    request.session.pop("mfa_pending_user_id", None)
    request.session.pop("mfa_pending_is_admin", None)
    request.session.pop("mfa_pending_access_token", None)

    request.session["user_email"] = email
    request.session["access_token"] = access_token
    request.session["is_admin"] = is_admin
    request.session["bot_user_id"] = user_id

    return JSONResponse({"ok": True})


@router.post("/api/mfa/setup")
async def api_mfa_setup(request: Request):
    email = _require_login(request)
    if not email:
        return JSONResponse({"error": "로그인이 필요합니다."}, status_code=401)

    # 세션에서 bot_user_id 정보 획득
    user_id = request.session.get("bot_user_id")
    if not user_id:
        return JSONResponse({"error": "연동된 봇 유저 정보가 없습니다."}, status_code=400)

    # 새로운 TOTP 보안키 생성
    mfa_secret = pyotp.random_base32()
    provisioning_uri = pyotp.totp.TOTP(mfa_secret).provisioning_uri(
        name=email,
        issuer_name="supabot-manager"
    )

    # QR 코드를 프론트엔드에서 렌더링하기 용이하게 QR API URL 제공
    import urllib.parse
    encoded_uri = urllib.parse.quote(provisioning_uri)
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={encoded_uri}"

    # 임시 키를 DB에 암호화하여 저장 (mfa_enabled는 여전히 False)
    try:
        db = get_db()
        enc_secret = encrypt_mfa_secret(mfa_secret)
        db.table("users").update({
            "mfa_secret": enc_secret,
            "mfa_enabled": False
        }).eq("user_id", user_id).execute()
    except Exception as e:
        return JSONResponse({"error": f"데이터베이스 업데이트 실패: {str(e)}"}, status_code=500)

    return JSONResponse({
        "secret": mfa_secret,
        "qr_url": qr_url
    })


@router.post("/api/mfa/enable")
async def api_mfa_enable(request: Request):
    email = _require_login(request)
    if not email:
        return JSONResponse({"error": "로그인이 필요합니다."}, status_code=401)

    user_id = request.session.get("bot_user_id")
    if not user_id:
        return JSONResponse({"error": "연동된 봇 유저 정보가 없습니다."}, status_code=400)

    try:
        body = await request.json()
        code = body.get("code", "").strip()
    except Exception:
        return JSONResponse({"error": "올바르지 않은 요청입니다."}, status_code=400)

    if not code:
        return JSONResponse({"error": "인증 코드를 입력해주세요."}, status_code=400)

    # DB에서 설정 중인 mfa_secret 로드
    try:
        db = get_db()
        rows = db.table("users").select("mfa_secret").eq("user_id", user_id).execute().data
    except Exception as e:
        return JSONResponse({"error": f"데이터베이스 조회 실패: {str(e)}"}, status_code=500)

    if not rows or not rows[0].get("mfa_secret"):
        return JSONResponse({"error": "설정 중인 MFA 정보가 없습니다. 다시 시작해주세요."}, status_code=400)

    try:
        mfa_secret = decrypt_mfa_secret(rows[0]["mfa_secret"])
    except Exception:
        return JSONResponse({"error": "비밀키 복호화에 실패했습니다."}, status_code=500)

    # TOTP 검증
    totp = pyotp.TOTP(mfa_secret)
    if not totp.verify(code):
        return JSONResponse({"error": "인증 코드가 올바르지 않습니다. 다시 입력해주세요."}, status_code=400)

    # 검증 성공 시 최종 활성화
    try:
        db.table("users").update({"mfa_enabled": True}).eq("user_id", user_id).execute()
    except Exception as e:
        return JSONResponse({"error": f"데이터베이스 업데이트 실패: {str(e)}"}, status_code=500)

    return JSONResponse({"ok": True})


@router.post("/api/mfa/disable")
async def api_mfa_disable(request: Request):
    email = _require_login(request)
    if not email:
        return JSONResponse({"error": "로그인이 필요합니다."}, status_code=401)

    user_id = request.session.get("bot_user_id")
    if not user_id:
        return JSONResponse({"error": "연동된 봇 유저 정보가 없습니다."}, status_code=400)

    try:
        body = await request.json()
        code = body.get("code", "").strip()
    except Exception:
        return JSONResponse({"error": "올바르지 않은 요청입니다."}, status_code=400)

    if not code:
        return JSONResponse({"error": "인증 코드를 입력해주세요."}, status_code=400)

    try:
        db = get_db()
        rows = db.table("users").select("mfa_secret").eq("user_id", user_id).execute().data
    except Exception as e:
        return JSONResponse({"error": f"데이터베이스 조회 실패: {str(e)}"}, status_code=500)

    if not rows or not rows[0].get("mfa_secret"):
        return JSONResponse({"error": "등록된 MFA 설정이 없습니다."}, status_code=400)

    try:
        mfa_secret = decrypt_mfa_secret(rows[0]["mfa_secret"])
    except Exception:
        return JSONResponse({"error": "비밀키 복호화에 실패했습니다."}, status_code=500)

    totp = pyotp.TOTP(mfa_secret)
    if not totp.verify(code):
        return JSONResponse({"error": "인증 코드가 올바르지 않습니다. 다시 입력해주세요."}, status_code=400)

    # 비활성화 및 초기화
    try:
        db.table("users").update({
            "mfa_enabled": False,
            "mfa_secret": None
        }).eq("user_id", user_id).execute()
    except Exception as e:
        return JSONResponse({"error": f"데이터베이스 업데이트 실패: {str(e)}"}, status_code=500)

    return JSONResponse({"ok": True})
