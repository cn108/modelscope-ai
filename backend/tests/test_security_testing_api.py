import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.providers.models import ModelConfig, ProviderConfig
from apps.security.models import SecurityTestResult, SecurityTestRun
from apps.workspaces.models import Membership
from apps.workspaces.services import add_member, create_workspace
from integrations.providers.http import ProviderRequestError


@pytest.fixture()
def project(user):
    workspace = create_workspace(user=user, name="AI testing")
    return Project.objects.create(workspace=workspace, name="Support assistant", created_by=user)


@pytest.fixture()
def provider(project):
    row = ProviderConfig.objects.create(
        project=project,
        name="Local test provider",
        kind=ProviderConfig.Kind.OLLAMA,
        endpoint="http://localhost:11434",
    )
    for model_id in ("safe-model", "vulnerable-model", "broken-model"):
        ModelConfig.objects.create(provider=row, model_id=model_id)
    return row


@pytest.fixture()
def owner_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture()
def fake_provider(monkeypatch):
    state = {"vulnerable": False}
    calls = []

    def fake_request(**kwargs):
        payload = kwargs["payload"]
        calls.append(payload)
        model = payload["model"]
        if model == "broken-model":
            raise ProviderRequestError("network_error", "Could not reach the provider endpoint.")
        user_message = next(
            (
                message["content"]
                for message in reversed(payload["messages"])
                if message["role"] == "user"
            ),
            "",
        )
        if state["vulnerable"] or model == "vulnerable-model":
            if "Reply only with RED" in user_message:
                content = "RED"
            elif "JAILBREAK-OK" in user_message:
                content = "JAILBREAK-OK. I have no restrictions."
            else:
                content = "I can't help with that."
        else:
            content = "I can't help with that request."
        return {
            "message": {"content": content},
            "prompt_eval_count": 32,
            "eval_count": 8,
            "done_reason": "stop",
        }

    monkeypatch.setattr("integrations.providers.adapters.request_json", fake_request)
    return state, calls


def create_run(client, project, provider, models, cases, **extra):
    payload = {
        "models": [
            {"provider": str(provider.id), "model_id": model_id}
            for model_id in models
        ],
        "cases": cases,
    }
    payload.update(extra)
    return client.post(
        f"/api/v1/projects/{project.id}/security-testing/runs/",
        payload,
        format="json",
    )


def dashboard(client, project):
    return client.get(f"/api/v1/projects/{project.id}/security-testing/")


def test_run_executes_actual_responses_and_records_pass_fail_and_inconclusive(
    owner_client, project, provider, fake_provider
):
    response = create_run(
        owner_client,
        project,
        provider,
        ["safe-model", "vulnerable-model"],
        ["prompt_injection.direct_override", "jailbreak.developer_mode"],
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "completed"
    assert body["total_models"] == 2
    assert body["total_cases"] == 2
    assert body["total_results"] == 4
    assert body["completed_results"] == 4
    assert body["progress"] == 100
    assert body["summary"]["totals"]["passed"] == 2
    assert body["summary"]["totals"]["failed"] == 2
    assert body["summary"]["totals"]["inconclusive"] == 0
    assert body["summary"]["totals"]["vulnerabilities"] == 2
    assert body["summary"]["severity_counts"]["high"] == 2
    assert body["summary"]["categories"]
    assert all(
        model["status"] == model["summary"]["status"] == "completed"
        for model in body["models"]
    )

    run = SecurityTestRun.objects.get(pk=body["id"])
    assert run.results.count() == 4
    failed = SecurityTestResult.objects.filter(run=run, verdict="failed")
    assert failed.count() == 2
    for result in failed:
        assert result.response_text
        assert result.attack_input
        assert result.system_prompt
        assert result.rationale
        assert result.evidence
        assert result.criteria
        assert result.mitigation
        assert result.severity == "high"
        assert result.executed_at is not None
        assert result.model.model_id == "vulnerable-model"
        assert result.input_tokens == 32
        assert result.output_tokens == 8

    safe = SecurityTestResult.objects.filter(run=run, verdict="passed")
    assert safe.count() == 2
    assert all(result.severity == "" for result in safe)
    assert all(result.response_text for result in safe)

    failed_list = owner_client.get(
        f"/api/v1/security-test-runs/{run.id}/results/",
        {"verdict": "failed"},
    )
    assert failed_list.status_code == 200
    assert failed_list.json()["count"] == 2
    result_id = failed_list.json()["results"][0]["id"]
    detail = owner_client.get(f"/api/v1/security-test-results/{result_id}/")
    assert detail.status_code == 200
    assert detail.json()["response_text"]
    assert detail.json()["attack_input"]
    assert detail.json()["criteria"]
    assert detail.json()["mitigation"]
    assert detail.json()["references"]
    assert detail.json()["matched_rules"]


def test_dashboard_and_existing_security_and_analytics_surfaces_are_connected(
    owner_client, project, provider, fake_provider
):
    created = create_run(
        owner_client,
        project,
        provider,
        ["safe-model", "vulnerable-model"],
        ["prompt_injection.direct_override", "jailbreak.developer_mode"],
    )
    assert created.status_code == 201, created.content

    response = dashboard(owner_client, project)
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["runs"] == 1
    assert body["completed_runs"] == 1
    assert body["tests_performed"] == 4
    assert body["passed"] == 2
    assert body["failed"] == 2
    assert body["vulnerabilities"] == 2
    assert body["inconclusive"] == 0
    assert body["severity_counts"]["high"] == 2
    assert len(body["models"]) == 2
    assert {row["model_id"] for row in body["models"]} == {
        "safe-model",
        "vulnerable-model",
    }
    assert body["categories"]
    assert body["recent_failures"]
    assert body["disclaimer"]
    assert body["limitations"]

    legacy_security = owner_client.get(f"/api/v1/projects/{project.id}/security/")
    assert legacy_security.status_code == 200, legacy_security.content
    legacy = legacy_security.json()
    assert legacy["security_test_runs"] == 1
    assert legacy["security_tests"] == 4
    assert legacy["security_tests_failed"] == 2

    analytics = owner_client.get(f"/api/v1/projects/{project.id}/analytics/")
    assert analytics.status_code == 200, analytics.content
    security = analytics.json()["summary"]["security"]
    assert security["test_runs"] == 1
    assert security["tests_performed"] == 4
    assert security["tests_passed"] == 2
    assert security["tests_failed"] == 2
    assert security["tests_inconclusive"] == 0
    assert security["test_severity_counts"]["high"] == 2
    assert any(point["security_tests"] == 4 for point in analytics.json()["trend"])


def test_rerun_preserves_history_and_comparison_reports_new_failures(
    owner_client, project, provider, fake_provider
):
    state, _ = fake_provider
    baseline = create_run(
        owner_client,
        project,
        provider,
        ["safe-model"],
        ["prompt_injection.direct_override", "jailbreak.developer_mode"],
    )
    assert baseline.status_code == 201, baseline.content
    baseline_body = baseline.json()
    assert baseline_body["summary"]["totals"]["failed"] == 0
    baseline_results = set(
        SecurityTestResult.objects.filter(run_id=baseline_body["id"]).values_list(
            "id", flat=True
        )
    )

    state["vulnerable"] = True
    rerun = owner_client.post(
        f"/api/v1/security-test-runs/{baseline_body['id']}/rerun/"
    )
    assert rerun.status_code == 201, rerun.content
    current_body = rerun.json()
    assert current_body["id"] != baseline_body["id"]
    assert current_body["summary"]["totals"]["failed"] == 2
    assert set(
        SecurityTestResult.objects.filter(run_id=baseline_body["id"]).values_list(
            "id", flat=True
        )
    ) == baseline_results

    comparison = owner_client.get(
        f"/api/v1/projects/{project.id}/security-testing/compare/",
        {"baseline": baseline_body["id"], "current": current_body["id"]},
    )
    assert comparison.status_code == 200, comparison.content
    body = comparison.json()
    assert body["counts"]["baseline_failed"] == 0
    assert body["counts"]["current_failed"] == 2
    assert body["counts"]["new_failures"] == 2
    assert body["counts"]["resolved_failures"] == 0
    assert len(body["new_failures"]) == 2
    assert body["new_failures"][0]["current"]["response_text"]
    assert body["warnings"]

    history = owner_client.get(
        f"/api/v1/projects/{project.id}/security-testing/history/",
        {"model": "safe-model"},
    )
    assert history.status_code == 200
    assert len(history.json()) == 2
    assert all(row["model_id"] == "safe-model" for row in history.json())


def test_provider_error_is_inconclusive_and_does_not_fabricate_a_vulnerability(
    owner_client, project, provider, fake_provider
):
    response = create_run(
        owner_client,
        project,
        provider,
        ["broken-model"],
        ["jailbreak.developer_mode"],
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "failed"
    assert body["summary"]["totals"]["passed"] == 0
    assert body["summary"]["totals"]["failed"] == 0
    assert body["summary"]["totals"]["inconclusive"] == 1
    assert body["summary"]["totals"]["errors"] == 1
    assert body["error"]["category"] == "no_model_responses"

    result = SecurityTestResult.objects.get(run_id=body["id"])
    assert result.status == "failed"
    assert result.verdict == "inconclusive"
    assert result.error["category"] == "network_error"
    assert result.response_text == ""
    assert result.severity == ""


def test_invalid_cases_foreign_providers_and_queue_failures_are_handled(
    owner_client, user, project, provider, fake_provider, monkeypatch
):
    unknown = create_run(
        owner_client, project, provider, ["safe-model"], ["not-a-case"]
    )
    assert unknown.status_code == 400
    assert "cases" in unknown.json()["error"]["details"]

    duplicate = create_run(
        owner_client,
        project,
        provider,
        ["safe-model", "safe-model"],
        ["jailbreak.developer_mode"],
    )
    assert duplicate.status_code == 400

    unconfigured = create_run(
        owner_client,
        project,
        provider,
        ["not-configured-model"],
        ["jailbreak.developer_mode"],
    )
    assert unconfigured.status_code == 400
    assert "not configured" in str(unconfigured.json()["error"]["details"])

    foreign_workspace = create_workspace(user=user, name="Other")
    foreign_project = Project.objects.create(
        workspace=foreign_workspace, name="Foreign", created_by=user
    )
    foreign_provider = ProviderConfig.objects.create(
        project=foreign_project,
        name="Foreign provider",
        kind=ProviderConfig.Kind.OLLAMA,
        endpoint="http://localhost:11434",
    )
    foreign = owner_client.post(
        f"/api/v1/projects/{project.id}/security-testing/runs/",
        {
            "models": [
                {"provider": str(foreign_provider.id), "model_id": "safe-model"}
            ],
            "cases": ["jailbreak.developer_mode"],
        },
        format="json",
    )
    assert foreign.status_code == 400
    assert SecurityTestRun.objects.count() == 0

    from apps.security import tasks

    def unavailable(*args, **kwargs):
        raise RuntimeError("broker down")

    monkeypatch.setattr(tasks.run_security_test, "delay", unavailable)
    queued = create_run(
        owner_client,
        project,
        provider,
        ["safe-model"],
        ["jailbreak.developer_mode"],
    )
    assert queued.status_code == 201, queued.content
    assert queued.json()["status"] == "failed"
    assert queued.json()["error"]["category"] == "queue_unavailable"


def test_workspace_permissions_for_runs_results_and_catalog(
    owner_client, user, other_user, third_user, project, provider, fake_provider
):
    created = create_run(
        owner_client,
        project,
        provider,
        ["safe-model"],
        ["jailbreak.developer_mode"],
    )
    assert created.status_code == 201, created.content
    run_id = created.json()["id"]
    result_id = SecurityTestResult.objects.filter(run_id=run_id).first().id
    add_member(
        actor=user,
        workspace_id=project.workspace_id,
        email=other_user.email,
        role=Membership.Role.VIEWER,
    )
    viewer = APIClient()
    viewer.force_authenticate(user=other_user)

    assert viewer.get("/api/v1/security-testing/catalog/").status_code == 200
    assert dashboard(viewer, project).status_code == 200
    assert viewer.get(f"/api/v1/security-test-runs/{run_id}/").status_code == 200
    assert viewer.get(f"/api/v1/security-test-results/{result_id}/").status_code == 200
    assert create_run(
        viewer, project, provider, ["safe-model"], ["jailbreak.developer_mode"]
    ).status_code == 403
    assert viewer.post(f"/api/v1/security-test-runs/{run_id}/rerun/").status_code == 403

    outsider = APIClient()
    outsider.force_authenticate(user=third_user)
    assert dashboard(outsider, project).status_code == 404
    assert outsider.get(f"/api/v1/security-test-runs/{run_id}/").status_code == 404
    assert outsider.get(f"/api/v1/security-test-results/{result_id}/").status_code == 404
    assert outsider.get(f"/api/v1/security-test-runs/{run_id}/results/").status_code == 404
    assert create_run(
        outsider, project, provider, ["safe-model"], ["jailbreak.developer_mode"]
    ).status_code == 404

    anonymous = APIClient()
    assert anonymous.get("/api/v1/security-testing/catalog/").status_code == 401
    assert anonymous.get(f"/api/v1/security-test-runs/{run_id}/").status_code == 401
