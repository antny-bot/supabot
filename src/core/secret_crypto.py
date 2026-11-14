"""Backward compatibility module: forwards to supabot_common.crypto."""
from supabot_common.crypto import (
    ENC_PREFIX,
    is_encrypted_secret,
    has_secret_key,
    can_decrypt_secrets,
    encrypt_secret,
    decrypt_secret,
)
