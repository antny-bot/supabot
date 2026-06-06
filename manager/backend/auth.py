import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode

import httpx
import requests


def supabase_sign_in(email: str, password: str) -> dict | None:
    """Returns user dict with access_token on success, None on failure."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not anon_key:
        return None
    try:
        resp = requests.post(
            f"{url}/auth/v1/token?grant_type=password",
            json={"email": email, "password": password},
            headers={"apikey": anon_key, "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.ok:
            return resp.json()
    except Exception:
        pass
    return None


def generate_pkce_pair() -> tuple[str, str]:
    """Returns (code_verifier, code_challenge) for PKCE OAuth flow."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def build_oauth_url(redirect_uri: str, code_challenge: str) -> str:
    """Constructs the Supabase authorize URL for Google OAuth with PKCE."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    params = urlencode({
        "provider": "google",
        "redirect_to": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    return f"{url}/auth/v1/authorize?{params}&apikey={anon_key}"


async def exchange_pkce_code(code: str, code_verifier: str) -> dict | None:
    """Exchanges authorization code for tokens via Supabase PKCE flow."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not anon_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{url}/auth/v1/token?grant_type=pkce",
                json={"auth_code": code, "code_verifier": code_verifier},
                headers={"apikey": anon_key, "Content-Type": "application/json"},
            )
            if resp.is_success:
                return resp.json()
    except Exception:
        pass
    return None
