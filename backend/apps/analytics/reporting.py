"""Report snapshots and export documents built from stored analytics data."""

from __future__ import annotations

import csv
import io

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.projects.services import project_for_user
from apps.workspaces.models import Membership
from apps.workspaces.permissions import require_membership
from integrations.reporting.pdf import render_pdf

from .models import AnalyticsReport
from .services import dashboard, model_performance

REPORT_SECTIONS = {
    "overview": "Overview",
    "usage": "Model usage",
    "performance": "Model performance",
    "evaluations": "Evaluation outcomes",
    "costs": "Costs",
    "security": "Security",
    "trends": "Daily trends",
}
DEFAULT_SECTIONS = list(REPORT_SECTIONS)
REPORT_SECTION_KEYS = tuple(REPORT_SECTIONS)


def _value(value, unavailable: str = "Unavailable") -> str:
    if value is None or value == "":
        return unavailable
    return str(value)


def _number(value, suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, float):
        return f"{value:,.2f}{suffix}"
    return f"{value:,}{suffix}"


def _percent(value) -> str:
    if value is None:
        return "Unavailable"
    return f"{round(float(value) * 100, 2)}%"


def _costs(costs) -> str:
    if not costs:
        return "Unavailable"
    return " · ".join(
        f"{cost.get('amount')} {cost.get('currency')}"
        for cost in costs
        if cost.get("amount") is not None
    ) or "Unavailable"


def _model_label(row) -> str:
    return f"{row.get('provider_name') or 'Unknown provider'} · {row.get('model_id') or 'Unknown model'}"


def _metadata(report: AnalyticsReport) -> list[tuple[str, str]]:
    snapshot = report.snapshot if isinstance(report.snapshot, dict) else {}
    scope = snapshot.get("scope") or report.scope or {}
    period = snapshot.get("period") or {
        "from": report.period_from.isoformat(),
        "to": report.period_to.isoformat(),
    }
    filters = snapshot.get("filters") or report.filters or {}
    sections = [
        REPORT_SECTIONS.get(key, key)
        for key in (report.sections or snapshot.get("sections") or [])
    ]
    return [
        ("Report", report.title),
        ("Project", _value(scope.get("project_name"))),
        ("Workspace", _value(scope.get("workspace_name"))),
        (
            "Reporting period",
            f"{period.get('from', report.period_from)} to "
            f"{period.get('to', report.period_to)}"
            f" ({period.get('days', '')} days)",
        ),
        ("Timezone", _value(period.get("timezone"), "UTC")),
        ("Generated at", report.created_at.isoformat()),
        ("Data captured at", _value(snapshot.get("data_as_of"))),
        ("Provider filter", _value(filters.get("provider_name"), "All providers")),
        ("Model filter", _value(filters.get("model"), "All models")),
        ("Source filter", _value(filters.get("source"), "All sources")),
        ("Scope", "Project analytics; figures are stored in this report snapshot"),
        ("Sections", ", ".join(sections) if sections else "None"),
        (
            "Reproducibility",
            "Exports use the stored snapshot and do not silently refresh with newer data.",
        ),
    ]


def _overview_rows(data: dict) -> list[tuple[str, str]]:
    summary = data.get("summary") or {}
    executions = summary.get("executions") or {}
    calls = summary.get("model_calls") or {}
    evaluations = summary.get("evaluations") or {}
    security = summary.get("security") or {}
    cost = data.get("cost") or {}
    rows = [
        ("Playground executions", _number(executions.get("total"))),
        ("Succeeded executions", _number(executions.get("succeeded"))),
        ("Partial executions", _number(executions.get("partial"))),
        ("Failed executions", _number(executions.get("failed"))),
        ("Execution success rate", _percent(executions.get("success_rate"))),
        ("Model calls", _number(calls.get("total"))),
        ("Succeeded model calls", _number(calls.get("succeeded"))),
        ("Failed model calls", _number(calls.get("failed"))),
        ("Model-call failure rate", _percent(calls.get("failure_rate"))),
        ("Average provider response time", _number(calls.get("avg_latency_ms"), " ms")),
        ("Input tokens", _number(calls.get("input_tokens"))),
        ("Output tokens", _number(calls.get("output_tokens"))),
        ("Calls reporting token usage", _number(calls.get("token_calls"))),
        ("Calls without token usage", _number(calls.get("calls_without_tokens"))),
        ("Estimated cost status", _value(cost.get("status"))),
        ("Estimated costs", _costs(cost.get("currencies"))),
        ("Evaluation runs", _number(evaluations.get("total"))),
        ("Completed evaluations", _number(evaluations.get("completed"))),
        ("Failed evaluations", _number(evaluations.get("failed"))),
        ("Evaluation mean score", _number(evaluations.get("avg_score"))),
        ("Security scans", _number(security.get("scans"))),
        ("Security findings", _number(security.get("findings"))),
        ("Open security findings", _number(security.get("open_findings"))),
    ]
    return rows


def _usage_rows(data: dict) -> list[tuple[str, str]]:
    rows = []
    usage = data.get("usage") or {}
    models = usage.get("models") or []
    providers = usage.get("providers") or []
    if not models:
        rows.append(("Models", "No model calls in this period."))
    for model in models:
        rows.append(
            (
                f"Model · {_model_label(model)}",
                f"{_number(model.get('count'))} calls; "
                f"{_number(model.get('succeeded'))} succeeded; "
                f"{_number(model.get('failed'))} failed; "
                f"{_number(model.get('avg_latency_ms'), ' ms')} average latency; "
                f"{_number(model.get('input_tokens'))} input tokens; "
                f"{_number(model.get('output_tokens'))} output tokens; "
                f"{_costs(model.get('costs'))} estimated cost",
            )
        )
    if not providers:
        rows.append(("Providers", "No provider calls in this period."))
    for provider in providers:
        rows.append(
            (
                f"Provider · {provider.get('provider_name') or 'Unknown'} "
                f"({provider.get('provider_kind') or 'unknown'})",
                f"{_number(provider.get('count'))} calls; "
                f"{_number(provider.get('failed'))} failed; "
                f"{_number(provider.get('input_tokens'))} input tokens; "
                f"{_number(provider.get('output_tokens'))} output tokens; "
                f"{_costs(provider.get('costs'))} estimated cost",
            )
        )
    return rows


def _performance_rows(data: dict) -> list[tuple[str, str]]:
    models = data.get("model_performance") or []
    if not models:
        return [("Models", "No model performance history in this period.")]
    rows = []
    for model in models:
        evaluation = model.get("evaluation") or {}
        rows.append(
            (
                f"Performance · {_model_label(model)}",
                f"{_number(model.get('calls'))} calls; "
                f"{_percent(model.get('failure_rate'))} failure rate; "
                f"{_number(model.get('avg_latency_ms'), ' ms')} average latency; "
                f"{_number(model.get('input_tokens'))} input tokens; "
                f"{_number(model.get('output_tokens'))} output tokens; "
                f"evaluation score {_number(evaluation.get('avg_score'))} "
                f"across {_number(evaluation.get('runs'))} runs",
            )
        )
        for point in model.get("trend") or []:
            if not point.get("calls") and point.get("avg_evaluation_score") is None:
                continue
            rows.append(
                (
                    f"{_model_label(model)} · {point.get('day')}",
                    f"{_number(point.get('calls'))} calls; "
                    f"{_number(point.get('failed'))} failed; "
                    f"{_number(point.get('avg_latency_ms'), ' ms')} average latency; "
                    f"{_number(point.get('input_tokens'))} input tokens; "
                    f"{_number(point.get('output_tokens'))} output tokens; "
                    f"evaluation score {_number(point.get('avg_evaluation_score'))}",
                )
            )
    return rows


def _evaluation_rows(data: dict) -> list[tuple[str, str]]:
    history = data.get("evaluation_history") or []
    if not history:
        return [("Evaluations", "No evaluation runs in this period.")]
    rows = []
    for run in history:
        models = ", ".join(
            f"{model.get('provider_name')}:{model.get('model_id')} "
            f"({_number(model.get('avg_score'))})"
            for model in run.get("models") or []
        )
        rows.append(
            (
                f"Evaluation · {run.get('dataset_name')} v{run.get('dataset_version')}",
                f"{run.get('status')}; created {run.get('created_at')}; "
                f"score {_number(run.get('avg_score'))}; "
                f"{_number(run.get('failed_cases'))} failed cases; models: "
                f"{models or 'none reported'}",
            )
        )
    return rows


def _cost_rows(data: dict) -> list[tuple[str, str]]:
    cost = data.get("cost") or {}
    rows = [
        ("Cost status", _value(cost.get("status"))),
        ("Cost detail", _value(cost.get("detail"))),
        ("Cost policy", _value(cost.get("note"))),
        ("Calls with estimated cost", _number(cost.get("estimated_calls"))),
        ("Calls without cost estimate", _number(cost.get("unavailable_calls"))),
    ]
    for item in cost.get("currencies") or []:
        rows.append(
            (
                f"Estimated total · {item.get('currency')}",
                f"{item.get('amount')} across {_number(item.get('calls'))} calls",
            )
        )
    if not cost.get("currencies"):
        rows.append(("Estimated total", "Unavailable"))
    for model in cost.get("by_model") or []:
        rows.append(
            (
                f"Model cost · {model.get('provider_name')}:{model.get('model_id')}",
                f"{_costs(model.get('costs'))} · {model.get('cost_status')} · "
                f"{_number(model.get('estimated_calls'))} estimated calls",
            )
        )
    for provider in cost.get("by_provider") or []:
        rows.append(
            (
                f"Provider cost · {provider.get('provider_name')}",
                f"{_costs(provider.get('costs'))} · {provider.get('cost_status')} · "
                f"{_number(provider.get('estimated_calls'))} estimated calls",
            )
        )
    return rows


def _security_rows(data: dict) -> list[tuple[str, str]]:
    security = data.get("summary", {}).get("security") or {}
    rows = [
        ("Security scans", _number(security.get("scans"))),
        ("Completed scans", _number(security.get("completed_scans"))),
        ("Failed scans", _number(security.get("failed_scans"))),
        ("Running scans", _number(security.get("running_scans"))),
        ("Findings", _number(security.get("findings"))),
        ("Open findings", _number(security.get("open_findings"))),
        ("Reviewed findings", _number(security.get("reviewed_findings"))),
        ("Resolved findings", _number(security.get("resolved_findings"))),
        ("AI security test runs", _number(security.get("test_runs"))),
        ("Completed AI test runs", _number(security.get("completed_test_runs"))),
        ("AI security tests performed", _number(security.get("tests_performed"))),
        ("AI tests passed", _number(security.get("tests_passed"))),
        ("AI tests failed", _number(security.get("tests_failed"))),
        ("AI tests inconclusive", _number(security.get("tests_inconclusive"))),
        (
            "Severity counts",
            ", ".join(
                f"{key}: {value}"
                for key, value in (security.get("severity_counts") or {}).items()
            )
            or "None",
        ),
        (
            "AI test severity counts",
            ", ".join(
                f"{key}: {value}"
                for key, value in (security.get("test_severity_counts") or {}).items()
            )
            or "None",
        ),
        (
            "AI test attack categories",
            ", ".join(
                f"{item.get('category')}: {item.get('count')}"
                for item in security.get("test_categories") or []
            )
            or "None",
        ),
        (
            "Categories",
            ", ".join(
                f"{item.get('category')}: {item.get('count')}"
                for item in security.get("categories") or []
            )
            or "None",
        ),
        ("Security interpretation", _value(security.get("note"))),
    ]
    for scan in security.get("recent_scans") or []:
        rows.append(
            (
                f"Recent scan · {scan.get('target_label')}",
                f"{scan.get('status')}; {scan.get('target_type')}; "
                f"{_number(scan.get('finding_count'))} findings; "
                f"{scan.get('highest_severity') or 'no severity'}; "
                f"created {scan.get('created_at')}",
            )
        )
    return rows


def _trend_rows(data: dict) -> list[tuple[str, str]]:
    trend = data.get("trend") or []
    if not trend:
        return [("Daily trends", "No daily analytics in this period.")]
    return [
        (
            f"Day · {point.get('day')}",
            f"{_number(point.get('calls'))} model calls; "
            f"{_number(point.get('failed'))} failed; "
            f"{_number(point.get('avg_latency_ms'), ' ms')} average latency; "
            f"{_number(point.get('input_tokens'))} input tokens; "
            f"{_number(point.get('output_tokens'))} output tokens; "
            f"{_number(point.get('executions'))} executions; "
            f"{_number(point.get('evaluations'))} evaluations; "
            f"{_number(point.get('security_findings'))} security findings; "
            f"{_number(point.get('security_tests'))} AI security tests; "
            f"{_number(point.get('security_test_failures'))} AI test failures",
        )
        for point in trend
    ]


def build_report_document(report: AnalyticsReport) -> dict:
    snapshot = report.snapshot if isinstance(report.snapshot, dict) else {}
    dashboard = snapshot.get("dashboard") or {}
    data = {
        **dashboard,
        "model_performance": snapshot.get("model_performance")
        or dashboard.get("model_performance")
        or [],
    }
    sections = []
    builders = {
        "overview": _overview_rows,
        "usage": _usage_rows,
        "performance": _performance_rows,
        "evaluations": _evaluation_rows,
        "costs": _cost_rows,
        "security": _security_rows,
        "trends": _trend_rows,
    }
    for key in report.sections or snapshot.get("sections") or []:
        builder = builders.get(key)
        if builder is not None:
            sections.append(
                {
                    "key": key,
                    "title": REPORT_SECTIONS.get(key, key),
                    "rows": builder(data),
                }
            )
    return {
        "title": report.title,
        "metadata": _metadata(report),
        "sections": sections,
        "notes": snapshot.get("limitations") or data.get("limitations") or [],
    }


def _csv_safe(value: str) -> str:
    text = str(value or "")
    if text[:1] in {"=", "+", "-", "@"}:
        return f"'{text}"
    return text


def report_csv(report: AnalyticsReport) -> bytes:
    document = build_report_document(report)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["section", "item", "value"])
    for label, value in document["metadata"]:
        writer.writerow(["Report metadata", _csv_safe(label), _csv_safe(value)])
    for section in document["sections"]:
        for label, value in section["rows"]:
            writer.writerow(
                [section["title"], _csv_safe(label), _csv_safe(value)]
            )
    if document["notes"]:
        for note in document["notes"]:
            writer.writerow(["Limitations", "Note", _csv_safe(note)])
    return buffer.getvalue().encode("utf-8")


def report_pdf(report: AnalyticsReport) -> bytes:
    return render_pdf(build_report_document(report))


def _sections(value) -> list[str]:
    if not value:
        return list(DEFAULT_SECTIONS)
    cleaned = []
    for key in value:
        if key in REPORT_SECTIONS and key not in cleaned:
            cleaned.append(key)
    return cleaned


@transaction.atomic
def create_report(*, actor, project_id, validated_data) -> AnalyticsReport:
    project = project_for_user(actor, project_id, Membership.Role.VIEWER)
    params = {
        "from": validated_data.get("from"),
        "to": validated_data.get("to"),
        "provider": validated_data.get("provider"),
        "model": validated_data.get("model"),
        "source": validated_data.get("source"),
    }
    params = {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in params.items()
        if value not in (None, "")
    }
    data = dashboard(user=actor, project_id=project.pk, params=params)
    performance = model_performance(
        user=actor, project_id=project.pk, params=params
    )
    sections = _sections(validated_data.get("sections"))
    period = data["range"]
    filters = data["filters"]
    title = (validated_data.get("title") or "").strip()
    if not title:
        title = (
            f"Analytics report — {project.name} — "
            f"{period['from']} to {period['to']}"
        )
    snapshot = {
        "schema_version": 1,
        "scope": {
            "project": str(project.pk),
            "project_name": project.name,
            "workspace": str(project.workspace_id),
            "workspace_name": project.workspace.name,
        },
        "period": period,
        "filters": filters,
        "sections": sections,
        "generated_at": timezone.now().isoformat(),
        "data_as_of": data["generated_at"],
        "dashboard": data,
        "model_performance": performance["models"],
        "limitations": data["limitations"],
    }
    return AnalyticsReport.objects.create(
        project=project,
        title=title[:200],
        sections=sections,
        period_from=data["range"]["from"],
        period_to=data["range"]["to"],
        filters=filters,
        scope=snapshot["scope"],
        snapshot=snapshot,
        created_by=actor,
    )


def list_reports(*, user, project_id) -> list[AnalyticsReport]:
    project = project_for_user(user, project_id, Membership.Role.VIEWER)
    return list(
        AnalyticsReport.objects.filter(project=project)
        .select_related("created_by")
        .order_by("-created_at")[:100]
    )


def report_for_user(user, report_id) -> AnalyticsReport:
    report = (
        AnalyticsReport.objects.select_related(
            "project", "project__workspace", "created_by"
        )
        .filter(pk=report_id)
        .first()
    )
    if report is None:
        raise NotFound("Analytics report not found.")
    require_membership(user, report.project.workspace_id, Membership.Role.VIEWER)
    return report
