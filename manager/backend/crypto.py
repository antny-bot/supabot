import os
import base64
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
