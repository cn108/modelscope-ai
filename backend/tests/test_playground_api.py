import pytest
from rest_framework.test import APIClient

from apps.playground.models import Execution, ExecutionResult
from apps.projects.models import Project
from apps.providers.models import ProviderConfig
from apps.workspaces.models import Membership
from apps.workspaces.services import add_member, create_workspace
from integrations.providers.http import ProviderRequestError


@pytest.fixture()
def project(user):
    workspace = create_workspace(user=user, name="Playground")
    return Project.objects.create(workspace=workspace, name="Playground project", created_by=user)


@pytest.fixture()
def providers(project):
    first = ProviderConfig.objects.create(
        project=project,
        name="Local A",
        kind=ProviderConfig.Kind.OLLAMA,
        endpoint="http://localhost:11434",
        settings={"temperature": 0.1},
    )
    second = ProviderConfig.objects.create(
        project=project,
        name="Local B",
        kind=ProviderConfig.Kind.OLLAMA,
        endpoint="http://localhost:11434",
    )
    return first, second


@pytest.fixture()
def owner_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture()
def fake_provider(monkeypatch):
    calls = []

    def fake_request(**kwargs):
        payload = kwargs["payload"]
        calls.append(payload)
        model = payload["model"]
        if model == "broken-model":
            raise ProviderRequestError("network_error", "Could not reach the provider endpoint.")
        return {
            "message": {"content": f"Reply from {model}"},
            "prompt_eval_count": 12,
            "eval_count": 8,
            "done_reason": "stop",
        }

    monkeypatch.setattr("integrations.providers.adapters.request_json", fake_request)
    return calls


def execute(client, project, models, **overrides):
    payload = {
        "system_prompt": "You are terse.",
        "user_prompt": "Say hello.",
        "parameters": {"max_tokens": 64},
        "models": models,
    }
    payload.update(overrides)
    return client.post(
        f"/api/v1/projects/{project.id}/executions/", payload, format="json"
    )


def test_single_execution_persists_response_and_metrics(owner_client, project, providers, fake_provider):
    first, _ = providers
    response = execute(owner_client, project, [{"provider": str(first.id), "model_id": "llama3.2"}])
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["mode"] == "single"
    assert body["status"] == "succeeded"
    assert body["system_prompt"] == "You are terse."
    assert body["user_prompt"] == "Say hello."
    assert body["parameters"] == {"max_tokens": 64}
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["provider_name"] == "Local A"
    assert result["model_id"] == "llama3.2"
    assert result["content"] == "Reply from llama3.2"
    assert result["input_tokens"] == 12
    assert result["output_tokens"] == 8
    assert result["latency_ms"] is not None
    assert result["estimated_cost"] is None
    assert result["error"] is None
    # Provider defaults are sent, then execution-level parameters.
    assert fake_provider[0]["options"] == {"temperature": 0.1, "max_tokens": 64}


def test_compare_keeps_success_when_the_other_model_fails(owner_client, project, providers, fake_provider):
    first, second = providers
    response = execute(
        owner_client,
        project,
        [
            {"provider": str(first.id), "model_id": "llama3.2"},
            {"provider": str(second.id), "model_id": "broken-model"},
        ],
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["mode"] == "compare"
    assert body["status"] == "partial"

    by_model = {row["model_id"]: row for row in body["results"]}
    assert by_model["llama3.2"]["status"] == "succeeded"
    assert by_model["llama3.2"]["content"] == "Reply from llama3.2"
    assert by_model["broken-model"]["status"] == "failed"
    assert by_model["broken-model"]["error"]["category"] == "network_error"
    assert by_model["broken-model"]["content"] == ""
    assert ExecutionResult.objects.filter(execution_id=body["id"]).count() == 2


def test_executions_list_is_scoped_and_ordered(owner_client, project, providers, fake_provider):
    first, _ = providers
    execute(owner_client, project, [{"provider": str(first.id), "model_id": "llama3.2"}])
    execute(owner_client, project, [{"provider": str(first.id), "model_id": "llama3.2"}])
    listing = owner_client.get(f"/api/v1/projects/{project.id}/executions/")
    assert listing.status_code == 200
    assert len(listing.json()) == 2


def test_prompt_edits_do_not_change_recorded_execution(owner_client, project, providers, fake_provider):
    first, _ = providers
    created = owner_client.post(
        f"/api/v1/projects/{project.id}/prompts/",
        {
            "name": "Greeting",
            "system_prompt": "Original system",
            "user_prompt": "Original user prompt",
            "parameters": {"temperature": 0.3},
        },
        format="json",
    )
    assert created.status_code == 201
    prompt_id = created.json()["id"]

    execution = execute(
        owner_client,
        project,
        [{"provider": str(first.id), "model_id": "llama3.2"}],
        prompt=prompt_id,
        system_prompt="Original system",
        user_prompt="Original user prompt",
        parameters={"temperature": 0.3},
    )
    assert execution.status_code == 201
    execution_id = execution.json()["id"]
    assert execution.json()["prompt_version"] == 1

    owner_client.patch(
        f"/api/v1/prompts/{prompt_id}/",
        {"system_prompt": "Rewritten system", "user_prompt": "Rewritten user prompt"},
        format="json",
    )

    stored = owner_client.get(f"/api/v1/executions/{execution_id}/").json()
    assert stored["system_prompt"] == "Original system"
    assert stored["user_prompt"] == "Original user prompt"
    assert stored["parameters"] == {"temperature": 0.3}


def test_rerun_replays_original_snapshot_without_mutating_it(owner_client, project, providers, fake_provider):
    first, _ = providers
    original = execute(
        owner_client,
        project,
        [{"provider": str(first.id), "model_id": "llama3.2"}],
        system_prompt="Frozen system",
        user_prompt="Frozen user prompt",
    ).json()

    rerun = owner_client.post(f"/api/v1/executions/{original['id']}/rerun/")
    assert rerun.status_code == 201, rerun.content
    body = rerun.json()
    assert body["id"] != original["id"]
    assert body["system_prompt"] == "Frozen system"
    assert body["user_prompt"] == "Frozen user prompt"
    assert body["results"][0]["content"] == "Reply from llama3.2"
    assert Execution.objects.count() == 2


def test_viewer_cannot_execute_but_can_read(owner_client, user, other_user, project, providers, fake_provider):
    first, _ = providers
    execution = execute(
        owner_client, project, [{"provider": str(first.id), "model_id": "llama3.2"}]
    ).json()
    add_member(
        actor=user,
        workspace_id=project.workspace_id,
        email=other_user.email,
        role=Membership.Role.VIEWER,
    )
    viewer = APIClient()
    viewer.force_authenticate(user=other_user)

    assert viewer.get(f"/api/v1/executions/{execution['id']}/").status_code == 200
    assert execute(
        viewer, project, [{"provider": str(first.id), "model_id": "llama3.2"}]
    ).status_code == 403


def test_cross_tenant_execution_access_is_404(owner_client, other_user, project, providers, fake_provider):
    first, _ = providers
    execution = execute(
        owner_client, project, [{"provider": str(first.id), "model_id": "llama3.2"}]
    ).json()
    outsider = APIClient()
    outsider.force_authenticate(user=other_user)
    assert outsider.get(f"/api/v1/executions/{execution['id']}/").status_code == 404
    assert outsider.get(f"/api/v1/projects/{project.id}/executions/").status_code == 404


def test_provider_from_another_project_is_rejected(owner_client, user, project, fake_provider):
    foreign_workspace = create_workspace(user=user, name="Other")
    foreign_project = Project.objects.create(workspace=foreign_workspace, name="Foreign")
    foreign_provider = ProviderConfig.objects.create(
        project=foreign_project, name="Foreign", kind=ProviderConfig.Kind.OLLAMA,
        endpoint="http://localhost:11434",
    )
    response = execute(
        owner_client, project, [{"provider": str(foreign_provider.id), "model_id": "x"}]
    )
    assert response.status_code == 400
    assert Execution.objects.count() == 0


def test_duplicate_or_excess_models_are_rejected(owner_client, project, providers):
    first, second = providers
    duplicate = execute(
        owner_client,
        project,
        [
            {"provider": str(first.id), "model_id": "llama3.2"},
            {"provider": str(first.id), "model_id": "llama3.2"},
        ],
    )
    assert duplicate.status_code == 400
    three = execute(
        owner_client,
        project,
        [
            {"provider": str(first.id), "model_id": "a"},
            {"provider": str(first.id), "model_id": "b"},
            {"provider": str(second.id), "model_id": "c"},
        ],
    )
    assert three.status_code == 400
