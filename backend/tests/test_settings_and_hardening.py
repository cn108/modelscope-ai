import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.projects.models import Project
from apps.providers.models import ProviderConfig
from apps.workspaces.models import Membership
from apps.workspaces.services import add_member, create_workspace
from common.throttling import LoginRateThrottle, ModelCallRateThrottle

PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture()
def client(user):
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture()
def workspace(user):
    return create_workspace(user=user, name="Settings workspace")


@pytest.fixture()
def project(workspace, user):
    return Project.objects.create(
        workspace=workspace, name="Settings project", created_by=user
    )


def test_profile_and_preferences_are_validated_and_persisted(
    client, user, workspace
):
    response = client.patch(
        "/api/v1/auth/me/",
        {
            "display_name": "  Ada Lovelace  ",
            "preferences": {
                "timezone": "Europe/London",
                "date_format": "iso",
                "default_workspace": str(workspace.id),
                "landing_page": "playground",
            },
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["display_name"] == "Ada Lovelace"
    assert body["preferences"]["timezone"] == "Europe/London"
    assert body["preferences"]["default_workspace"] == str(workspace.id)
    user.refresh_from_db()
    assert user.preferences["landing_page"] == "playground"

    invalid_zone = client.patch(
        "/api/v1/auth/me/",
        {"preferences": {"timezone": "Mars/Olympus"}},
        format="json",
    )
    assert invalid_zone.status_code == 400
    assert "timezone" in invalid_zone.json()["error"]["details"]["preferences"]

    foreign = create_workspace(user=User.objects.create_user(
        email="other@example.com", password=PASSWORD
    ), name="Not yours")
    invalid_workspace = client.patch(
        "/api/v1/auth/me/",
        {"preferences": {"default_workspace": str(foreign.id)}},
        format="json",
    )
    assert invalid_workspace.status_code == 400
    assert (
        "default_workspace"
        in invalid_workspace.json()["error"]["details"]["preferences"]
    )


def test_change_password_revokes_refresh_tokens_and_rejects_wrong_password(
    api_client, user
):
    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": PASSWORD},
        format="json",
    ).json()
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {login['tokens']['access']}"
    )
    wrong = api_client.post(
        "/api/v1/auth/change-password/",
        {"current_password": "not-the-password", "new_password": "An0ther-Pass!"},
        format="json",
    )
    assert wrong.status_code == 400

    changed = api_client.post(
        "/api/v1/auth/change-password/",
        {"current_password": PASSWORD, "new_password": "An0ther-Pass!"},
        format="json",
    )
    assert changed.status_code == 200, changed.content
    assert changed.json()["refresh_tokens_revoked"] >= 1

    reused = api_client.post(
        "/api/v1/auth/refresh/",
        {"refresh": login["tokens"]["refresh"]},
        format="json",
    )
    assert reused.status_code == 401

    new_login = api_client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": "An0ther-Pass!"},
        format="json",
    )
    assert new_login.status_code == 200


def test_account_and_workspace_audit_events_are_scoped(client, user, workspace):
    client.post("/api/v1/auth/login/", {"email": user.email, "password": PASSWORD})
    account = client.get("/api/v1/auth/audit/")
    assert account.status_code == 200
    actions = [row["action"] for row in account.json()["results"]]
    assert "auth.login_succeeded" in actions

    workspace_audit = client.get(f"/api/v1/workspaces/{workspace.id}/audit/")
    assert workspace_audit.status_code == 200
    assert any(
        row["action"] == "workspace.created"
        for row in workspace_audit.json()["results"]
    )

    viewer = User.objects.create_user(email="viewer@example.com", password=PASSWORD)
    add_member(
        actor=user,
        workspace_id=workspace.id,
        email=viewer.email,
        role=Membership.Role.VIEWER,
    )
    viewer_client = APIClient()
    viewer_client.force_authenticate(user=viewer)
    denied = viewer_client.get(f"/api/v1/workspaces/{workspace.id}/audit/")
    assert denied.status_code == 403


def test_about_endpoint_is_authenticated_and_safe(api_client, client):
    assert api_client.get("/api/v1/about/").status_code == 401
    response = client.get("/api/v1/about/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "ModelScope AI"
    assert body["version"]
    assert body["features"]["observability_retention_days"] >= 0
    assert "SECRET" not in str(body).upper()


def test_login_rate_limit_returns_429(api_client, user, monkeypatch):
    monkeypatch.setitem(LoginRateThrottle.THROTTLE_RATES, "login", "1/min")
    payload = {"email": user.email, "password": "wrong-password"}
    assert api_client.post("/api/v1/auth/login/", payload, format="json").status_code == 401
    limited = api_client.post("/api/v1/auth/login/", payload, format="json")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "throttled"


def test_model_execution_rate_limit_returns_429(
    client, project, monkeypatch
):
    provider = ProviderConfig.objects.create(
        project=project,
        name="Local Ollama",
        kind=ProviderConfig.Kind.OLLAMA,
        endpoint="http://localhost:11434",
    )

    def fake_request(**kwargs):
        return {
            "message": {"content": "ok"},
            "prompt_eval_count": 1,
            "eval_count": 1,
            "done_reason": "stop",
        }

    monkeypatch.setattr("integrations.providers.adapters.request_json", fake_request)
    monkeypatch.setitem(ModelCallRateThrottle.THROTTLE_RATES, "model_call", "1/min")
    payload = {
        "user_prompt": "Hello",
        "models": [{"provider": str(provider.id), "model_id": "llama3.2:1b"}],
    }
    first = client.post(
        f"/api/v1/projects/{project.id}/executions/", payload, format="json"
    )
    assert first.status_code == 201, first.content
    second = client.post(
        f"/api/v1/projects/{project.id}/executions/", payload, format="json"
    )
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "throttled"
