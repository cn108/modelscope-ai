from decimal import Decimal
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.datasets.models import Dataset, DatasetRecord
from apps.evaluations.models import Evaluation, EvaluationModel, EvaluationResult
from apps.evaluations.services import _build_judge
from apps.observability.models import Span, Trace
from apps.projects.models import Project
from apps.providers.models import ProviderConfig
from apps.workspaces.models import Membership
from apps.workspaces.services import add_member, create_workspace
from integrations.providers.base import GenerationResult
from integrations.providers.http import ProviderRequestError


@pytest.fixture()
def project(user):
    workspace = create_workspace(user=user, name="Observability")
    return Project.objects.create(
        workspace=workspace, name="Observability project", created_by=user
    )


@pytest.fixture()
def provider(project):
    return ProviderConfig.objects.create(
        project=project,
        name="Local Ollama",
        kind=ProviderConfig.Kind.OLLAMA,
        endpoint="http://localhost:11434",
        settings={"temperature": 0.1},
    )


@pytest.fixture()
def dataset(project, user):
    dataset = Dataset.objects.create(
        project=project, name="Observability QA", created_by=user
    )
    DatasetRecord.objects.create(
        dataset=dataset, position=1, input="What is 2+2?", expected_output="4"
    )
    DatasetRecord.objects.create(
        dataset=dataset,
        position=2,
        input="Capital of France?",
        expected_output="Paris",
        context=["Paris is the capital of France."],
    )
    return dataset


@pytest.fixture()
def owner_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture()
def viewer_client(user, other_user, project):
    add_member(
        actor=user,
        workspace_id=project.workspace_id,
        email=other_user.email,
        role=Membership.Role.VIEWER,
    )
    client = APIClient()
    client.force_authenticate(user=other_user)
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
        if model == "no-token-model":
            return {"message": {"content": "No usage"}, "done_reason": "stop"}
        prompt = " ".join(
            message.get("content", "")
            for message in payload.get("messages", [])
            if isinstance(message, dict)
        )
        content = "4" if "2+2" in prompt else "Paris" if "France" in prompt else "ok"
        return {
            "message": {"content": content},
            "prompt_eval_count": 12,
            "eval_count": 8,
            "done_reason": "stop",
        }

    monkeypatch.setattr("integrations.providers.adapters.request_json", fake_request)
    return calls


def run_playground(client, project, provider, model_id="llama3.2"):
    return client.post(
        f"/api/v1/projects/{project.id}/executions/",
        {
            "system_prompt": "Be terse.",
            "user_prompt": "Say hello.",
            "parameters": {"max_tokens": 64},
            "models": [{"provider": str(provider.id), "model_id": model_id}],
        },
        format="json",
    )


def start_evaluation(client, project, dataset, provider, **extra):
    payload = {
        "dataset": str(dataset.id),
        "metrics": ["exact_match", "token_f1"],
        "models": [{"provider": str(provider.id), "model_id": "llama3.2"}],
    }
    payload.update(extra)
    return client.post(
        f"/api/v1/projects/{project.id}/evaluations/", payload, format="json"
    )


def summary(client, project, **params):
    return client.get(f"/api/v1/projects/{project.id}/observability/", params)


def traces(client, project, **params):
    return client.get(
        f"/api/v1/projects/{project.id}/observability/traces/", params
    )


def test_playground_execution_creates_linked_trace_and_span_tree(
    owner_client, project, provider, fake_provider
):
    response = run_playground(owner_client, project, provider)
    assert response.status_code == 201, response.content
    result = response.json()["results"][0]

    trace = Trace.objects.get()
    assert trace.source == Trace.Source.PLAYGROUND
    assert trace.role == Trace.Role.MODEL
    assert trace.status == Trace.Status.SUCCEEDED
    assert str(trace.execution_result_id) == result["id"]
    assert trace.provider_id == provider.id
    assert trace.provider_name == "Local Ollama"
    assert trace.model_id == "llama3.2"
    assert trace.input_tokens == 12
    assert trace.output_tokens == 8
    assert trace.duration_ms is not None
    assert trace.provider_latency_ms is not None
    assert trace.cost_status == Trace.CostStatus.UNAVAILABLE
    assert trace.estimated_cost is None
    assert "No pricing is configured" in trace.cost_detail

    spans = list(trace.spans.order_by("sequence"))
    assert [span.name for span in spans] == ["provider.prepare", "provider.generate"]
    assert all(span.parent_id is None for span in spans)
    assert spans[0].status == Span.Status.OK
    assert spans[1].kind == Span.Kind.CLIENT
    assert spans[1].attributes["gen_ai.usage.input_tokens"] == 12

    listing = traces(owner_client, project)
    assert listing.status_code == 200, listing.content
    page = listing.json()
    assert page["count"] == 1
    row = page["results"][0]
    assert row["id"] == str(trace.id)
    assert row["source_label"] == "Playground"
    assert row["request_preview"] == "Say hello."
    assert row["link"]["execution_id"] == response.json()["id"]
    assert row["cost_status"] == "unavailable"

    detail = owner_client.get(f"/api/v1/observability/traces/{trace.id}/")
    assert detail.status_code == 200, detail.content
    body = detail.json()
    assert body["request"]["kind"] == "playground"
    assert body["request"]["system_prompt"] == "Be terse."
    assert body["response"] == "ok"
    assert len(body["spans"]) == 2
    assert body["spans"][1]["name"] == "provider.generate"


def test_failed_provider_call_records_error_on_trace_and_span(
    owner_client, project, provider, fake_provider
):
    response = run_playground(owner_client, project, provider, "broken-model")
    assert response.status_code == 201, response.content
    assert response.json()["status"] == "failed"

    trace = Trace.objects.get()
    assert trace.status == Trace.Status.FAILED
    assert trace.error["category"] == "network_error"
    generate = trace.spans.get(name="provider.generate")
    assert generate.status == Span.Status.ERROR
    assert generate.error["category"] == "network_error"

    data = summary(owner_client, project).json()
    assert data["totals"]["calls"] == 1
    assert data["totals"]["failed"] == 1
    assert data["errors"][0]["category"] == "network_error"


def test_configured_pricing_records_an_explicit_estimate(
    owner_client, project, provider, fake_provider, settings
):
    settings.EXECUTION_PRICING = {
        "ollama:llama3.2": {
            "input_per_million": "1.00",
            "output_per_million": "2.00",
            "currency": "USD",
        }
    }
    response = run_playground(owner_client, project, provider)
    assert response.status_code == 201, response.content
    result = response.json()["results"][0]
    assert Decimal(result["estimated_cost"]) == Decimal("0.000028")
    assert result["cost_currency"] == "USD"

    trace = Trace.objects.get()
    assert trace.cost_status == Trace.CostStatus.ESTIMATED
    assert trace.estimated_cost == Decimal("0.000028")
    assert trace.cost_currency == "USD"

    data = summary(owner_client, project).json()
    assert data["cost_status"] == "estimated"
    assert data["costs"] == [{"currency": "USD", "amount": "0.000028", "calls": 1}]
    assert data["totals"]["estimated_cost_calls"] == 1
    assert data["totals"]["unavailable_cost_calls"] == 0


def test_cost_stays_unavailable_when_tokens_are_missing(
    owner_client, project, provider, fake_provider, settings
):
    settings.EXECUTION_PRICING = {
        "ollama:no-token-model": {
            "input_per_million": "1.00",
            "output_per_million": "2.00",
            "currency": "USD",
        }
    }
    run_playground(owner_client, project, provider, "no-token-model")
    trace = Trace.objects.get()
    assert trace.input_tokens is None
    assert trace.cost_status == Trace.CostStatus.UNAVAILABLE
    assert "Token usage was not reported" in trace.cost_detail
    data = summary(owner_client, project).json()
    assert data["cost_status"] == "unavailable"
    assert data["costs"] == []


def test_dashboard_aggregates_filters_and_workspace_permissions(
    owner_client, viewer_client, third_user, project, provider, fake_provider
):
    run_playground(owner_client, project, provider, "llama3.2")
    run_playground(owner_client, project, provider, "broken-model")

    data = summary(owner_client, project).json()
    assert data["totals"]["calls"] == 2
    assert data["totals"]["succeeded"] == 1
    assert data["totals"]["failed"] == 1
    assert data["totals"]["avg_latency_ms"] is not None
    assert data["facets"]["models"] == ["broken-model", "llama3.2"]
    assert data["facets"]["providers"][0]["id"] == str(provider.id)
    assert data["models"][0]["model_id"] == "broken-model"
    assert data["models"][0]["failure_rate"] == 1.0
    assert data["telemetry"]["enabled"] is True

    failed = summary(owner_client, project, status="failed").json()
    assert failed["totals"]["calls"] == 1
    assert failed["totals"]["failed"] == 1
    assert failed["models"][0]["model_id"] == "broken-model"

    by_model = summary(owner_client, project, model="llama3.2").json()
    assert by_model["totals"]["calls"] == 1
    assert by_model["totals"]["succeeded"] == 1

    by_provider = summary(owner_client, project, provider=str(provider.id)).json()
    assert by_provider["totals"]["calls"] == 2

    by_source = summary(owner_client, project, source="playground").json()
    assert by_source["totals"]["calls"] == 2

    empty = summary(owner_client, project, **{"from": "2100-01-01"}).json()
    assert empty["totals"]["calls"] == 0
    assert empty["cost_status"] == "unavailable"
    assert empty["trend"] == []

    invalid = summary(owner_client, project, **{"from": "not-a-date"})
    assert invalid.status_code == 400
    invalid_status = summary(owner_client, project, status="unknown")
    assert invalid_status.status_code == 400

    viewer = summary(viewer_client, project)
    assert viewer.status_code == 200
    assert traces(viewer_client, project).status_code == 200

    outsider = APIClient()
    outsider.force_authenticate(user=third_user)
    foreign_workspace = create_workspace(user=third_user, name="Foreign")
    foreign_project = Project.objects.create(
        workspace=foreign_workspace, name="Foreign project"
    )
    assert summary(outsider, foreign_project).json()["totals"]["calls"] == 0
    assert summary(outsider, project).status_code == 404
    assert summary(APIClient(), project).status_code == 401

    trace = Trace.objects.first()
    assert (
        outsider.get(f"/api/v1/observability/traces/{trace.id}/").status_code
        == 404
    )
    assert (
        owner_client.get(f"/api/v1/observability/traces/{trace.id}/").status_code
        == 200
    )


def test_evaluation_creates_a_trace_per_case_with_metric_child_spans(
    owner_client, project, dataset, provider, fake_provider
):
    response = start_evaluation(owner_client, project, dataset, provider)
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "completed"

    rows = list(
        Trace.objects.filter(source=Trace.Source.EVALUATION).order_by("started_at")
    )
    assert len(rows) == 2
    for trace in rows:
        assert trace.role == Trace.Role.MODEL
        assert trace.status == Trace.Status.SUCCEEDED
        assert trace.evaluation_result_id is not None
        assert trace.input_tokens == 12
        assert trace.provider_latency_ms is not None
        names = list(trace.spans.order_by("sequence").values_list("name", flat=True))
        assert names[0] == "provider.prepare"
        assert names[1] == "provider.generate"
        assert "metrics.evaluate" in names
        assert "metrics.exact_match" in names
        assert "metrics.token_f1" in names
        parent = trace.spans.get(name="metrics.evaluate")
        children = trace.spans.filter(parent=parent)
        assert children.count() == 2
        assert {child.name for child in children} == {
            "metrics.exact_match",
            "metrics.token_f1",
        }

    listing = traces(owner_client, project)
    assert listing.status_code == 200
    assert listing.json()["count"] == 2
    assert listing.json()["results"][0]["link"]["source"] == "evaluation"

    data = summary(owner_client, project, source="evaluation").json()
    assert data["totals"]["calls"] == 2
    assert data["totals"]["succeeded"] == 2
    assert data["models"][0]["roles"] == {"model": 2}


def test_deleting_a_linked_evaluation_removes_its_traces_and_spans(
    owner_client, project, dataset, provider, fake_provider
):
    response = start_evaluation(owner_client, project, dataset, provider)
    assert response.status_code == 201, response.content
    assert Trace.objects.count() == 2
    assert Span.objects.exists()

    Evaluation.objects.get(pk=response.json()["id"]).delete()

    assert Trace.objects.count() == 0
    assert Span.objects.count() == 0


def test_judge_calls_are_recorded_as_separate_traces(
    owner_client, project, provider, monkeypatch
):
    evaluation = Evaluation.objects.create(
        project=project,
        dataset_name="Judge dataset",
        judge_provider=provider,
        judge_provider_name=provider.name,
        judge_model_id="judge-model",
        metrics=["answer_relevancy"],
    )
    model_row = EvaluationModel.objects.create(
        evaluation=evaluation,
        position=1,
        provider=provider,
        provider_name=provider.name,
        provider_kind=provider.kind,
        model_id="llama3.2",
    )
    result = EvaluationResult.objects.create(
        evaluation=evaluation,
        model=model_row,
        record_position=1,
        input="What is 2+2?",
        expected_output="4",
    )

    class FakeAdapter:
        def generate(self, request):
            return GenerationResult(
                provider="ollama",
                model_id=request.model_id,
                content="judge answer",
                input_tokens=20,
                output_tokens=10,
                tokens_are_provider_reported=True,
                latency_ms=12.5,
            )

    monkeypatch.setattr("apps.providers.services.adapter_for", lambda provider: FakeAdapter())
    judge = _build_judge(
        evaluation, [SimpleNamespace(requires_judge=True)]
    )
    assert judge is not None
    judge.observer.result = result
    judge.generate("Judge this answer.")

    trace = Trace.objects.get(role=Trace.Role.JUDGE)
    assert trace.evaluation_result_id == result.pk
    assert trace.provider_name == provider.name
    assert trace.model_id == "judge-model"
    assert trace.input_tokens == 20
    assert trace.output_tokens == 10
    assert trace.status == Trace.Status.SUCCEEDED
    assert trace.request_text == "Judge this answer."
    assert trace.response_text == "judge answer"
    assert trace.spans.get(name="judge.call").status == Span.Status.OK

    detail = owner_client.get(f"/api/v1/observability/traces/{trace.id}/").json()
    assert detail["request"]["kind"] == "judge"
    assert detail["request"]["prompt"] == "Judge this answer."
    assert detail["response"] == "judge answer"
