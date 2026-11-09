import pytest


@pytest.fixture()
def fernet_key_env(settings):
    """Configure a throwaway encryption key for tests only."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    settings.PROVIDER_SECRET_KEYS = [key]
    return key


@pytest.fixture()
def user(db):
    from apps.accounts.models import User

    return User.objects.create_user(
        email="owner@example.com",
        password="Str0ng-Passw0rd!",
        display_name="Owner",
    )


@pytest.fixture()
def other_user(db):
    from apps.accounts.models import User

    return User.objects.create_user(
        email="member@example.com",
        password="Str0ng-Passw0rd!",
        display_name="Member",
    )


@pytest.fixture()
def third_user(db):
    from apps.accounts.models import User

    return User.objects.create_user(
        email="viewer@example.com",
        password="Str0ng-Passw0rd!",
        display_name="Viewer",
    )


@pytest.fixture()
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture()
def authenticated_client():
    from rest_framework.test import APIClient

    def _client(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _client
