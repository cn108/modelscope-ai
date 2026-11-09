from apps.accounts.models import User

REGISTER_URL = "/api/v1/auth/register/"
LOGIN_URL = "/api/v1/auth/login/"
REFRESH_URL = "/api/v1/auth/refresh/"
ME_URL = "/api/v1/auth/me/"

PASSWORD = "Str0ng-Passw0rd!"


def test_register_returns_tokens_and_hashes_password(api_client, db):
    response = api_client.post(
        REGISTER_URL,
        {
            "email": "New@Example.com",
            "password": PASSWORD,
            "display_name": " New ",
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "new@example.com"
    assert body["user"]["display_name"] == "New"
    assert body["tokens"]["access"]
    assert body["tokens"]["refresh"]

    stored = User.objects.get(email="new@example.com")
    assert stored.password.startswith("argon2$")
    assert stored.check_password(PASSWORD)


def test_register_duplicate_email_conflicts(api_client, user):
    response = api_client.post(
        REGISTER_URL,
        {"email": "OWNER@example.com", "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_register_weak_password_is_rejected(api_client):
    response = api_client.post(
        REGISTER_URL,
        {"email": "weak@example.com", "password": "short"},
        format="json",
    )
    assert response.status_code == 400
    assert "password" in response.json()["error"]["details"]


def test_login_returns_tokens_case_insensitively(api_client, user):
    response = api_client.post(
        LOGIN_URL,
        {"email": "OWNER@example.com", "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["tokens"]["access"]
    assert response.json()["user"]["email"] == user.email


def test_login_rejects_bad_credentials_without_enumeration(api_client, user):
    payloads = [
        {"email": user.email, "password": "wrong-password"},
        {"email": "nobody@example.com", "password": "wrong-password"},
    ]
    messages = set()
    for payload in payloads:
        response = api_client.post(LOGIN_URL, payload, format="json")
        assert response.status_code == 401
        messages.add(response.json()["error"]["message"])
    assert messages == {"Invalid email or password."}


def test_me_requires_authentication(api_client):
    assert api_client.get(ME_URL).status_code == 401


def test_me_returns_profile_for_bearer_token(api_client, user):
    login = api_client.post(
        LOGIN_URL,
        {"email": user.email, "password": PASSWORD},
        format="json",
    ).json()
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {login['tokens']['access']}"
    )
    response = api_client.get(ME_URL)
    assert response.status_code == 200
    assert response.json()["email"] == user.email


def test_refresh_rotates_and_blacklists_the_old_token(api_client, db):
    register = api_client.post(
        REGISTER_URL,
        {"email": "refresh@example.com", "password": PASSWORD},
        format="json",
    ).json()
    refresh = register["tokens"]["refresh"]

    rotated = api_client.post(REFRESH_URL, {"refresh": refresh}, format="json")
    assert rotated.status_code == 200
    assert rotated.json()["access"]
    assert rotated.json()["refresh"] != refresh

    reused = api_client.post(REFRESH_URL, {"refresh": refresh}, format="json")
    assert reused.status_code == 401
