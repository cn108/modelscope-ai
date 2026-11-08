import pytest


@pytest.fixture()
def fernet_key_env(settings):
    """Configure a throwaway encryption key for tests only."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    settings.PROVIDER_SECRET_KEYS = [key]
    return key
