"""Analytics and reporting services for Milestone 8.

The service reads the platform's existing records instead of maintaining a
second analytics database:

* ``playground.Execution`` supplies playground execution counts and outcomes;
* ``observability.Trace`` / ``TraceRollup`` supply model calls, tokens,
  latency, errors and cost estimates;
* ``evaluations.Evaluation`` / ``EvaluationModel`` supply evaluation history
  and stored metric averages;
* ``security.SecurityScan`` / ``SecurityFinding`` supply security activity.

Trace aggregation follows the same completed-day rollup / recent-raw-trace
split as the observability dashboard.  Missing token or pricing information is
returned as missing, never as a made-up number or a zero cost.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal
import uuid

from django.db.models import Count, Q, Subquery, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import ValidationError

from apps.evaluations.models import Evaluation
from apps.observability.models import Trace, TraceRollup
from apps.observability.services import (
    TraceFilters,
    _window,
    dashboard as observability_dashboard,
)
from apps.playground.models import Execution
from apps.projects.services import project_for_user
from apps.providers.models import ProviderConfig
from apps.security.models import (
    SecurityFinding,
    SecurityScan,
    SecuritySeverity,
    SecurityTestResult,
    SecurityTestRun,
)
from apps.workspaces.models import Membership

DEFAULT_WINDOW_DAYS = 30
SOURCES = {"playground", "evaluation"}
SECURITY_NOTE = (
    "Security counts cover every scan and AI security test detected in the "
    "reporting period; provider and model filters do not apply to dataset or "
    "prompt scans. AI test results are model-specific and are counted for the "
    "selected period."
)
EVALUATION_SCORE_NOTE = (
    "The evaluation score is the mean of available stored metric averages. "
    "It can combine different metrics and only covers completed evaluation runs."
)
COST_NOTE = (
    "Costs are estimates only when explicit token pricing is configured and the "
    "provider reported both token counts. Unpriced calls are reported as "
    "unavailable, not as zero."
)


def _money(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return format(value.quantize(Decimal("0.000001")), "f")


def _day_start(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, dt_time.min))


def _next_day_start(day: date) -> datetime:
    return _day_start(day + timedelta(days=1))


def _parse_day(value, field: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = parse_date(text)
    if parsed is None:
        parsed_at = parse_datetime(text)
        if parsed_at is not None:
            if timezone.is_aware(parsed_at):
                parsed_at = timezone.localtime(parsed_at)
            parsed = parsed_at.date()
    if parsed is None:
        raise ValidationError({field: "Use an ISO date (YYYY-MM-DD)."})
    return parsed


@dataclass(frozen=True)
class AnalyticsFilters:
    start: date
    end: date
    defaulted: bool
    provider_id: uuid.UUID | None = None
    model_id: str = ""
    source: str = ""

    @property
    def start_at(self) -> datetime:
        return _day_start(self.start)

    @property
    def end_before(self) -> datetime:
        return _next_day_start(self.end)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @classmethod
    def from_params(cls, params, *, today: date | None = None) -> "AnalyticsFilters":
        start = _parse_day(params.get("from"), "from")
        end = _parse_day(params.get("to"), "to")
        defaulted = start is None and end is None
        current = today or timezone.localdate()
        if start is None and end is None:
            end = current
            start = end - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
        elif start is None:
            start = end - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
        elif end is None:
            end = current
        if start > end:
            raise ValidationError({"to": "The end date must be on or after the start date."})

        provider_id = None
        raw_provider = str(params.get("provider") or "").strip()
        if raw_provider:
            try:
                provider_id = uuid.UUID(raw_provider)
            except (TypeError, ValueError):
                raise ValidationError({"provider": "Provider must be a UUID."}) from None

        source = str(params.get("source") or "").strip()
        if source and source not in SOURCES:
            raise ValidationError({"source": "Unknown analytics source."})

        return cls(
            start=start,
            end=end,
            defaulted=defaulted,
            provider_id=provider_id,
            model_id=str(params.get("model") or "").strip()[:200],
            source=source,
        )


def _parameters(filters: AnalyticsFilters) -> dict:
    params = {
        "from": filters.start.isoformat(),
        "to": filters.end.isoformat(),
        "role": "model",
    }
    if filters.provider_id:
        params["provider"] = str(filters.provider_id)
    if filters.model_id:
        params["model"] = filters.model_id
    if filters.source:
        params["source"] = filters.source
    return params


def _context(*, user, project_id, params):
    project = project_for_user(user, project_id, Membership.Role.VIEWER)
    filters = AnalyticsFilters.from_params(params)
    provider_name = ""
    if filters.provider_id:
        provider = ProviderConfig.objects.filter(
            pk=filters.provider_id, project=project
        ).first()
        if provider is None:
            raise ValidationError({"provider": "Provider not found in this project."})
        provider_name = provider.name
    return project, filters, provider_name


def _filter_meta(filters: AnalyticsFilters, provider_name: str) -> dict:
    return {
        "from": filters.start.isoformat(),
        "to": filters.end.isoformat(),
        "provider": str(filters.provider_id) if filters.provider_id else None,
        "provider_name": provider_name,
        "model": filters.model_id or None,
        "source": filters.source or None,
    }


def _range_meta(filters: AnalyticsFilters) -> dict:
    return {
        "from": filters.start.isoformat(),
        "to": filters.end.isoformat(),
        "days": filters.days,
        "defaulted": filters.defaulted,
        "timezone": "UTC",
    }


def _key(provider_id, provider_kind, provider_name, model_id) -> str:
    return "::".join(
        [
            str(provider_id) if provider_id else "none",
            str(provider_kind or ""),
            str(provider_name or ""),
            str(model_id or ""),
        ]
    )


def _cost_list(costs: dict) -> list[dict]:
    return [
        {
            "currency": currency or "Unspecified",
            "amount": _money(item["amount"]),
            "calls": int(item["calls"] or 0),
        }
        for currency, item in sorted((costs or {}).items())
    ]


def _merge_costs(target: dict, source: dict) -> None:
    for currency, item in (source or {}).items():
        bucket = target.setdefault(currency, {"amount": Decimal("0"), "calls": 0})
        bucket["amount"] += item["amount"]
        bucket["calls"] += int(item["calls"] or 0)


def _execution_data(project, filters: AnalyticsFilters) -> dict:
    base = Execution.objects.filter(
        project=project,
        created_at__gte=filters.start_at,
        created_at__lt=filters.end_before,
    )
    if filters.source == "evaluation":
        base = base.none()
    if filters.provider_id:
        base = base.filter(results__provider_id=filters.provider_id)
    if filters.model_id:
        base = base.filter(results__model_id=filters.model_id)
    execution_ids = base.order_by().values("id").distinct()
    scoped = Execution.objects.filter(id__in=Subquery(execution_ids))

    status_counts = {
        row["status"]: int(row["count"])
        for row in scoped.values("status").annotate(count=Count("id"))
    }
    total = sum(status_counts.values())
    succeeded = status_counts.get(Execution.Status.SUCCEEDED, 0)
    partial = status_counts.get(Execution.Status.PARTIAL, 0)
    failed = status_counts.get(Execution.Status.FAILED, 0)
    daily = {
        row["day"]: int(row["count"])
        for row in scoped.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    }
    daily_status = defaultdict(dict)
    for row in (
        scoped.annotate(day=TruncDate("created_at"))
        .values("day", "status")
        .annotate(count=Count("id"))
    ):
        daily_status[row["day"]][row["status"]] = int(row["count"])

    return {
        "total": total,
        "succeeded": succeeded,
        "partial": partial,
        "failed": failed,
        "success_rate": round(succeeded / total, 4) if total else 0,
        "daily": daily,
        "daily_status": dict(daily_status),
    }


def _matching_evaluation_models(evaluation, filters: AnalyticsFilters):
    rows = list(evaluation.models.all())
    if filters.provider_id:
        rows = [
            row
            for row in rows
            if str(row.provider_id) == str(filters.provider_id)
        ]
    if filters.model_id:
        rows = [row for row in rows if row.model_id == filters.model_id]
    return rows


def _model_metric_values(model_row) -> list[float]:
    summary = model_row.summary if isinstance(model_row.summary, dict) else {}
    averages = summary.get("metric_averages") or {}
    if not isinstance(averages, dict):
        return []
    return [
        float(value)
        for value in averages.values()
        if isinstance(value, (int, float))
    ]


def _model_metric_average(model_row) -> float | None:
    values = _model_metric_values(model_row)
    return round(sum(values) / len(values), 4) if values else None


def _evaluation_data(project, filters: AnalyticsFilters) -> dict:
    empty = {
        "total": 0,
        "completed": 0,
        "failed": 0,
        "running": 0,
        "avg_score": None,
        "scored_models": 0,
        "scored_metrics": 0,
        "history": [],
        "daily": {},
        "daily_status": {},
        "model_scores": {},
        "model_daily_scores": {},
    }
    if filters.source == "playground":
        return empty

    base = Evaluation.objects.filter(
        project=project,
        created_at__gte=filters.start_at,
        created_at__lt=filters.end_before,
    )
    if filters.provider_id:
        base = base.filter(models__provider_id=filters.provider_id)
    if filters.model_id:
        base = base.filter(models__model_id=filters.model_id)
    evaluations = list(
        base.distinct()
        .prefetch_related("models")
        .order_by("-created_at")
    )

    status_counts = defaultdict(int)
    score_values: list[float] = []
    model_scores: dict[str, dict] = {}
    model_daily_scores: dict[str, dict[date, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    daily = defaultdict(int)
    daily_status = defaultdict(lambda: defaultdict(int))
    daily_scores: dict[date, list[float]] = defaultdict(list)
    scored_evaluations = 0
    history = []

    for evaluation in evaluations:
        day = timezone.localtime(evaluation.created_at).date()
        daily[day] += 1
        daily_status[day][evaluation.status] += 1
        status_counts[evaluation.status] += 1
        models = _matching_evaluation_models(evaluation, filters)
        model_history = []
        evaluation_values = []
        for model_row in models:
            values = _model_metric_values(model_row)
            average = _model_metric_average(model_row)
            model_history.append(
                {
                    "id": str(model_row.pk),
                    "provider": str(model_row.provider_id)
                    if model_row.provider_id
                    else None,
                    "provider_name": model_row.provider_name,
                    "provider_kind": model_row.provider_kind,
                    "model_id": model_row.model_id,
                    "status": model_row.status,
                    "cases": model_row.summary.get("cases", 0)
                    if isinstance(model_row.summary, dict)
                    else 0,
                    "failed": model_row.summary.get("failed", 0)
                    if isinstance(model_row.summary, dict)
                    else 0,
                    "avg_score": average,
                    "scored_metrics": len(values),
                }
            )
            if evaluation.status != Evaluation.Status.COMPLETED:
                continue
            evaluation_values.extend(values)
            if not values:
                continue
            key = _key(
                model_row.provider_id,
                model_row.provider_kind,
                model_row.provider_name,
                model_row.model_id,
            )
            bucket = model_scores.setdefault(
                key,
                {
                    "provider": str(model_row.provider_id)
                    if model_row.provider_id
                    else None,
                    "provider_name": model_row.provider_name,
                    "provider_kind": model_row.provider_kind,
                    "model_id": model_row.model_id,
                    "score_total": 0.0,
                    "score_count": 0,
                    "run_ids": set(),
                },
            )
            bucket["score_total"] += sum(values)
            bucket["score_count"] += len(values)
            bucket["run_ids"].add(str(evaluation.pk))
            model_daily_scores[key][day].extend(values)

        evaluation_average = (
            round(sum(evaluation_values) / len(evaluation_values), 4)
            if evaluation_values
            else None
        )
        if evaluation.status == Evaluation.Status.COMPLETED and evaluation_values:
            score_values.extend(evaluation_values)
            daily_scores[day].extend(evaluation_values)
            scored_evaluations += 1
        history.append(
            {
                "id": str(evaluation.pk),
                "dataset_name": evaluation.dataset_name,
                "dataset_version": evaluation.dataset_version,
                "status": evaluation.status,
                "metrics": list(evaluation.metrics or []),
                "total_cases": evaluation.total_cases,
                "failed_cases": evaluation.failed_cases,
                "created_at": evaluation.created_at.isoformat(),
                "avg_score": evaluation_average,
                "scored_metrics": len(evaluation_values),
                "models": model_history,
            }
        )

    final_scores = {}
    for key, bucket in model_scores.items():
        count = bucket["score_count"]
        final_scores[key] = {
            **bucket,
            "avg_score": round(bucket["score_total"] / count, 4) if count else None,
            "scored_metrics": count,
            "runs": len(bucket["run_ids"]),
        }
        final_scores[key].pop("score_total", None)
        final_scores[key].pop("score_count", None)
        final_scores[key].pop("run_ids", None)

    completed = status_counts.get(Evaluation.Status.COMPLETED, 0)
    return {
        "total": len(evaluations),
        "completed": completed,
        "failed": status_counts.get(Evaluation.Status.FAILED, 0),
        "running": status_counts.get(Evaluation.Status.RUNNING, 0)
        + status_counts.get(Evaluation.Status.QUEUED, 0),
        "avg_score": round(sum(score_values) / len(score_values), 4)
        if score_values
        else None,
        "scored_models": len(final_scores),
        "scored_metrics": len(score_values),
        "history": history[:10],
        "daily": dict(daily),
        "daily_status": {
            day.isoformat(): dict(counts) for day, counts in daily_status.items()
        },
        "scored_evaluations": scored_evaluations,
        "model_scores": final_scores,
        "model_daily_scores": {
            key: {
                day: round(sum(values) / len(values), 4)
                for day, values in day_values.items()
                if values
            }
            for key, day_values in model_daily_scores.items()
        },
        "daily_scores": {
            day.isoformat(): round(sum(values) / len(values), 4)
            for day, values in daily_scores.items()
        },
    }


def _security_data(project, filters: AnalyticsFilters) -> dict:
    scans = SecurityScan.objects.filter(
        project=project,
        created_at__gte=filters.start_at,
        created_at__lt=filters.end_before,
    )
    findings = SecurityFinding.objects.filter(
        project=project,
        detected_at__gte=filters.start_at,
        detected_at__lt=filters.end_before,
    )
    test_runs = SecurityTestRun.objects.filter(
        project=project,
        created_at__gte=filters.start_at,
        created_at__lt=filters.end_before,
    )
    test_results = SecurityTestResult.objects.filter(
        run__project=project,
        run__created_at__gte=filters.start_at,
        run__created_at__lt=filters.end_before,
    ).exclude(status=SecurityTestResult.Status.PENDING)
    scan_status = {
        row["status"]: int(row["count"])
        for row in scans.values("status").annotate(count=Count("id"))
    }
    finding_status = {
        row["status"]: int(row["count"])
        for row in findings.values("status").annotate(count=Count("id"))
    }
    test_run_status = {
        row["status"]: int(row["count"])
        for row in test_runs.values("status").annotate(count=Count("id"))
    }
    test_verdicts = {
        row["verdict"]: int(row["count"])
        for row in test_results.values("verdict").annotate(count=Count("id"))
    }
    test_severity_counts = {value: 0 for value, _ in SecuritySeverity.choices}
    for row in test_results.filter(verdict=SecurityTestResult.Verdict.FAILED).values(
        "severity"
    ).annotate(count=Count("id")):
        if row["severity"]:
            test_severity_counts[row["severity"]] = int(row["count"])
    test_categories = [
        {
            "category": row["category"],
            "label": row["category_label"],
            "count": int(row["count"]),
        }
        for row in test_results.values("category", "category_label")
        .annotate(count=Count("id"))
        .order_by("-count")[:6]
    ]
    severity_counts = {
        value: 0 for value, _ in SecuritySeverity.choices
    }
    for row in findings.values("severity").annotate(count=Count("id")):
        severity_counts[row["severity"]] = int(row["count"])
    categories = [
        {"category": row["category"], "count": int(row["count"])}
        for row in findings.values("category")
        .annotate(count=Count("id"))
        .order_by("-count")[:6]
    ]
    recent = [
        {
            "id": str(scan.pk),
            "target_type": scan.target_type,
            "target_label": scan.target_label,
            "status": scan.status,
            "finding_count": scan.finding_count,
            "highest_severity": scan.highest_severity,
            "created_at": scan.created_at.isoformat(),
            "completed_at": scan.completed_at.isoformat()
            if scan.completed_at
            else None,
        }
        for scan in scans.order_by("-created_at")[:5]
    ]
    scan_daily = {
        row["day"].isoformat(): int(row["count"])
        for row in scans.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    }
    finding_daily = {
        row["day"].isoformat(): int(row["count"])
        for row in findings.annotate(day=TruncDate("detected_at"))
        .values("day")
        .annotate(count=Count("id"))
    }
    test_daily = {
        row["day"].isoformat(): int(row["count"])
        for row in test_results.annotate(day=TruncDate("executed_at"))
        .values("day")
        .annotate(count=Count("id"))
    }
    test_failed_daily = {
        row["day"].isoformat(): int(row["count"])
        for row in test_results.filter(verdict=SecurityTestResult.Verdict.FAILED)
        .annotate(day=TruncDate("executed_at"))
        .values("day")
        .annotate(count=Count("id"))
    }
    return {
        "scans": sum(scan_status.values()),
        "completed_scans": scan_status.get(SecurityScan.Status.COMPLETED, 0),
        "failed_scans": scan_status.get(SecurityScan.Status.FAILED, 0),
        "running_scans": scan_status.get(SecurityScan.Status.RUNNING, 0)
        + scan_status.get(SecurityScan.Status.QUEUED, 0),
        "findings": sum(finding_status.values()),
        "open_findings": finding_status.get(SecurityFinding.Status.OPEN, 0),
        "reviewed_findings": finding_status.get(SecurityFinding.Status.REVIEWED, 0),
        "resolved_findings": finding_status.get(SecurityFinding.Status.RESOLVED, 0),
        "severity_counts": severity_counts,
        "categories": categories,
        "test_runs": sum(test_run_status.values()),
        "completed_test_runs": test_run_status.get(
            SecurityTestRun.Status.COMPLETED, 0
        ),
        "failed_test_runs": test_run_status.get(SecurityTestRun.Status.FAILED, 0),
        "running_test_runs": test_run_status.get(SecurityTestRun.Status.RUNNING, 0)
        + test_run_status.get(SecurityTestRun.Status.QUEUED, 0),
        "tests_performed": sum(test_verdicts.values()),
        "tests_passed": test_verdicts.get(SecurityTestResult.Verdict.PASSED, 0),
        "tests_failed": test_verdicts.get(SecurityTestResult.Verdict.FAILED, 0),
        "tests_inconclusive": test_verdicts.get(
            SecurityTestResult.Verdict.INCONCLUSIVE, 0
        ),
        "test_severity_counts": test_severity_counts,
        "test_categories": test_categories,
        "recent_scans": recent,
        "daily_scans": scan_daily,
        "daily_findings": finding_daily,
        "daily_tests": test_daily,
        "daily_test_failures": test_failed_daily,
        "note": SECURITY_NOTE,
    }


def _attach_evaluation_scores(models: list[dict], model_scores: dict) -> None:
    for row in models:
        key = _key(
            row.get("provider_id"),
            row.get("provider_kind"),
            row.get("provider_name"),
            row.get("model_id"),
        )
        score = model_scores.get(key) or {}
        row["evaluation"] = {
            "runs": score.get("runs", 0),
            "avg_score": score.get("avg_score"),
            "scored_metrics": score.get("scored_metrics", 0),
        }


def _daily_points(
    filters: AnalyticsFilters,
    observability_trend: list[dict],
    executions: dict,
    evaluations: dict,
    security: dict,
) -> list[dict]:
    points = {}
    current = filters.start
    while current <= filters.end:
        points[current] = {
            "day": current.isoformat(),
            "calls": 0,
            "succeeded": 0,
            "failed": 0,
            "avg_latency_ms": None,
            "input_tokens": None,
            "output_tokens": None,
            "costs": [],
            "executions": 0,
            "executions_succeeded": 0,
            "executions_partial": 0,
            "executions_failed": 0,
            "evaluations": 0,
            "avg_evaluation_score": None,
            "security_scans": 0,
            "security_findings": 0,
            "security_tests": 0,
            "security_test_failures": 0,
        }
        current += timedelta(days=1)

    for row in observability_trend:
        try:
            day = date.fromisoformat(str(row.get("day")))
        except (TypeError, ValueError):
            continue
        point = points.get(day)
        if point is None:
            continue
        point.update(
            {
                "calls": int(row.get("count") or 0),
                "succeeded": int(row.get("succeeded") or 0),
                "failed": int(row.get("failed") or 0),
                "avg_latency_ms": row.get("avg_latency_ms"),
                "input_tokens": row.get("input_tokens"),
                "output_tokens": row.get("output_tokens"),
                "costs": row.get("costs") or [],
            }
        )

    for day, count in executions["daily"].items():
        point = points.get(day)
        if point:
            point["executions"] = count
    for day, counts in executions["daily_status"].items():
        point = points.get(day)
        if point:
            point["executions_succeeded"] = counts.get(
                Execution.Status.SUCCEEDED, 0
            )
            point["executions_partial"] = counts.get(Execution.Status.PARTIAL, 0)
            point["executions_failed"] = counts.get(Execution.Status.FAILED, 0)
    for day, count in evaluations["daily"].items():
        point = points.get(day)
        if point:
            point["evaluations"] = count
    for day, value in evaluations.get("daily_scores", {}).items():
        try:
            point = points.get(date.fromisoformat(str(day)))
        except (TypeError, ValueError):
            point = None
        if point:
            point["avg_evaluation_score"] = value
    for day, count in security["daily_scans"].items():
        try:
            point = points.get(date.fromisoformat(day))
        except (TypeError, ValueError):
            point = None
        if point:
            point["security_scans"] = count
    for day, count in security["daily_findings"].items():
        try:
            point = points.get(date.fromisoformat(day))
        except (TypeError, ValueError):
            point = None
        if point:
            point["security_findings"] = count
    for day, count in security["daily_tests"].items():
        try:
            point = points.get(date.fromisoformat(day))
        except (TypeError, ValueError):
            point = None
        if point:
            point["security_tests"] = count
    for day, count in security["daily_test_failures"].items():
        try:
            point = points.get(date.fromisoformat(day))
        except (TypeError, ValueError):
            point = None
        if point:
            point["security_test_failures"] = count
    return [points[day] for day in sorted(points)]


def dashboard(*, user, project_id, params) -> dict:
    project, filters, provider_name = _context(
        user=user, project_id=project_id, params=params
    )
    observability = observability_dashboard(
        user=user, project_id=project.pk, params=_parameters(filters)
    )
    executions = _execution_data(project, filters)
    evaluations = _evaluation_data(project, filters)
    security = _security_data(project, filters)
    _attach_evaluation_scores(
        observability.get("models", []), evaluations["model_scores"]
    )

    totals = observability["totals"]
    costs = observability["costs"]
    cost_status = observability["cost_status"]
    cost_detail = observability["cost_detail"]
    cost_section = {
        "status": cost_status,
        "detail": cost_detail,
        "currencies": costs,
        "estimated_calls": totals["estimated_cost_calls"],
        "unavailable_calls": totals["unavailable_cost_calls"],
        "by_model": [
            {
                "model_id": row["model_id"],
                "provider_name": row["provider_name"],
                "costs": row["costs"],
                "estimated_calls": row["estimated_calls"],
                "cost_status": row["cost_status"],
            }
            for row in observability["models"]
            if row["count"]
        ],
        "by_provider": [
            {
                "provider_name": row["provider_name"],
                "provider_kind": row["provider_kind"],
                "costs": row["costs"],
                "estimated_calls": row["estimated_calls"],
                "cost_status": row["cost_status"],
            }
            for row in observability["providers"]
            if row["count"]
        ],
        "note": COST_NOTE,
    }

    model_calls = {
        "total": totals["calls"],
        "succeeded": totals["succeeded"],
        "failed": totals["failed"],
        "failure_rate": round(totals["failed"] / totals["calls"], 4)
        if totals["calls"]
        else 0,
        "avg_latency_ms": totals["avg_latency_ms"],
        "avg_duration_ms": totals["avg_duration_ms"],
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
        "token_calls": totals["token_calls"],
        "calls_without_tokens": max(totals["calls"] - totals["token_calls"], 0),
        "cost_status": cost_status,
        "cost_detail": cost_detail,
        "costs": costs,
        "estimated_calls": totals["estimated_cost_calls"],
        "unavailable_calls": totals["unavailable_cost_calls"],
    }
    evaluation_summary = {
        key: evaluations[key]
        for key in (
            "total",
            "completed",
            "failed",
            "running",
            "avg_score",
            "scored_models",
            "scored_metrics",
        )
    }
    security_summary = {
        key: security[key]
        for key in (
            "scans",
            "completed_scans",
            "failed_scans",
            "running_scans",
            "findings",
            "open_findings",
            "reviewed_findings",
            "resolved_findings",
            "severity_counts",
            "categories",
            "test_runs",
            "completed_test_runs",
            "failed_test_runs",
            "running_test_runs",
            "tests_performed",
            "tests_passed",
            "tests_failed",
            "tests_inconclusive",
            "test_severity_counts",
            "test_categories",
            "recent_scans",
            "note",
        )
    }
    trend = _daily_points(
        filters,
        observability.get("trend", []),
        executions,
        evaluations,
        security,
    )
    data_quality = {
        "model_calls_without_tokens": model_calls["calls_without_tokens"],
        "calls_without_cost_estimate": totals["unavailable_cost_calls"],
        "evaluations_without_scores": max(
            evaluations["completed"] - evaluations.get("scored_evaluations", 0),
            0,
        ),
        "failed_security_scans": security["failed_scans"],
    }
    limitations = [
        COST_NOTE,
        EVALUATION_SCORE_NOTE,
        SECURITY_NOTE,
        "Analytics covers the selected project and reporting period. Provider "
        "and model filters apply to model calls, playground executions and "
        "evaluations; security counts remain target-wide for the period.",
    ]
    return {
        "project": str(project.pk),
        "workspace": str(project.workspace_id),
        "generated_at": timezone.now().isoformat(),
        "range": _range_meta(filters),
        "filters": _filter_meta(filters, provider_name),
        "summary": {
            "executions": {
                key: executions[key]
                for key in (
                    "total",
                    "succeeded",
                    "partial",
                    "failed",
                    "success_rate",
                )
            },
            "model_calls": model_calls,
            "evaluations": evaluation_summary,
            "security": security_summary,
        },
        "cost": cost_section,
        "usage": {
            "models": observability.get("models", []),
            "providers": observability.get("providers", []),
        },
        "evaluation_history": evaluations["history"],
        "trend": trend,
        "errors": observability.get("errors", []),
        "facets": observability.get("facets", {"providers": [], "models": []}),
        "data_quality": data_quality,
        "limitations": limitations,
        "scope_notes": [SECURITY_NOTE],
        "rollups": observability.get("rollups", {}),
        "telemetry": observability.get("telemetry", {}),
    }


def _raw_model_rows(raw):
    """Group already date-scoped raw traces by day and model."""
    dimensions = ("provider_id", "provider_name", "provider_kind", "model_id")
    rows = list(
        raw.annotate(day=TruncDate("started_at"))
        .values("day", *dimensions)
        .annotate(
            call_total=Count("id"),
            success_total=Count("id", filter=Q(status=Trace.Status.SUCCEEDED)),
            failed_total=Count("id", filter=Q(status=Trace.Status.FAILED)),
            latency_total=Sum(Coalesce("provider_latency_ms", "duration_ms")),
            latency_count=Count(
                "id",
                filter=Q(provider_latency_ms__isnull=False)
                | Q(duration_ms__isnull=False),
            ),
            input_token_total=Sum("input_tokens"),
            output_token_total=Sum("output_tokens"),
            token_call_total=Count(
                "id",
                filter=Q(input_tokens__isnull=False)
                | Q(output_tokens__isnull=False),
            ),
            estimated_call_total=Count(
                "id", filter=Q(cost_status=Trace.CostStatus.ESTIMATED)
            ),
            unavailable_call_total=Count(
                "id", filter=Q(cost_status=Trace.CostStatus.UNAVAILABLE)
            ),
        )
    )
    costs = defaultdict(dict)
    for row in (
        raw.filter(cost_status=Trace.CostStatus.ESTIMATED)
        .annotate(day=TruncDate("started_at"))
        .values("day", *dimensions, "cost_currency")
        .annotate(amount=Sum("estimated_cost"), call_total=Count("id"))
    ):
        key = (
            row["day"],
            str(row["provider_id"]) if row["provider_id"] else "",
            row["provider_name"],
            row["provider_kind"],
            row["model_id"],
        )
        costs[key][row["cost_currency"] or ""] = {
            "amount": row["amount"] or Decimal("0"),
            "calls": int(row["call_total"] or 0),
        }
    for row in rows:
        row["calls"] = row.pop("call_total")
        row["succeeded"] = row.pop("success_total")
        row["failed"] = row.pop("failed_total")
        row["input_token_total"] = row.pop("input_token_total")
        row["output_token_total"] = row.pop("output_token_total")
        row["token_calls"] = row.pop("token_call_total")
        row["estimated_calls"] = row.pop("estimated_call_total")
        row["unavailable_calls"] = row.pop("unavailable_call_total")
        key = (
            row["day"],
            str(row["provider_id"]) if row["provider_id"] else "",
            row["provider_name"],
            row["provider_kind"],
            row["model_id"],
        )
        row["_costs"] = costs.get(key, {})
    return rows


def _rollup_model_rows(rollups):
    """Group already date-scoped rollup rows by day and model."""
    dimensions = ("provider_id", "provider_name", "provider_kind", "model_id")
    rows = list(
        rollups.values("day", *dimensions).annotate(
            call_total=Sum("calls"),
            success_total=Sum("calls", filter=Q(status=Trace.Status.SUCCEEDED)),
            failed_total=Sum("calls", filter=Q(status=Trace.Status.FAILED)),
            latency_total=Sum("latency_total_ms"),
            latency_samples=Sum("latency_count"),
            input_token_total=Sum("input_tokens"),
            output_token_total=Sum("output_tokens"),
            token_call_total=Sum("token_calls"),
            estimated_call_total=Sum("estimated_calls"),
            unavailable_call_total=Sum("unavailable_calls"),
        )
    )
    costs = defaultdict(dict)
    for row in (
        rollups.filter(estimated_calls__gt=0)
        .values("day", *dimensions, "cost_currency")
        .annotate(amount=Sum("estimated_cost"), call_total=Sum("estimated_calls"))
    ):
        key = (
            row["day"],
            row["provider_id"] or "",
            row["provider_name"],
            row["provider_kind"],
            row["model_id"],
        )
        costs[key][row["cost_currency"] or ""] = {
            "amount": row["amount"] or Decimal("0"),
            "calls": int(row["call_total"] or 0),
        }
    for row in rows:
        row["calls"] = row.pop("call_total")
        row["succeeded"] = row.pop("success_total")
        row["failed"] = row.pop("failed_total")
        row["latency_count"] = row.pop("latency_samples")
        row["input_token_total"] = row.pop("input_token_total")
        row["output_token_total"] = row.pop("output_token_total")
        row["token_calls"] = row.pop("token_call_total")
        row["estimated_calls"] = row.pop("estimated_call_total")
        row["unavailable_calls"] = row.pop("unavailable_call_total")
        key = (
            row["day"],
            row["provider_id"] or "",
            row["provider_name"],
            row["provider_kind"],
            row["model_id"],
        )
        row["_costs"] = costs.get(key, {})
    return rows


def _model_trends(project, filters: AnalyticsFilters, evaluations: dict) -> list[dict]:
    # Use the observability window so model history and the overview dashboard
    # make the same rollup/raw split. This avoids counting a rolled-up day twice
    # or disagreeing with the main analytics totals.
    trace_filters = TraceFilters.from_params(_parameters(filters))
    traces = trace_filters.apply(Trace.objects.filter(project=project))
    window = _window(project, trace_filters, traces)
    rows = []
    if window.rollup is not None:
        rows.extend(_rollup_model_rows(window.rollup))
    rows.extend(_raw_model_rows(window.raw))

    groups: dict[str, dict] = {}
    for row in rows:
        provider_id = str(row["provider_id"]) if row["provider_id"] else None
        key = _key(
            provider_id,
            row["provider_kind"],
            row["provider_name"],
            row["model_id"],
        )
        group = groups.setdefault(
            key,
            {
                "key": key,
                "provider_id": provider_id,
                "provider_name": row["provider_name"],
                "provider_kind": row["provider_kind"],
                "model_id": row["model_id"],
                "days": {},
            },
        )
        day = row["day"]
        point = group["days"].setdefault(
            day,
            {
                "calls": 0,
                "succeeded": 0,
                "failed": 0,
                "latency_total": 0.0,
                "latency_count": 0,
                "input_token_total": 0,
                "output_token_total": 0,
                "token_calls": 0,
                "estimated_calls": 0,
                "unavailable_calls": 0,
                "costs": {},
            },
        )
        for name in (
            "calls",
            "succeeded",
            "failed",
            "latency_total",
            "latency_count",
            "input_token_total",
            "output_token_total",
            "token_calls",
            "estimated_calls",
            "unavailable_calls",
        ):
            if name == "latency_total":
                point[name] += float(row.get(name) or 0)
            else:
                point[name] += int(row.get(name) or 0)
        _merge_costs(point["costs"], row.get("_costs", {}))

    for key, score in evaluations["model_scores"].items():
        if key in groups:
            continue
        groups[key] = {
            "key": key,
            "provider_id": score["provider"],
            "provider_name": score["provider_name"],
            "provider_kind": score["provider_kind"],
            "model_id": score["model_id"],
            "days": {},
        }

    result = []
    for key, group in groups.items():
        days = []
        current = filters.start
        while current <= filters.end:
            point = group["days"].get(current)
            evaluation_daily = evaluations["model_daily_scores"].get(key, {})
            evaluation_score = evaluation_daily.get(current)
            if point is None:
                days.append(
                    {
                        "day": current.isoformat(),
                        "calls": 0,
                        "succeeded": 0,
                        "failed": 0,
                        "avg_latency_ms": None,
                        "input_tokens": None,
                        "output_tokens": None,
                        "costs": [],
                        "avg_evaluation_score": evaluation_score,
                    }
                )
            else:
                days.append(
                    {
                        "day": current.isoformat(),
                        "calls": int(point["calls"]),
                        "succeeded": int(point["succeeded"]),
                        "failed": int(point["failed"]),
                        "avg_latency_ms": round(
                            point["latency_total"] / point["latency_count"], 2
                        )
                        if point["latency_count"]
                        else None,
                        "input_tokens": int(point["input_token_total"])
                        if point["token_calls"]
                        else None,
                        "output_tokens": int(point["output_token_total"])
                        if point["token_calls"]
                        else None,
                        "costs": _cost_list(point["costs"]),
                        "avg_evaluation_score": evaluation_score,
                    }
                )
            current += timedelta(days=1)

        calls = sum(day["calls"] for day in days)
        succeeded = sum(day["succeeded"] for day in days)
        failed = sum(day["failed"] for day in days)
        # The per-day averages cannot be recombined without their sample counts.
        raw_latency_total = sum(
            point["latency_total"] for point in group["days"].values()
        )
        raw_latency_count = sum(
            point["latency_count"] for point in group["days"].values()
        )
        token_calls = sum(
            point["token_calls"] for point in group["days"].values()
        )
        input_tokens = sum(
            point["input_token_total"] for point in group["days"].values()
        )
        output_tokens = sum(
            point["output_token_total"] for point in group["days"].values()
        )
        estimated_calls = sum(
            point["estimated_calls"] for point in group["days"].values()
        )
        unavailable_calls = sum(
            point["unavailable_calls"] for point in group["days"].values()
        )
        all_costs = {}
        for point in group["days"].values():
            _merge_costs(all_costs, point["costs"])
        evaluation = evaluations["model_scores"].get(key, {})
        result.append(
            {
                "key": key,
                "provider_id": group["provider_id"],
                "provider_name": group["provider_name"],
                "provider_kind": group["provider_kind"],
                "model_id": group["model_id"],
                "calls": calls,
                "succeeded": succeeded,
                "failed": failed,
                "failure_rate": round(failed / calls, 4) if calls else 0,
                "avg_latency_ms": round(raw_latency_total / raw_latency_count, 2)
                if raw_latency_count
                else None,
                "input_tokens": input_tokens if token_calls else None,
                "output_tokens": output_tokens if token_calls else None,
                "token_calls": token_calls,
                "costs": _cost_list(all_costs),
                "estimated_calls": estimated_calls,
                "unavailable_calls": unavailable_calls,
                "cost_status": (
                    "unavailable"
                    if not estimated_calls
                    else "partial"
                    if unavailable_calls
                    else "estimated"
                ),
                "evaluation": {
                    "runs": evaluation.get("runs", 0),
                    "avg_score": evaluation.get("avg_score"),
                    "scored_metrics": evaluation.get("scored_metrics", 0),
                },
                "trend": days,
            }
        )
    result.sort(key=lambda row: (-row["calls"], row["model_id"]))
    return result


def model_performance(*, user, project_id, params) -> dict:
    project, filters, provider_name = _context(
        user=user, project_id=project_id, params=params
    )
    evaluations = _evaluation_data(project, filters)
    models = _model_trends(project, filters, evaluations)
    return {
        "project": str(project.pk),
        "workspace": str(project.workspace_id),
        "generated_at": timezone.now().isoformat(),
        "range": _range_meta(filters),
        "filters": _filter_meta(filters, provider_name),
        "models": models,
        "comparison_note": (
            "Model history uses completed daily trace rollups for older days "
            "and live traces for newer days. Evaluation scores are stored "
            "metric averages from completed runs."
        ),
        "warnings": [COST_NOTE, EVALUATION_SCORE_NOTE],
    }
