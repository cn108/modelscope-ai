import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.datasets.models import Dataset, DatasetRecord
from apps.evaluations.models import Evaluation, EvaluationResult
from apps.evaluations.services import create_evaluation
from apps.evaluations.tasks import run_evaluation
from apps.projects.models import Project
from apps.providers.models import ProviderConfig
from apps.workspaces.models import Membership
from apps.workspaces.services import add_member, create_workspace
from integrations.providers.http import ProviderRequestError


@pytest.fixture()
def project(user):
    workspace = create_workspace(user=user, name="Evaluations")
    return Project.objects.create(
        workspace=workspace, name="Evaluation project", created_by=user
    )


@pytest.fixture()
def dataset(project, user):
    dataset = Dataset.objects.create(
        project=project, name="Support QA", description="", created_by=user
    )
    DatasetRecord.objects.create(
        dataset=dataset,
        position=1,
        input="What is 2+2?",
        expected_output="4",
    )
    DatasetRecord.objects.create(
        dataset=dataset,
        position=2,
        input="Capital of France?",
        expected_output="Paris",
        context=["France's capital is Paris."],
    )
    # Simulate prior edits so the snapshot version is meaningful.
    Dataset.objects.filter(pk=dataset.pk).update(version=3)
    dataset.refresh_from_db()
    return dataset


@pytest.fixture()
def dataset_without_reference(project, user):
    dataset = Dataset.objects.create(
        project=project, name="Open questions", created_by=user
    )
    DatasetRecord.objects.create(dataset=dataset, position=1, input="Say something nice")
    return dataset


@pytest.fixture()
def provider(project):
    return ProviderConfig.objects.create(
        project=project,
        name="Local Ollama",
        kind=ProviderConfig.Kind.OLLAMA,
        endpoint="http://localhost:11434",
        settings={"temperature": 0.2},
    )


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
            raise ProviderRequestError(
                "network_error", "Could not reach the provider endpoint."
            )
        prompt = " ".join(
            message.get("content", "")
            for message in payload.get("messages", [])
            if isinstance(message, dict)
        )
        if "2+2" in prompt:
            content = "4"
        elif "France" in prompt:
            content = "Paris"
        else:
            content = f"Answer from {model}"
        return {
            "message": {"content": content},
            "prompt_eval_count": 10,
            "eval_count": 5,
            "done_reason": "stop",
        }

    monkeypatch.setattr("integrations.providers.adapters.request_json", fake_request)
    return calls


def payload_for(dataset, provider, model_ids=None, metrics=None, **extra):
    payload = {
        "dataset": str(dataset.id),
        "metrics": metrics or ["exact_match", "token_f1"],
        "models": [
            {"provider": str(provider.id), "model_id": model_id}
            for model_id in (model_ids or ["llama3.2"])
        ],
    }
    payload.update(extra)
    return payload


def start(client, project, dataset, provider, **kwargs):
    return client.post(
        f"/api/v1/projects/{project.id}/evaluations/",
        payload_for(dataset, provider, **kwargs),
        format="json",
    )


def results(client, evaluation_id, **params):
    return client.get(f"/api/v1/evaluations/{evaluation_id}/results/", params)


def test_eager_evaluation_persists_per_case_results_and_summary(
    owner_client, project, dataset, provider, fake_provider
):
    response = start(owner_client, project, dataset, provider)
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "completed"
    assert body["dataset_name"] == "Support QA"
    assert body["dataset_version"] == 3
    assert body["total_cases"] == 2
    assert body["total_results"] == 2
    assert body["completed_cases"] == 2
    assert body["failed_cases"] == 0

    model_summary = body["models"][0]["summary"]
    assert model_summary["succeeded"] == 2
    assert model_summary["failed"] == 0
    assert model_summary["metric_averages"]["exact_match"] == 1.0
    assert model_summary["metric_averages"]["token_f1"] == 1.0
    assert body["summary"]["totals"]["succeeded"] == 2
    assert body["summary"]["totals"]["records"] == 2
    assert body["summary"]["totals"]["case_results"] == 2

    rows = results(owner_client, body["id"])
    assert rows.status_code == 200
    page = rows.json()
    assert page["count"] == 2
    first = page["results"][0]
    assert first["record_position"] == 1
    assert first["expected_output"] == "4"
    assert first["generated_response"] == "4"
    assert first["input_tokens"] == 10
    assert first["output_tokens"] == 5
    assert first["status"] == "succeeded"
    assert first["scores"]["exact_match"] == 1.0
    assert first["metric_results"][0]["metric"] == "exact_match"
    assert first["metric_results"][0]["passed"] is True

    second = page["results"][1]
    assert second["context"] == ["France's capital is Paris."]
    assert second["generated_response"] == "Paris"

    assert (
        EvaluationResult.objects.filter(evaluation_id=body["id"]).count() == 2
    )
    # Provider settings are applied on top of evaluation/model parameters.
    assert fake_provider[0]["options"] == {"temperature": 0.2}


def test_evaluation_is_queued_and_snapshots_records(
    owner_client, project, dataset, provider, monkeypatch
):
    class Deferred:
        id = "task-123"

    monkeypatch.setattr(
        "apps.evaluations.tasks.run_evaluation.delay", lambda *a, **k: Deferred()
    )
    response = start(owner_client, project, dataset, provider)
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "queued"
    assert body["completed_cases"] == 0

    evaluation = Evaluation.objects.get(pk=body["id"])
    assert evaluation.task_id == "task-123"
    assert evaluation.status == Evaluation.Status.QUEUED

    # Editing the dataset after queueing must not rewrite the frozen snapshot.
    record = dataset.records.get(position=1)
    record.input = "Rewritten input"
    record.save(update_fields=["input"])
    dataset.records.filter(position=2).delete()

    rows = results(owner_client, body["id"]).json()
    assert rows["count"] == 2
    assert {row["input"] for row in rows["results"]} == {
        "What is 2+2?",
        "Capital of France?",
    }
    assert owner_client.get(f"/api/v1/evaluations/{body['id']}/").json()[
        "dataset_version"
    ] == 3


def test_rerun_creates_a_new_evaluation_and_keeps_history(
    owner_client, project, dataset, provider, fake_provider
):
    first = start(owner_client, project, dataset, provider).json()
    first_completed_at = Evaluation.objects.get(pk=first["id"]).completed_at
    first_rows = list(
        EvaluationResult.objects.filter(evaluation_id=first["id"]).values(
            "record_position", "status", "scores", "generated_response"
        )
    )

    rerun = owner_client.post(f"/api/v1/evaluations/{first['id']}/rerun/")
    assert rerun.status_code == 201, rerun.content
    second = rerun.json()
    assert second["id"] != first["id"]
    assert second["status"] == "completed"
    assert second["dataset_version"] == first["dataset_version"]
    assert second["total_cases"] == first["total_cases"]
    assert Evaluation.objects.count() == 2

    # The original run is untouched by the replay.
    Evaluation.objects.get(pk=first["id"]).refresh_from_db()
    assert (
        list(
            EvaluationResult.objects.filter(evaluation_id=first["id"]).values(
                "record_position", "status", "scores", "generated_response"
            )
        )
        == first_rows
    )
    assert Evaluation.objects.get(pk=first["id"]).completed_at == first_completed_at


def test_rerun_uses_the_original_snapshot_after_dataset_deletion(
    owner_client, project, dataset, provider, fake_provider
):
    first = start(owner_client, project, dataset, provider).json()
    assert owner_client.delete(f"/api/v1/datasets/{dataset.id}/").status_code == 204

    rerun = owner_client.post(f"/api/v1/evaluations/{first['id']}/rerun/")
    assert rerun.status_code == 201, rerun.content
    second = rerun.json()
    assert second["status"] == "completed"
    assert second["dataset"] is None
    assert second["dataset_name"] == "Support QA"
    rows = results(owner_client, second["id"]).json()["results"]
    assert [row["input"] for row in rows] == [
        "What is 2+2?",
        "Capital of France?",
    ]


def test_one_model_failure_does_not_discard_the_other_model(
    owner_client, project, dataset, provider, fake_provider
):
    response = start(
        owner_client,
        project,
        dataset,
        provider,
        model_ids=["llama3.2", "broken-model"],
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "completed"
    assert body["failed_cases"] == 2
    assert body["total_results"] == 4
    statuses = {row["model_id"]: row["status"] for row in body["models"]}
    assert statuses == {"llama3.2": "completed", "broken-model": "failed"}

    rows = results(owner_client, body["id"]).json()["results"]
    broken = [row for row in rows if row["model_id"] == "broken-model"]
    good = [row for row in rows if row["model_id"] == "llama3.2"]
    assert len(broken) == 2 and len(good) == 2
    assert all(row["status"] == "failed" for row in broken)
    assert all(row["error"]["category"] == "network_error" for row in broken)
    assert all(row["scores"] == {} for row in broken)
    assert all(row["status"] == "succeeded" for row in good)
    assert all(row["scores"]["exact_match"] == 1.0 for row in good)


def test_all_models_failing_marks_the_run_failed(
    owner_client, project, dataset, provider, fake_provider
):
    response = start(
        owner_client, project, dataset, provider, model_ids=["broken-model"]
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["category"] == "all_cases_failed"
    assert body["failed_cases"] == 2
    assert body["completed_cases"] == 2
    rows = results(owner_client, body["id"]).json()["results"]
    assert all(row["status"] == "failed" for row in rows)


def test_missing_expected_answer_is_reported_per_metric(
    owner_client, project, dataset_without_reference, provider, fake_provider
):
    response = start(
        owner_client,
        project,
        dataset_without_reference,
        provider,
        metrics=["exact_match"],
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "completed"
    row = results(owner_client, body["id"]).json()["results"][0]
    assert row["status"] == "succeeded"
    assert row["generated_response"]
    assert row["scores"] == {}
    assert "expected answer" in row["metric_results"][0]["error"]
    assert body["models"][0]["summary"]["metric_averages"] == {}


def test_judge_metrics_require_and_record_a_judge(
    owner_client, project, dataset, provider, fake_provider, monkeypatch
):
    missing = start(
        owner_client, project, dataset, provider, metrics=["faithfulness"]
    )
    assert missing.status_code == 400
    assert "judge" in str(missing.json()).lower()

    monkeypatch.setattr(
        "integrations.evaluation.registry.judge_score",
        lambda *a, **k: {
            "score": 0.75,
            "passed": True,
            "threshold": 0.5,
            "reason": "Supported by context.",
        },
    )
    response = start(
        owner_client,
        project,
        dataset,
        provider,
        metrics=["faithfulness"],
        judge={"provider": str(provider.id), "model_id": "judge-model"},
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "completed"
    assert body["judge"]["model_id"] == "judge-model"
    rows = results(owner_client, body["id"]).json()["results"]
    judged = [row for row in rows if row["record_position"] == 2][0]
    assert judged["scores"]["faithfulness"] == 0.75
    assert judged["metric_results"][0]["reason"] == "Supported by context."
    without_context = [row for row in rows if row["record_position"] == 1][0]
    assert "retrieval context" in without_context["metric_results"][0]["error"]


def test_evaluation_validation(owner_client, user, project, dataset, provider):
    unknown_metric = start(
        owner_client, project, dataset, provider, metrics=["does_not_exist"]
    )
    assert unknown_metric.status_code == 400

    duplicate_models = start(
        owner_client, project, dataset, provider, model_ids=["llama3.2", "llama3.2"]
    )
    assert duplicate_models.status_code == 400

    other_workspace = create_workspace(user=user, name="Elsewhere")
    other_project = Project.objects.create(
        workspace=other_workspace, name="Elsewhere", created_by=user
    )
    foreign_provider = ProviderConfig.objects.create(
        project=other_project,
        name="Foreign",
        kind=ProviderConfig.Kind.OLLAMA,
        endpoint="http://localhost:11434",
    )
    foreign = start(owner_client, project, dataset, foreign_provider)
    assert foreign.status_code == 400

    foreign_dataset = Dataset.objects.create(
        project=other_project, name="Foreign data", created_by=user
    )
    DatasetRecord.objects.create(dataset=foreign_dataset, position=1, input="x")
    mismatched = start(owner_client, project, foreign_dataset, provider)
    assert mismatched.status_code == 400

    empty = Dataset.objects.create(project=project, name="Empty", created_by=user)
    empty_response = start(owner_client, project, empty, provider)
    assert empty_response.status_code == 400
    assert Evaluation.objects.count() == 0


def test_viewer_and_cross_tenant_permissions(
    owner_client, user, other_user, project, dataset, provider, fake_provider
):
    evaluation = start(owner_client, project, dataset, provider).json()
    add_member(
        actor=user,
        workspace_id=project.workspace_id,
        email=other_user.email,
        role=Membership.Role.VIEWER,
    )
    viewer = APIClient()
    viewer.force_authenticate(user=other_user)
    assert viewer.get(f"/api/v1/evaluations/{evaluation['id']}/").status_code == 200
    assert (
        viewer.get(f"/api/v1/evaluations/{evaluation['id']}/results/").status_code
        == 200
    )
    viewer_run = start(viewer, project, dataset, provider)
    assert viewer_run.status_code == 403
    assert (
        viewer.post(f"/api/v1/evaluations/{evaluation['id']}/rerun/").status_code
        == 403
    )

    outsider = APIClient()
    outsider.force_authenticate(user=other_user)
    # A viewer is not a member of a different tenant's workspace; reuse a fresh
    # user without membership for the cross-tenant check.
    from apps.accounts.models import User

    stranger = User.objects.create_user(
        email="stranger@example.com", password="Str0ng-Passw0rd!"
    )
    outsider.force_authenticate(user=stranger)
    assert outsider.get(f"/api/v1/evaluations/{evaluation['id']}/").status_code == 404
    assert outsider.get(f"/api/v1/projects/{project.id}/evaluations/").status_code == 404


def test_queue_failure_is_surfaced(
    owner_client, project, dataset, provider, monkeypatch
):
    def fail(*args, **kwargs):
        raise RuntimeError("broker down")

    monkeypatch.setattr("apps.evaluations.tasks.run_evaluation.delay", fail)
    response = start(owner_client, project, dataset, provider)
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["category"] == "queue_unavailable"


def test_celery_task_processes_a_queued_evaluation(
    user, project, dataset, provider, fake_provider, monkeypatch
):
    class Deferred:
        id = "task-456"

    monkeypatch.setattr(
        "apps.evaluations.tasks.run_evaluation.delay", lambda *a, **k: Deferred()
    )
    client = APIClient()
    client.force_authenticate(user=user)
    queued = start(client, project, dataset, provider).json()
    assert queued["status"] == "queued"
    assert Evaluation.objects.get(pk=queued["id"]).task_id == "task-456"

    outcome = run_evaluation.apply(args=[queued["id"]]).get()
    assert outcome["status"] == "completed"

    evaluation = Evaluation.objects.get(pk=queued["id"])
    assert evaluation.status == Evaluation.Status.COMPLETED
    assert evaluation.completed_cases == 2
    assert evaluation.started_at is not None
    assert evaluation.completed_at is not None
    assert evaluation.summary["totals"]["succeeded"] == 2
    # A worker records its own task id when it picks the run up.
    assert evaluation.task_id


def test_create_evaluation_service_snapshots_every_model(
    user, project, dataset, provider, fake_provider
):
    evaluation = create_evaluation(
        actor=user,
        project_id=project.id,
        validated_data={
            "dataset": dataset.id,
            "metrics": ["token_f1"],
            "models": [
                {"provider": provider.id, "model_id": "llama3.2"},
                {"provider": provider.id, "model_id": "second-model"},
            ],
            "parameters": {"max_tokens": 64},
        },
    )
    assert evaluation.status == Evaluation.Status.QUEUED
    assert evaluation.models.count() == 2
    assert evaluation.results.count() == 4
    assert evaluation.dataset_version == dataset.version
    assert evaluation.parameters == {"max_tokens": 64}
    assert evaluation.models.first().parameters == {}


def test_human_reviews_and_disagreement_summary(
    owner_client, user, other_user, project, dataset, provider, fake_provider
):
    evaluation = start(owner_client, project, dataset, provider).json()
    row = results(owner_client, evaluation["id"]).json()["results"][0]
    url = f"/api/v1/evaluations/{evaluation['id']}/results/{row['id']}/reviews/"

    first = owner_client.post(
        url, {"label": "pass", "note": "Looks correct."}, format="json"
    )
    assert first.status_code == 200, first.content
    assert first.json()["reviewer_email"] == user.email

    add_member(
        actor=user,
        workspace_id=project.workspace_id,
        email=other_user.email,
        role=Membership.Role.MEMBER,
    )
    second_client = APIClient()
    second_client.force_authenticate(user=other_user)
    second = second_client.post(
        url, {"label": "fail", "note": "The answer is incomplete."}, format="json"
    )
    assert second.status_code == 200, second.content

    reviews = owner_client.get(url).json()
    assert {item["label"] for item in reviews} == {"pass", "fail"}
    detail = owner_client.get(f"/api/v1/evaluations/{evaluation['id']}/").json()
    assert detail["review_summary"]["disagreements"] == 1
    assert detail["review_summary"]["agreement_rate"] == 0.0

    viewer_client = APIClient()
    viewer = User.objects.create_user(
        email="review-viewer@example.com", password="Str0ng-Passw0rd!"
    )
    add_member(
        actor=user,
        workspace_id=project.workspace_id,
        email=viewer.email,
        role=Membership.Role.VIEWER,
    )
    viewer_client.force_authenticate(user=viewer)
    denied = viewer_client.post(url, {"label": "pass"}, format="json")
    assert denied.status_code == 403


def test_evaluations_are_listed_newest_first(
    owner_client, project, dataset, provider, fake_provider
):
    first = start(owner_client, project, dataset, provider).json()
    second = start(owner_client, project, dataset, provider).json()
    listing = owner_client.get(f"/api/v1/projects/{project.id}/evaluations/")
    assert listing.status_code == 200
    ids = [row["id"] for row in listing.json()]
    assert ids[:2] == [second["id"], first["id"]]
