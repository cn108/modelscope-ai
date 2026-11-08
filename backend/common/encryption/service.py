"""Authenticated encryption for provider credentials (specification §11).

Design:
- Fernet (AES-128-CBC + HMAC-SHA256) envelope encryption.
- Keys come ONLY from the PROVIDER_SECRET_KEYS setting (env-driven, outside DB
  and source control). Comma-separated list; first key encrypts, all keys can
  decrypt, enabling rotation: prepend new key, re-encrypt lazily, drop old key.
- Secrets must never be written to logs, traces, ordinary project JSON or
  plaintext columns. Call sites store the output of `encrypt_secret` only.

Key generation:  python -m cryptography.fernet  (or `Fernet.generate_key()`).
Rotation runbook: docs/adr/ADR-0003-secret-encryption.md
"""

from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken


class SecretCryptoError(RuntimeError):
    """Raised when encryption/decryption cannot be performed safely."""


def _fernets() -> list[Fernet]:
    keys = getattr(settings, "PROVIDER_SECRET_KEYS", [])
    if not keys:
        raise SecretCryptoError(
            "PROVIDER_SECRET_KEYS is not configured. Generate a key with "
            "`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` "
            "and set it in the environment (never in source control)."
        )
    try:
        return [Fernet(key.encode()) for key in keys]
    except Exception as exc:  # noqa: BLE001
        raise SecretCryptoError(f"Invalid PROVIDER_SECRET_KEYS configuration: {exc}") from exc


def encrypt_secret(plaintext: str) -> bytes:
    """Encrypt with the current (first) key. Returns url-safe token bytes."""
    if plaintext is None:
        raise SecretCryptoError("Cannot encrypt None.")
    return _fernets()[0].encrypt(plaintext.encode("utf-8"))


def decrypt_secret(token: bytes | str) -> str:
    """Try each configured key (supports rotation); raises InvalidToken if none match."""
    if isinstance(token, str):
        token = token.encode("utf-8")
    last_error: Exception | None = None
    for fernet in _fernets():
        try:
            return fernet.decrypt(token).decode("utf-8")
        except InvalidToken as exc:
            last_error = exc
    raise SecretCryptoError("Secret could not be decrypted with any configured key.") from last_error
