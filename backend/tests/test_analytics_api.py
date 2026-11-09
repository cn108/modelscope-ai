from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics.models import AnalyticsReport
from apps.evaluations.models import Evaluation, EvaluationModel
from apps.observability.models import Trace, TraceRollup, TraceRollupState
from apps.playground.models import Execution, ExecutionResult
from apps.projects.models import Project
from apps.providers.models import ProviderConfig
from apps.security.models import SecurityFinding, SecurityScan
from apps.workspaces.models import Membership
from apps.workspaces.services import add_member, create_workspace


@pytest.fixture()
def project(user):
    workspace = create_workspace(user=user, name="Analytics workspace")
    return Project.objects.create(
        workspace=workspace, name="Analytics project", created_by=user
    )


@pytest.fixture()
def provider(project):
    return ProviderConfig.objects.create(
        project=project,
        name="Analytics Ollama",
        kind=ProviderConfig.Kind.OLLAMA,
        endpoint="http://localhost:11434",
    )


@pytest.fixture()
def second_provider(project):
    return ProviderConfig.objects.create(
        project=project,
        name="Analytics Z.ai",
        kind=ProviderConfig.Kind.ZAI,
        endpoint="https://api.z.ai",
    )


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


def make_execution(
    *,
    project,
    provider,
    model_id,
    execution_status,
    when,
    latency_ms=100.0,
    input_tokens=100,
    output_tokens=50,
    cost=None,
    currency="",
):
    result_status = (
        ExecutionResult.Status.SUCCEEDED
        if execution_status == Execution.Status.SUCCEEDED
        else ExecutionResult.Status.FAILED
    )
    execution = Execution.objects.create(
        project=project,
        user_prompt="Analytics test prompt",
        system_prompt="",
        parameters={},
        status=execution_status,
        mode=Execution.Mode.SINGLE,
    )
    Execution.objects.filter(pk=execution.pk).update(created_at=when)
    result = ExecutionResult.objects.create(
        execution=execution,
        position=1,
        provider=provider,
        provider_name=provider.name,
        provider_kind=provider.kind,
        model_id=model_id,
        content="test response" if result_status == ExecutionResult.Status.SUCCEEDED else "",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tokens_are_provider_reported=input_tokens is not None,
        latency_ms=latency_ms,
        estimated_cost=cost,
        cost_currency=currency,
        status=result_status,
        error=None
        if result_status == ExecutionResult.Status.SUCCEEDED
        else {"category": "provider_error", "message": "Provider failed."},
    )
    ExecutionResult.objects.filter(pk=result.pk).update(created_at=when)
    trace = Trace.objects.create(
        project=project,
        source=Trace.Source.PLAYGROUND,
        role=Trace.Role.MODEL,
        execution_result=result,
        provider=provider,
        provider_name=provider.name,
        provider_kind=provider.kind,
        model_id=model_id,
        status=Trace.Status.SUCCEEDED
        if result_status == ExecutionResult.Status.SUCCEEDED
        else Trace.Status.FAILED,
        started_at=when,
        ended_at=when + timedelta(milliseconds=latency_ms),
        duration_ms=latency_ms + 5,
        provider_latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=cost,
        cost_currency=currency,
        cost_status=Trace.CostStatus.ESTIMATED
        if cost is not None
        else Trace.CostStatus.UNAVAILABLE,
        error=None
        if result_status == ExecutionResult.Status.SUCCEEDED
        else {"category": "provider_error", "message": "Provider failed."},
    )
    return execution, result, trace


def make_evaluation(
    *,
    project,
    provider,
    model_id,
    when,
    status=Evaluation.Status.COMPLETED,
    score=0.8,
    dataset_name="Analytics QA",
):
    evaluation = Evaluation.objects.create(
        project=project,
        dataset_name=dataset_name,
        dataset_version=1,
        status=status,
        metrics=["exact_match"],
        total_cases=2,
        completed_cases=2 if status == Evaluation.Status.COMPLETED else 0,
        failed_cases=0,
        summary={},
    )
    Evaluation.objects.filter(pk=evaluation.pk).update(created_at=when)
    EvaluationModel.objects.create(
        evaluation=evaluation,
        position=1,
        provider=provider,
        provider_name=provider.name,
        provider_kind=provider.kind,
        model_id=model_id,
        status=EvaluationModel.Status.COMPLETED
        if status == Evaluation.Status.COMPLETED
        else EvaluationModel.Status.FAILED,
        summary={
            "cases": 2,
            "succeeded": 2,
            "failed": 0,
            "avg_latency_ms": 90.0,
            "total_input_tokens": 40,
            "total_output_tokens": 20,
            "metric_averages": {"exact_match": score} if score is not None else {},
            "metric_scored_counts": {"exact_match": 2} if score is not None else {},
        },
    )
    return evaluation


def make_security(project, provider, when):
    execution, _, _ = make_execution(
        project=project,
        provider=provider,
        model_id="security-model",
        execution_status=Execution.Status.SUCCEEDED,
        when=when,
    )
    scan = SecurityScan.objects.create(
        project=project,
        target_type=SecurityScan.TargetType.EXECUTION,
        execution=execution,
        target_label="Analytics execution",
        target_identifier=str(execution.pk),
        checks=["pii", "unsafe_output"],
        status=SecurityScan.Status.COMPLETED,
        total_items=1,
        scanned_items=1,
        finding_count=1,
        highest_severity="high",
        completed_at=when,
    )
    SecurityScan.objects.filter(pk=scan.pk).update(created_at=when)
    finding = SecurityFinding.objects.create(
        scan=scan,
        project=project,
        check_key="unsafe_output",
        category="unsafe_output.violence",
        title="Potential violent content",
        description="Heuristic detection.",
        severity="high",
        disposition="warning",
        resource_type=SecurityFinding.ResourceType.EXECUTION_RESULT,
        resource_id=str(execution.pk),
        resource_label="Analytics execution",
        location="response",
        evidence="Redacted evidence.",
        remediation="Review the response.",
        detected_at=when,
        execution=execution,
    )
    return scan, finding


def analytics_url(project):
    return f"/api/v1/projects/{project.id}/analytics/"


def analytics(client, project, **params):
    return client.get(analytics_url(project), params)


def models_url(project):
    return f"/api/v1/projects/{project.id}/analytics/models/"


def reports_url(project):
    return f"/api/v1/projects/{project.id}/analytics/reports/"


def test_dashboard_aggregates_real_calls_executions_evaluations_costs_and_security(
    owner_client, viewer_client, third_user, project, provider, second_provider
):
    today = timezone.localdate()
    start = today - timedelta(days=6)
    within = timezone.now() - timedelta(days=1)
    make_execution(
        project=project,
        provider=provider,
        model_id="alpha",
        execution_status=Execution.Status.SUCCEEDED,
        when=within,
        latency_ms=120,
        input_tokens=100,
        output_tokens=50,
        cost=Decimal("0.000100"),
        currency="USD",
    )
    make_execution(
        project=project,
        provider=provider,
        model_id="alpha",
        execution_status=Execution.Status.FAILED,
        when=within,
        latency_ms=300,
        input_tokens=None,
        output_tokens=None,
    )
    make_execution(
        project=project,
        provider=second_provider,
        model_id="beta",
        execution_status=Execution.Status.PARTIAL,
        when=within,
        latency_ms=200,
        input_tokens=200,
        output_tokens=100,
        cost=Decimal("0.000200"),
        currency="USD",
    )
    make_evaluation(
        project=project,
        provider=provider,
        model_id="alpha",
        when=within,
        score=0.8,
    )
    make_evaluation(
        project=project,
        provider=second_provider,
        model_id="beta",
        when=within,
        score=0.6,
    )
    make_evaluation(
        project=project,
        provider=provider,
        model_id="alpha",
        when=within,
        status=Evaluation.Status.FAILED,
        score=None,
    )
    make_security(project, provider, within)

    response = analytics(
        owner_client,
        project,
        **{"from": start.isoformat(), "to": today.isoformat()},
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["range"]["from"] == start.isoformat()
    assert body["range"]["to"] == today.isoformat()
    assert body["range"]["days"] == 7
    assert body["summary"]["executions"] == {
        "total": 4,
        "succeeded": 2,
        "partial": 1,
        "failed": 1,
        "success_rate": 0.5,
    }
    assert body["summary"]["model_calls"]["total"] == 4
    assert body["summary"]["model_calls"]["succeeded"] == 2
    assert body["summary"]["model_calls"]["failed"] == 2
    assert body["summary"]["model_calls"]["failure_rate"] == 0.5
    assert body["summary"]["model_calls"]["input_tokens"] == 400
    assert body["summary"]["model_calls"]["output_tokens"] == 200
    assert body["summary"]["model_calls"]["token_calls"] == 3
    assert body["summary"]["model_calls"]["calls_without_tokens"] == 1
    assert body["summary"]["model_calls"]["costs"] == [
        {"currency": "USD", "amount": "0.000300", "calls": 2}
    ]
    assert body["cost"]["status"] == "partial"
    assert body["summary"]["model_calls"]["estimated_calls"] == 2
    assert body["summary"]["model_calls"]["unavailable_calls"] == 2
    assert body["summary"]["evaluations"]["total"] == 3
    assert body["summary"]["evaluations"]["completed"] == 2
    assert body["summary"]["evaluations"]["failed"] == 1
    assert body["summary"]["evaluations"]["avg_score"] == 0.7
    assert body["summary"]["evaluations"]["scored_metrics"] == 2
    assert body["summary"]["security"]["scans"] == 1
    assert body["summary"]["security"]["findings"] == 1
    assert body["summary"]["security"]["severity_counts"]["high"] == 1
    assert body["usage"]["models"]
    assert {row["model_id"] for row in body["usage"]["models"]} == {
        "alpha",
        "beta",
        "security-model",
    }
    assert len(body["trend"]) == 7
    assert body["trend"][-2]["calls"] >= 4
    assert body["data_quality"]["model_calls_without_tokens"] >= 1
    assert "not as zero" in body["limitations"][0]
    assert "provider and model filters do not apply" in body["scope_notes"][0].lower()

    by_provider = analytics(
        owner_client,
        project,
        provider=str(provider.id),
        **{"from": start.isoformat(), "to": today.isoformat()},
    ).json()
    # The security fixture creates an execution for the same provider too.
    assert by_provider["summary"]["executions"]["total"] == 3
    assert by_provider["summary"]["model_calls"]["total"] == 3
    assert by_provider["summary"]["model_calls"]["succeeded"] == 2
    assert by_provider["summary"]["model_calls"]["input_tokens"] == 200
    assert by_provider["summary"]["evaluations"]["total"] == 2
    assert by_provider["filters"]["provider_name"] == "Analytics Ollama"
    assert by_provider["summary"]["security"]["scans"] == 1

    by_model = analytics(
        owner_client,
        project,
        model="beta",
        **{"from": start.isoformat(), "to": today.isoformat()},
    ).json()
    assert by_model["summary"]["executions"]["total"] == 1
    assert by_model["summary"]["model_calls"]["total"] == 1
    assert by_model["summary"]["evaluations"]["total"] == 1
    assert by_model["usage"]["models"][0]["model_id"] == "beta"

    evaluation_only = analytics(
        owner_client,
        project,
        source="evaluation",
        **{"from": start.isoformat(), "to": today.isoformat()},
    ).json()
    assert evaluation_only["summary"]["executions"]["total"] == 0
    assert evaluation_only["summary"]["model_calls"]["total"] == 0
    assert evaluation_only["summary"]["evaluations"]["total"] == 3

    playground_only = analytics(
        owner_client,
        project,
        source="playground",
        **{"from": start.isoformat(), "to": today.isoformat()},
    ).json()
    assert playground_only["summary"]["executions"]["total"] == 4
    assert playground_only["summary"]["evaluations"]["total"] == 0

    maybe_empty = analytics(
        owner_client,
        project,
        **{"from": "2100-01-01", "to": "2100-01-02"},
    ).json()
    assert maybe_empty["summary"]["model_calls"]["total"] == 0
    assert maybe_empty["summary"]["model_calls"]["avg_latency_ms"] is None
    assert maybe_empty["summary"]["model_calls"]["input_tokens"] is None
    assert maybe_empty["cost"]["status"] == "unavailable"
    assert maybe_empty["trend"][0]["calls"] == 0

    assert analytics(viewer_client, project).status_code == 200
    outsider = APIClient()
    outsider.force_authenticate(user=third_user)
    assert analytics(outsider, project).status_code == 404
    assert analytics(APIClient(), project).status_code == 401
    assert analytics(owner_client, project, source="unknown").status_code == 400
    assert analytics(owner_client, project, provider="not-a-uuid").status_code == 400
    assert analytics(
        owner_client,
        project,
        **{"from": "2026-02-01", "to": "2026-01-01"},
    ).status_code == 400


def test_model_performance_uses_rollups_then_live_history_and_scores(
    owner_client, project, provider, second_provider
):
    today = timezone.localdate()
    old_day = today - timedelta(days=10)
    old_at = timezone.make_aware(
        datetime.combine(old_day, time.min)
    ) + timedelta(hours=12)
    new_at = timezone.now() - timedelta(days=1)
    make_execution(
        project=project,
        provider=provider,
        model_id="alpha",
        execution_status=Execution.Status.SUCCEEDED,
        when=old_at,
        latency_ms=500,
        input_tokens=1000,
        output_tokens=500,
        cost=Decimal("0.500000"),
        currency="USD",
    )
    make_execution(
        project=project,
        provider=provider,
        model_id="alpha",
        execution_status=Execution.Status.SUCCEEDED,
        when=new_at,
        latency_ms=100,
        input_tokens=10,
        output_tokens=5,
        cost=Decimal("0.010000"),
        currency="USD",
    )
    make_execution(
        project=project,
        provider=second_provider,
        model_id="beta",
        execution_status=Execution.Status.FAILED,
        when=new_at,
        latency_ms=300,
        input_tokens=None,
        output_tokens=None,
    )
    make_evaluation(
        project=project,
        provider=provider,
        model_id="alpha",
        when=new_at,
        score=0.9,
    )
    make_evaluation(
        project=project,
        provider=second_provider,
        model_id="beta",
        when=new_at,
        score=0.4,
    )

    TraceRollup.objects.create(
        project=project,
        day=old_day,
        source=Trace.Source.PLAYGROUND,
        role=Trace.Role.MODEL,
        status=Trace.Status.SUCCEEDED,
        provider_id=str(provider.id),
        provider_name=provider.name,
        provider_kind=provider.kind,
        model_id="alpha",
        cost_currency="USD",
        calls=1,
        input_tokens=1000,
        output_tokens=500,
        token_calls=1,
        latency_total_ms=500,
        latency_count=1,
        duration_total_ms=505,
        duration_count=1,
        estimated_cost=Decimal("0.500000"),
        estimated_calls=1,
        unavailable_calls=0,
        first_seen=old_at,
        last_seen=old_at,
    )
    TraceRollupState.objects.create(project=project, through_day=old_day)

    response = owner_client.get(
        models_url(project),
        {"from": old_day.isoformat(), "to": today.isoformat()},
    )
    assert response.status_code == 200, response.content
    body = response.json()
    alpha = next(row for row in body["models"] if row["model_id"] == "alpha")
    beta = next(row for row in body["models"] if row["model_id"] == "beta")
    # The rollup day and the newer raw day are both included, but the older
    # raw trace is excluded so the same call is not counted twice.
    assert alpha["calls"] == 2
    assert alpha["succeeded"] == 2
    assert alpha["failed"] == 0
    assert alpha["avg_latency_ms"] == 300.0
    assert alpha["input_tokens"] == 1010
    assert alpha["output_tokens"] == 505
    assert alpha["costs"] == [
        {"currency": "USD", "amount": "0.510000", "calls": 2}
    ]
    assert alpha["evaluation"]["avg_score"] == 0.9
    assert alpha["evaluation"]["runs"] == 1
    assert len(alpha["trend"]) == 11
    old_point = next(
        point for point in alpha["trend"] if point["day"] == old_day.isoformat()
    )
    assert old_point["calls"] == 1
    assert old_point["input_tokens"] == 1000
    assert beta["calls"] == 1
    assert beta["failed"] == 1
    assert beta["input_tokens"] is None
    assert beta["cost_status"] == "unavailable"
    assert beta["evaluation"]["avg_score"] == 0.4
    beta_day = timezone.localtime(new_at).date().isoformat()
    beta_point = next(point for point in beta["trend"] if point["day"] == beta_day)
    assert beta_point["avg_evaluation_score"] == 0.4
    assert "live traces" in body["comparison_note"]
    assert "not as zero" in body["warnings"][0]


def test_reports_are_snapshots_and_export_csv_and_pdf(
    owner_client, viewer_client, third_user, project, provider
):
    today = timezone.localdate()
    start = today - timedelta(days=4)
    when = timezone.now() - timedelta(days=1)
    make_execution(
        project=project,
        provider=provider,
        model_id="alpha",
        execution_status=Execution.Status.SUCCEEDED,
        when=when,
        latency_ms=150,
        input_tokens=120,
        output_tokens=60,
        cost=Decimal("0.000120"),
        currency="USD",
    )
    make_evaluation(
        project=project,
        provider=provider,
        model_id="alpha",
        when=when,
        score=0.75,
    )
    make_security(project, provider, when)

    response = owner_client.post(
        reports_url(project),
        {
            "title": "Analytics test report",
            "from": start.isoformat(),
            "to": today.isoformat(),
            "provider": str(provider.id),
            "sections": [
                "overview",
                "usage",
                "performance",
                "evaluations",
                "costs",
                "security",
                "trends",
            ],
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    report_body = response.json()
    report_id = report_body["id"]
    assert report_body["title"] == "Analytics test report"
    assert report_body["period_from"] == start.isoformat()
    assert report_body["period_to"] == today.isoformat()
    assert report_body["filters"]["provider_name"] == "Analytics Ollama"
    assert report_body["section_labels"] == [
        "Overview",
        "Model usage",
        "Model performance",
        "Evaluation outcomes",
        "Costs",
        "Security",
        "Daily trends",
    ]
    assert report_body["document"]["metadata"]
    assert any(
        row[0] == "Reporting period"
        for row in report_body["document"]["metadata"]
    )
    performance_section = next(
        section
        for section in report_body["document"]["sections"]
        if section["key"] == "performance"
    )
    assert performance_section["rows"]
    assert not performance_section["rows"][0][0] == "Models"
    report = AnalyticsReport.objects.get(pk=report_id)
    assert report.created_by.email == "owner@example.com"
    assert report.scope["project_name"] == "Analytics project"
    # One execution is the report fixture and one is created by make_security.
    assert report.snapshot["dashboard"]["summary"]["executions"]["total"] == 2
    assert report.snapshot["filters"]["provider_name"] == "Analytics Ollama"

    listing = owner_client.get(reports_url(project))
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == report_id
    assert "document" not in listing.json()[0]
    assert viewer_client.get(reports_url(project)).status_code == 200
    detail = viewer_client.get(f"/api/v1/analytics-reports/{report_id}/")
    assert detail.status_code == 200
    assert detail.json()["document"]["sections"]
    assert detail.json()["document"]["metadata"]

    csv_export = owner_client.get(
        f"/api/v1/analytics-reports/{report_id}/export/", {"export_format": "csv"}
    )
    assert csv_export.status_code == 200
    assert csv_export["Content-Type"].startswith("text/csv")
    assert "attachment" in csv_export["Content-Disposition"]
    csv_text = csv_export.content.decode("utf-8")
    assert "Analytics test report" in csv_text
    assert "Reporting period" in csv_text
    assert "Playground executions,2" in csv_text
    assert "Costs" in csv_text
    assert "Security" in csv_text
    assert "Evaluation outcomes" in csv_text
    assert "Daily trends" in csv_text
    assert "Model performance" in csv_text
    assert "No model performance history" not in csv_text

    pdf_export = owner_client.get(
        f"/api/v1/analytics-reports/{report_id}/export/", {"export_format": "pdf"}
    )
    assert pdf_export.status_code == 200
    assert pdf_export["Content-Type"] == "application/pdf"
    assert pdf_export.content.startswith(b"%PDF-1.4")
    assert b"Analytics test report" in pdf_export.content
    assert b"Reporting period" in pdf_export.content
    assert b"Playground executions" in pdf_export.content

    # An export uses the stored snapshot; a later execution must not change it.
    make_execution(
        project=project,
        provider=provider,
        model_id="late-model",
        execution_status=Execution.Status.SUCCEEDED,
        when=timezone.now(),
    )
    csv_again = owner_client.get(
        f"/api/v1/analytics-reports/{report_id}/export/", {"export_format": "csv"}
    ).content.decode("utf-8")
    assert "Playground executions,2" in csv_again
    report.refresh_from_db()
    assert report.snapshot["dashboard"]["summary"]["executions"]["total"] == 2

    assert owner_client.get(
        f"/api/v1/analytics-reports/{report_id}/export/", {"export_format": "xlsx"}
    ).status_code == 400
    outsider = APIClient()
    outsider.force_authenticate(user=third_user)
    assert outsider.get(f"/api/v1/analytics-reports/{report_id}/").status_code == 404
    assert outsider.get(reports_url(project)).status_code == 404
    assert APIClient().get(reports_url(project)).status_code == 401
    assert APIClient().get(
        f"/api/v1/analytics-reports/{report_id}/export/", {"export_format": "csv"}
    ).status_code == 401

    invalid_sections = owner_client.post(
        reports_url(project),
        {"sections": []},
        format="json",
    )
    assert invalid_sections.status_code == 400
    invalid_dates = owner_client.post(
        reports_url(project),
        {"from": "2026-02-01", "to": "2026-01-01"},
        format="json",
    )
    assert invalid_dates.status_code == 400


def test_report_defaults_missing_costs_to_unavailable_not_zero(
    owner_client, project, provider
):
    when = timezone.now() - timedelta(days=1)
    make_execution(
        project=project,
        provider=provider,
        model_id="unpriced",
        execution_status=Execution.Status.SUCCEEDED,
        when=when,
        input_tokens=None,
        output_tokens=None,
        cost=None,
    )
    response = owner_client.post(
        reports_url(project),
        {"title": "Unpriced report", "sections": ["overview", "costs"]},
        format="json",
    )
    assert response.status_code == 201, response.content
    report_id = response.json()["id"]
    assert AnalyticsReport.objects.filter(pk=report_id).exists()
    metadata = dict(response.json()["document"]["metadata"])
    assert metadata["Provider filter"] == "All providers"
    assert metadata["Model filter"] == "All models"
    detail_response = owner_client.get(f"/api/v1/analytics-reports/{report_id}/")
    assert detail_response.status_code == 200, detail_response.content
    csv_text = owner_client.get(
        f"/api/v1/analytics-reports/{report_id}/export/", {"export_format": "csv"}
    ).content.decode("utf-8")
    assert "Cost status,unavailable" in csv_text
    assert "Estimated costs,Unavailable" in csv_text
    assert "0.000000" not in csv_text
