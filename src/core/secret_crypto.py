import os

from cryptography.fernet import Fernet, InvalidToken


ENC_PREFIX = "enc:v1:"


def is_encrypted_secret(value):
    return isinstance(value, str) and value.startswith(ENC_PREFIX)


def has_secret_key():
    return bool(os.getenv("USER_SECRET_KEY", "").strip())


def _fernet():
    key = os.getenv("USER_SECRET_KEY", "").strip()
    if not key:
        raise ValueError("USER_SECRET_KEY is required to encrypt user secrets")
    return Fernet(key.encode())


def encrypt_secret(value):
    text = str(value or "").strip()
    if not text or is_encrypted_secret(text):
        return text
    token = _fernet().encrypt(text.encode()).decode()
    return f"{ENC_PREFIX}{token}"


def decrypt_secret(value):
    text = str(value or "")
    if not text or not is_encrypted_secret(text):
        return text
    try:
        return _fernet().decrypt(text[len(ENC_PREFIX):].encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise ValueError("stored secret cannot be decrypted") from exc
