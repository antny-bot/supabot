import os

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
