# -*- coding: utf-8 -*-
"""Google Drive REST API 연동 및 토큰 관리 모듈 (Manager Backend 전용)."""

import base64
from hashlib import sha256
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Tuple
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("manager.gdrive")

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
DEFAULT_TIMEOUT = 15.0
ENC_PREFIX = "enc:v1:"


def _get_fernet() -> Optional[Fernet]:
    """공통 키(USER_SECRET_KEY 또는 MANAGER_API_KEY 또는 SESSION_SECRET)로부터 Fernet 객체를 생성합니다."""
    key = os.environ.get("USER_SECRET_KEY", "").strip()
    if key:
        try:
            return Fernet(key.encode())
        except Exception:
            # 32바이트 urlsafe 키가 아닌 임의 문자열인 경우 sha256으로 해싱하여 생성
            derived = base64.urlsafe_b64encode(sha256(key.encode()).digest())
            return Fernet(derived)

    fallback = os.environ.get("MANAGER_API_KEY", "").strip() or os.environ.get("SESSION_SECRET", "").strip()
    if fallback:
        derived = base64.urlsafe_b64encode(sha256(fallback.encode()).digest())
        return Fernet(derived)

    return None


def encrypt_token(plain_token: str) -> str:
    """토큰을 암호화합니다."""
    text = str(plain_token or "").strip()
    if not text:
        return ""
    if text.startswith(ENC_PREFIX):
        return text
    f = _get_fernet()
    if not f:
        return text
    enc = f.encrypt(text.encode()).decode()
    return f"{ENC_PREFIX}{enc}"


def decrypt_token(enc_token: str) -> str:
    """암호화된 토큰을 복호화합니다."""
    text = str(enc_token or "").strip()
    if not text:
        return ""
    if not text.startswith(ENC_PREFIX):
        return text
    f = _get_fernet()
    if not f:
        return text
    raw_enc = text[len(ENC_PREFIX):]
    try:
        return f.decrypt(raw_enc.encode()).decode()
    except (InvalidToken, Exception) as err:
        logger.warning("Failed to decrypt token: %s", err)
        return text


def exchange_code_for_tokens(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """OAuth Authorization code를 access_token 및 refresh_token으로 교환합니다."""
    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        err_body = error.read().decode("utf-8", errors="ignore")
        logger.error("Failed to exchange code for tokens: %s", err_body)
        raise ValueError("Google OAuth 토큰 교환에 실패했습니다.") from error


def fetch_google_user_email(access_token: str) -> str:
    """Access token을 사용하여 연동된 Google 사용자 이메일을 조회합니다."""
    req = urllib.request.Request(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("email", "")
    except Exception as error:
        logger.warning("Failed to fetch Google user email: %s", error)
        return ""
