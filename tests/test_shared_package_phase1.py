import pytest
from supabot_common.ticks import (
    get_tick_size as common_get_tick_size,
    get_krx_tick_size,
    get_crypto_tick_size,
    adjust_krx_price_to_tick,
    adjust_crypto_price_to_tick,
    adjust_us_price_to_tick,
)
from core.exchanges.common import CommonMixin
from manager.backend.services.order_planner import get_tick_size as planner_get_tick_size, adjust_price_to_tick as planner_adjust_price_to_tick
from supabot_common.crypto import encrypt_secret, decrypt_secret, is_encrypted_secret, has_secret_key
from core.secret_crypto import encrypt_secret as bot_encrypt, decrypt_secret as bot_decrypt


def test_tick_sizes_identical_between_bot_manager_shared():
    """모든 거래소/가격대에서 shared, bot(CommonMixin), manager(order_planner)의 틱사이즈 결과가 동일한지 검증."""
    test_cases_krx = [1500, 2000, 4990, 5000, 19900, 20000, 49950, 50000, 199500, 200000, 499000, 500000, 1000000]
    for p in test_cases_krx:
        krx_tick = get_krx_tick_size(p)
        assert CommonMixin.get_krx_tick_size(p) == krx_tick
        assert planner_get_tick_size(p, "kis") == krx_tick
        assert planner_get_tick_size(p, "toss") == krx_tick
        assert common_get_tick_size(p, "kis") == krx_tick

        adj_krx = adjust_krx_price_to_tick(p + 3)
        assert CommonMixin.adjust_krx_price_to_tick(p + 3) == adj_krx
        assert planner_adjust_price_to_tick(p + 3, "kis") == adj_krx

    test_cases_crypto = [0.05, 0.5, 5.0, 50.0, 500.0, 5000.0, 50000.0, 500000.0, 1500000.0, 2500000.0]
    for p in test_cases_crypto:
        crypto_tick = get_crypto_tick_size(p)
        assert CommonMixin.get_tick_size(p) == crypto_tick
        assert planner_get_tick_size(p, "upbit") == crypto_tick
        assert common_get_tick_size(p, "upbit") == crypto_tick

        adj_crypto = adjust_crypto_price_to_tick(p * 1.05)
        assert CommonMixin.adjust_price_to_tick(p * 1.05) == adj_crypto


def test_shared_crypto_identical(monkeypatch):
    """암복호화 로직이 supabot_common과 core.secret_crypto 간에 완전히 호환되는지 검증."""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("USER_SECRET_KEY", key)

    secret = "my-super-secret-api-key-12345"
    enc = encrypt_secret(secret)
    assert is_encrypted_secret(enc)

    # bot_decrypt can decrypt enc
    assert bot_decrypt(enc) == secret

    # bot_encrypt can be decrypted by shared decrypt_secret
    enc_bot = bot_encrypt(secret)
    assert decrypt_secret(enc_bot) == secret
