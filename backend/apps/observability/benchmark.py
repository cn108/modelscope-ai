"""Synthetic observability data for benchmarks and query-count regression tests.

This module deliberately creates its own temporary workspace/project so a
benchmark never adds synthetic rows to a real tenant.  The dataset has two
parts:

* rollup buckets for completed days, representing a large historical call
  volume without storing every raw trace; and
* a current-day raw trace set, so the live edge of the dashboard is exercised
  too.

The benchmark measures ``services.dashboard`` directly, which is the same
workspace-scoped aggregation path used by the public API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
from decimal import Decimal
from statistics import median
from time import perf_counter
from uuid import uuid4

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.observability.models import Trace, TraceRollup, TraceRollupState
from apps.observability.services import dashboard
from apps.playground.models import Execution, ExecutionResult
from apps.projects.models import Project
from apps.providers.models import ProviderConfig
from apps.workspaces.models import Membership, Workspace

ROLLUP_BATCH_SIZE = 1_000
TRACE_BATCH_SIZE = 1_000


@dataclass
class BenchmarkDataset:
    workspace: Workspace
    project: Project
    user: object
    rollup_rows: int
    raw_traces: int
    calls_represented: int


def _day_start(day) -> datetime:
    return timezone.make_aware(datetime.combine(day, dt_time.min))


def _next_day_start(day) -> datetime:
    return _day_start(day + timedelta(days=1))


def _make_workspace(user, *, label: str) -> tuple[Workspace, Project]:
    workspace = Workspace.objects.create(
        name=f"Observability benchmark {label}",
        owner=user,
        settings={"benchmark": True},
    )
    Membership.objects.create(
        workspace=workspace,
        user=user,
        role=Membership.Role.OWNER,
    )
    project = Project.objects.create(
        workspace=workspace,
        name="Observability benchmark",
        description="Temporary synthetic data for dashboard benchmarks.",
        created_by=user,
    )
    return workspace, project


def _make_providers(project: Project, count: int) -> list[ProviderConfig]:
    providers = [
        ProviderConfig(
            project=project,
            name=f"Benchmark provider {index:02d}",
            kind=ProviderConfig.Kind.OLLAMA,
            endpoint="http://localhost:11434",
        )
        for index in range(max(count, 1))
    ]
    return ProviderConfig.objects.bulk_create(providers)


def _make_raw_result(project: Project, providers, user) -> ExecutionResult:
    execution = Execution.objects.create(
        project=project,
        mode=Execution.Mode.SINGLE,
        system_prompt="Benchmark system prompt.",
        user_prompt="Benchmark user prompt.",
        parameters={"max_tokens": 64},
        status=Execution.Status.SUCCEEDED,
        created_by=user,
    )
    return ExecutionResult.objects.create(
        execution=execution,
        position=1,
        provider=providers[0],
        provider_name=providers[0].name,
        provider_kind=providers[0].kind,
        model_id="benchmark-model-00",
        content="Benchmark response.",
        input_tokens=100,
        output_tokens=40,
        tokens_are_provider_reported=True,
        latency_ms=450,
        status=ExecutionResult.Status.SUCCEEDED,
    )


def _rollup_rows(
    *,
    project: Project,
    providers: list[ProviderConfig],
    models: int,
    days: int,
    calls_per_bucket: int,
    today,
):
    total = 0
    batch = []
    for day_offset in range(days, 0, -1):
        day = today - timedelta(days=day_offset)
        first_seen = _day_start(day)
        last_seen = _next_day_start(day) - timedelta(seconds=1)
        for provider in providers:
            for model_index in range(max(models, 1)):
                for source in (Trace.Source.PLAYGROUND, Trace.Source.EVALUATION):
                    for role in (Trace.Role.MODEL, Trace.Role.JUDGE):
                        for status in (Trace.Status.SUCCEEDED, Trace.Status.FAILED):
                            calls = max(calls_per_bucket, 1)
                            failures = calls if status == Trace.Status.FAILED else 0
                            batch.append(
                                TraceRollup(
                                    project=project,
                                    day=day,
                                    source=source,
                                    role=role,
                                    status=status,
                                    provider_id=str(provider.pk),
                                    provider_name=provider.name,
                                    provider_kind=provider.kind,
                                    model_id=f"benchmark-model-{model_index:02d}",
                                    cost_currency="USD",
                                    calls=calls,
                                    input_tokens=calls * 100,
                                    output_tokens=calls * 40,
                                    token_calls=calls,
                                    latency_total_ms=calls * 450.0,
                                    latency_count=calls,
                                    duration_total_ms=calls * 500.0,
                                    duration_count=calls,
                                    estimated_cost=Decimal("0.0001") * calls,
                                    estimated_calls=calls,
                                    unavailable_calls=0,
                                    error_counts={"provider_error": failures}
                                    if failures
                                    else {},
                                    first_seen=first_seen,
                                    last_seen=last_seen,
                                )
                            )
                            total += calls
                            if len(batch) >= ROLLUP_BATCH_SIZE:
                                TraceRollup.objects.bulk_create(batch)
                                batch.clear()
    if batch:
        TraceRollup.objects.bulk_create(batch)
    return total


def _raw_traces(
    *,
    project: Project,
    result: ExecutionResult,
    providers: list[ProviderConfig],
    models: int,
    count: int,
    today,
):
    day_start = _day_start(today)
    day_span = int((_next_day_start(today) - day_start).total_seconds() * 1000)
    batch = []
    created = 0
    for index in range(count):
        failed = index % 10 == 0
        provider = providers[index % len(providers)]
        model_id = f"benchmark-model-{index % max(models, 1):02d}"
        started = day_start + timedelta(milliseconds=(index * 997) % max(day_span - 1, 1))
        ended = started + timedelta(milliseconds=500)
        batch.append(
            Trace(
                id=uuid4(),
                project=project,
                source=Trace.Source.PLAYGROUND,
                role=Trace.Role.MODEL,
                execution_result=result,
                provider=provider,
                provider_name=provider.name,
                provider_kind=provider.kind,
                model_id=model_id,
                status=Trace.Status.FAILED if failed else Trace.Status.SUCCEEDED,
                started_at=started,
                ended_at=ended,
                duration_ms=500.0,
                provider_latency_ms=450.0,
                input_tokens=None if failed else 100,
                output_tokens=None if failed else 40,
                estimated_cost=None,
                cost_currency="",
                cost_status=Trace.CostStatus.UNAVAILABLE,
                cost_detail="Synthetic benchmark trace.",
                error={"category": "provider_error", "message": "Synthetic failure."}
                if failed
                else None,
                attributes={"benchmark": True},
                request_text="",
                response_text="",
                otel_trace_id="",
                created_at=timezone.now(),
            )
        )
        created += 1
        if len(batch) >= TRACE_BATCH_SIZE:
            Trace.objects.bulk_create(batch)
            batch.clear()
    if batch:
        Trace.objects.bulk_create(batch)
    return created


def seed_benchmark(
    *,
    user,
    days: int = 365,
    models: int = 20,
    providers: int = 4,
    raw_traces: int = 10_000,
    calls_per_bucket: int = 100,
) -> BenchmarkDataset:
    """Create a temporary production-sized benchmark dataset.

    Defaults represent 365 days, 4 providers, 20 models and 100 calls per
    source/role/status bucket (about 23 million calls) plus 10,000 current-day
    raw traces.  The caller is responsible for deleting ``workspace`` when
    finished.
    """
    if days < 0 or models < 1 or providers < 1 or raw_traces < 0:
        raise ValueError("Benchmark dimensions must be non-negative and non-zero.")

    workspace, project = _make_workspace(user, label=str(uuid4())[:8])
    try:
        provider_rows = _make_providers(project, providers)
        result = _make_raw_result(project, provider_rows, user)
        today = timezone.now().date()
        represented = _rollup_rows(
            project=project,
            providers=provider_rows,
            models=models,
            days=days,
            calls_per_bucket=calls_per_bucket,
            today=today,
        )
        raw_created = _raw_traces(
            project=project,
            result=result,
            providers=provider_rows,
            models=models,
            count=raw_traces,
            today=today,
        )
        if days:
            TraceRollupState.objects.create(
                project=project, through_day=today - timedelta(days=1)
            )
        return BenchmarkDataset(
            workspace=workspace,
            project=project,
            user=user,
            rollup_rows=TraceRollup.objects.filter(project=project).count(),
            raw_traces=raw_created,
            calls_represented=represented,
        )
    except Exception:
        workspace.delete()
        raise


def measure_dashboard(*, dataset: BenchmarkDataset, runs: int = 5) -> dict:
    """Measure the dashboard service, including database query counts."""
    runs = max(runs, 1)
    dashboard(user=dataset.user, project_id=dataset.project.pk, params={})
    timings: list[float] = []
    query_counts: list[int] = []
    result = None
    for _ in range(runs):
        with CaptureQueriesContext(connection) as queries:
            started = perf_counter()
            result = dashboard(
                user=dataset.user, project_id=dataset.project.pk, params={}
            )
            timings.append((perf_counter() - started) * 1000)
        query_counts.append(len(queries))

    ordered = sorted(timings)
    p95_index = max(int(len(ordered) * 0.95) - 1, 0)
    return {
        "database": connection.vendor,
        "rollup_rows": dataset.rollup_rows,
        "raw_traces": dataset.raw_traces,
        "calls_represented": dataset.calls_represented,
        "runs": runs,
        "queries": {
            "min": min(query_counts),
            "max": max(query_counts),
            "samples": query_counts,
        },
        "latency_ms": {
            "min": round(min(timings), 2),
            "median": round(median(timings), 2),
            "p95": round(ordered[p95_index], 2),
            "max": round(max(timings), 2),
        },
        "dashboard": {
            "calls": result["totals"]["calls"],
            "rollups_through": result["rollups"]["through"],
            "cost_status": result["cost_status"],
        },
    }


def cleanup_benchmark(dataset: BenchmarkDataset) -> None:
    workspace_id = dataset.workspace.pk
    if workspace_id:
        Workspace.objects.filter(pk=workspace_id).delete()
