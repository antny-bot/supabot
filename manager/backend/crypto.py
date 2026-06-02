import os
import base64
import time
import json
from hashlib import sha256
from cryptography.fernet import Fernet

def _get_fernet() -> Fernet:
    secret = os.environ.get("SESSION_SECRET", "change-me-in-production-must-be-32-bytes-long-minimum-or-more")
    # Generate 32-byte key for Fernet from SESSION_SECRET
    key_bytes = sha256(secret.encode()).digest()
    key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(key)

def encrypt_mfa_secret(plain_secret: str) -> str:
    if not plain_secret:
        return ""
    f = _get_fernet()
    return f.encrypt(plain_secret.encode()).decode()

def decrypt_mfa_secret(enc_secret: str) -> str:
    if not enc_secret:
        return ""
    f = _get_fernet()
    try:
        return f.decrypt(enc_secret.encode()).decode()
    except Exception:
        raise ValueError("stored mfa secret cannot be decrypted")

def create_trusted_token(user_id: str, days: int = 30) -> str:
    """Create an encrypted token for a trusted device."""
    payload = {
        "uid": user_id,
        "exp": int(time.time()) + (days * 86400)
    }
    f = _get_fernet()
    return f.encrypt(json.dumps(payload).encode()).decode()

def verify_trusted_token(token: str) -> str | None:
    """Verify a trusted device token and return user_id if valid."""
    if not token:
        return None
    f = _get_fernet()
    try:
        decrypted = f.decrypt(token.encode()).decode()
        payload = json.loads(decrypted)
        
        # Check expiration
        if payload.get("exp", 0) < int(time.time()):
            return None
            
        return payload.get("uid")
    except Exception:
        return None
