import pytest
from django.conf import settings

from common.encryption import SecretCryptoError, decrypt_secret, encrypt_secret


def test_roundtrip(fernet_key_env):
    token = encrypt_secret("sk-super-secret-value")
    assert b"sk-super-secret" not in token
    assert decrypt_secret(token) == "sk-super-secret-value"


def test_missing_key_raises_clear_error():
    settings.PROVIDER_SECRET_KEYS = []
    with pytest.raises(SecretCryptoError, match="PROVIDER_SECRET_KEYS is not configured"):
        encrypt_secret("x")


def test_rotation_decrypts_old_and_new(fernet_key_env):
    from cryptography.fernet import Fernet

    old_token = encrypt_secret("old-secret")
    new_key = Fernet.generate_key().decode()
    settings.PROVIDER_SECRET_KEYS = [new_key, *settings.PROVIDER_SECRET_KEYS]
    # Old ciphertext still decrypts during rotation window; new writes use new key.
    assert decrypt_secret(old_token) == "old-secret"
    assert decrypt_secret(encrypt_secret("fresh")) == "fresh"


def test_tampered_token_rejected(fernet_key_env):
    token = encrypt_secret("integrity")
    with pytest.raises(SecretCryptoError):
        decrypt_secret(token[:-4] + b"AAAA")
