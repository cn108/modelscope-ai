import json
import urllib.error

import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.providers.models import ProviderConfig, ProviderSecret
from apps.workspaces.models import Membership
from apps.workspaces.services import add_member, create_workspace
from common.audit.models import AuditEvent
from common.encryption.service import decrypt_secret
from integrations.providers.adapters import (
    OllamaAdapter,
    ZaiAdapter,
    validate_ollama_endpoint,
)
from integrations.providers.base import GenerationRequest
from integrations.providers.http import ProviderRequestError, request_json


def provider_payload(kind="ollama", **overrides):
    payload = {"name": "Local test", "kind": kind, "settings": {}}
    if kind == "ollama":
        payload["endpoint"] = "http://localhost:11434/api"
    if kind == "zai":
        payload.update(endpoint="https://api.z.ai/api/paas/v4", api_key="test-secret-value")
    payload.update(overrides)
    return payload


@pytest.fixture()
def project(user):
    workspace = create_workspace(user=user, name="Providers")
    return Project.objects.create(workspace=workspace, name="Provider project", created_by=user)


@pytest.fixture()
def owner_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_create_provider_encrypts_key_and_never_returns_it(owner_client, project, fernet_key_env):
    response = owner_client.post(
        f"/api/v1/projects/{project.id}/providers/",
        provider_payload("zai", name="Cloud test"),
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert "api_key" not in body
    assert body["has_secret"] is True

    provider = ProviderConfig.objects.get(pk=body["id"])
    stored = ProviderSecret.objects.get(provider=provider)
    assert b"test-secret-value" not in bytes(stored.encrypted_value)
    assert decrypt_secret(stored.encrypted_value) == "test-secret-value"
    assert AuditEvent.objects.filter(action="provider.created", target_id=provider.id).exists()


def test_ollama_provider_does_not_need_secret(owner_client, project):
    response = owner_client.post(
        f"/api/v1/projects/{project.id}/providers/", provider_payload(), format="json"
    )
    assert response.status_code == 201
    assert response.json()["has_secret"] is False


def test_provider_list_is_scoped_to_project_and_user(owner_client, project, other_user):
    created = owner_client.post(
        f"/api/v1/projects/{project.id}/providers/", provider_payload(), format="json"
    )
    foreign_workspace = create_workspace(user=other_user, name="Foreign")
    foreign_project = Project.objects.create(workspace=foreign_workspace, name="Foreign project")
    foreign = owner_client.get(f"/api/v1/projects/{foreign_project.id}/providers/")
    assert foreign.status_code == 404
    listing = owner_client.get(f"/api/v1/projects/{project.id}/providers/")
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()] == [created.json()["id"]]
    assert "api_key" not in json.dumps(listing.json())


def test_members_can_read_but_only_admins_can_mutate_provider(owner_client, user, other_user, project):
    created = owner_client.post(
        f"/api/v1/projects/{project.id}/providers/", provider_payload(), format="json"
    )
    provider_id = created.json()["id"]
    add_member(actor=user, workspace_id=project.workspace_id, email=other_user.email, role=Membership.Role.MEMBER)
    client = APIClient()
    client.force_authenticate(user=other_user)

    assert client.get(f"/api/v1/providers/{provider_id}/").status_code == 200
    assert client.post(f"/api/v1/providers/{provider_id}/test/").status_code == 403
    assert client.patch(
        f"/api/v1/providers/{provider_id}/", {"name": "Unauthorized"}, format="json"
    ).status_code == 403


def test_unauthenticated_provider_access_is_denied(project):
    response = APIClient().get(f"/api/v1/projects/{project.id}/providers/")
    assert response.status_code == 401


def test_zai_models_and_normalizes_completion(monkeypatch):
    def fake_request(**kwargs):
        assert kwargs["url"] == "https://api.z.ai/api/paas/v4/chat/completions"
        assert kwargs["api_key"] == "not-in-response"
        return {
            "id": "request-123",
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

    monkeypatch.setattr("integrations.providers.adapters.request_json", fake_request)
    adapter = ZaiAdapter("not-in-response")
    result = adapter.generate(GenerationRequest(model_id="glm-5.3", messages=[{"role": "user", "content": "hi"}]))
    assert result.content == "OK"
    assert result.input_tokens == 5
    assert result.output_tokens == 2
    assert result.tokens_are_provider_reported is True
    assert result.request_id == "request-123"
    assert result.error is None
    assert {model.model_id for model in adapter.list_models()} == {"glm-5.3", "glm-5.3-flash"}


def test_ollama_models_and_normalizes_completion(monkeypatch):
    def fake_request(**kwargs):
        if kwargs["url"].endswith("/api/tags"):
            return {"models": [{"name": "llama3.2", "details": {"family": "llama"}}]}
        return {
            "message": {"content": "local response"},
            "prompt_eval_count": 11,
            "eval_count": 7,
            "done_reason": "stop",
        }

    monkeypatch.setattr("integrations.providers.adapters.request_json", fake_request)
    adapter = OllamaAdapter("http://localhost:11434/api")
    assert adapter.list_models()[0].model_id == "llama3.2"
    result = adapter.generate(GenerationRequest(model_id="llama3.2", messages=[]))
    assert result.content == "local response"
    assert result.input_tokens == 11
    assert result.output_tokens == 7
    assert result.tokens_are_provider_reported is True
    assert result.request_id is None


def test_ollama_target_allowlist_blocks_ssrf():
    assert validate_ollama_endpoint("http://localhost:11434/api") == "http://localhost:11434"
    assert validate_ollama_endpoint("http://host.docker.internal:11434/api") == "http://host.docker.internal:11434"
    for endpoint in (
        "http://169.254.169.254:11434/api",
        "http://192.168.1.5:11434/api",
        "https://evil.example/api",
        "http://user:password@localhost:11434/api",
        "http://localhost:9999/api",
    ):
        with pytest.raises(ValueError):
            validate_ollama_endpoint(endpoint)


def test_connection_errors_are_redacted(monkeypatch):
    def fail_request(**kwargs):
        raise ProviderRequestError("authentication_failed", "Provider rejected the configured credentials.", 401)

    monkeypatch.setattr("integrations.providers.adapters.request_json", fail_request)
    result = ZaiAdapter("secret-that-must-not-escape").validate_connection()
    assert result.ok is False
    assert "secret-that-must-not-escape" not in (result.detail or "")
    assert "secret-that-must-not-escape" not in json.dumps(result.__dict__)


def test_missing_encryption_key_returns_clear_503(owner_client, project, settings):
    settings.PROVIDER_SECRET_KEYS = []
    response = owner_client.post(
        f"/api/v1/projects/{project.id}/providers/",
        provider_payload("zai", name="Unconfigured"),
        format="json",
    )
    assert response.status_code == 503
    assert "credential storage is not configured" in response.json()["error"]["message"]
    assert "PROVIDER_SECRET_KEYS" not in response.content.decode()
    assert not ProviderConfig.objects.filter(name="Unconfigured").exists()


def test_provider_transport_does_not_follow_redirects(monkeypatch):
    class RedirectingOpener:
        def open(self, request, timeout):
            assert request.get_header("Authorization") == "Bearer private-key"
            raise urllib.error.HTTPError(
                request.full_url,
                302,
                "Found",
                {"Location": "http://127.0.0.1:8000/internal"},
                None,
            )

    monkeypatch.setattr("urllib.request.build_opener", lambda *handlers: RedirectingOpener())
    with pytest.raises(ProviderRequestError, match="redirects are not allowed"):
        request_json(url="https://provider.example/", api_key="private-key")
