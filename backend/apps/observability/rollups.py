"""Daily trace rollups and configurable retention.

The dashboard can keep using raw traces for recent days while completed days
are read from ``TraceRollup``.  Rollups are rebuilt idempotently from raw traces
for one UTC day, then the project watermark is advanced.  Retention deletes raw
traces only after the affected days have been rolled up, so historical totals
survive while the raw table stays bounded.
"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Min, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.observability.models import Trace, TraceRollup, TraceRollupState
from apps.projects.models import Project

logger = logging.getLogger(__name__)

ROLLUP_DIMENSIONS = (
    "source",
    "role",
    "status",
    "provider_id",
    "provider_name",
    "provider_kind",
    "model_id",
    "cost_currency",
)
ROLLUP_BATCH_SIZE = 500


def _day_start(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, dt_time.min))


def _next_day_start(day: date) -> datetime:
    return _day_start(day + timedelta(days=1))


def _complete_day(now: datetime | None = None) -> date:
    """Only fully elapsed UTC days are safe to aggregate."""
    return (now or timezone.now()).date() - timedelta(days=1)


def _provider_key(value) -> str:
    return str(value) if value else ""


def _row_dimensions(row: dict) -> dict:
    values = {name: row.get(name) for name in ROLLUP_DIMENSIONS}
    values["provider_id"] = _provider_key(values.get("provider_id"))
    return values


def _bucket_key(row: dict) -> tuple:
    values = _row_dimensions(row)
    return tuple(values[name] for name in ROLLUP_DIMENSIONS)


def _rollup_enabled() -> bool:
    return bool(getattr(settings, "OBSERVABILITY_ROLLUP_ENABLED", True))


def configured_retention_days() -> int:
    raw = getattr(settings, "OBSERVABILITY_TRACE_RETENTION_DAYS", 0) or 0
    try:
        days = int(raw)
    except (TypeError, ValueError):
        raise ValueError("OBSERVABILITY_TRACE_RETENTION_DAYS must be an integer.") from None
    if days < 0:
        raise ValueError("OBSERVABILITY_TRACE_RETENTION_DAYS cannot be negative.")
    return days


def _build_day(project: Project, day: date) -> int:
    """Rebuild one day's aggregate rows; returns the number of rollup rows."""
    started_at = _day_start(day)
    ended_at = _next_day_start(day)
    traces = Trace.objects.filter(
        project=project, started_at__gte=started_at, started_at__lt=ended_at
    )

    with transaction.atomic():
        TraceRollup.objects.filter(project=project, day=day).delete()
        if not traces.exists():
            return 0

        rows = list(
            traces.values(*ROLLUP_DIMENSIONS).annotate(
                calls=Count("id"),
                input_token_total=Sum("input_tokens"),
                output_token_total=Sum("output_tokens"),
                token_calls=Count(
                    "id",
                    filter=Q(input_tokens__isnull=False)
                    | Q(output_tokens__isnull=False),
                ),
                latency_total_ms=Sum(
                    Coalesce("provider_latency_ms", "duration_ms")
                ),
                latency_count=Count(
                    "id",
                    filter=Q(provider_latency_ms__isnull=False)
                    | Q(duration_ms__isnull=False),
                ),
                duration_total_ms=Sum("duration_ms"),
                duration_count=Count(
                    "id", filter=Q(duration_ms__isnull=False)
                ),
                estimated_cost=Sum(
                    "estimated_cost",
                    filter=Q(cost_status=Trace.CostStatus.ESTIMATED),
                ),
                estimated_calls=Count(
                    "id", filter=Q(cost_status=Trace.CostStatus.ESTIMATED)
                ),
                unavailable_calls=Count(
                    "id", filter=Q(cost_status=Trace.CostStatus.UNAVAILABLE)
                ),
                first_seen=Min("started_at"),
                last_seen=Max("started_at"),
            )
        )

        error_counts: dict[tuple, dict[str, int]] = {}
        error_rows = (
            traces.exclude(error__isnull=True)
            .values(*ROLLUP_DIMENSIONS, "error__category")
            .annotate(count=Count("id"))
        )
        for row in error_rows:
            key = _bucket_key(row)
            category = str(row.get("error__category") or "unknown")[:120]
            bucket = error_counts.setdefault(key, {})
            bucket[category] = bucket.get(category, 0) + row["count"]

        objects = []
        for row in rows:
            values = _row_dimensions(row)
            objects.append(
                TraceRollup(
                    project=project,
                    day=day,
                    **values,
                    calls=row["calls"] or 0,
                    input_tokens=row["input_token_total"] or 0,
                    output_tokens=row["output_token_total"] or 0,
                    token_calls=row["token_calls"] or 0,
                    latency_total_ms=row["latency_total_ms"] or 0,
                    latency_count=row["latency_count"] or 0,
                    duration_total_ms=row["duration_total_ms"] or 0,
                    duration_count=row["duration_count"] or 0,
                    estimated_cost=row["estimated_cost"] or Decimal("0"),
                    estimated_calls=row["estimated_calls"] or 0,
                    unavailable_calls=row["unavailable_calls"] or 0,
                    error_counts=error_counts.get(_bucket_key(row), {}),
                    first_seen=row["first_seen"] or started_at,
                    last_seen=row["last_seen"] or ended_at,
                )
            )
        TraceRollup.objects.bulk_create(objects, batch_size=ROLLUP_BATCH_SIZE)
        return len(objects)


def rollup_project(
    *, project: Project, through_day: date | None = None, start_day: date | None = None
) -> dict:
    """Build every missing day up to ``through_day`` for one project.

    The watermark only advances after all days succeed.  Calling this again is
    safe: each day is deleted and recreated from raw traces before the
    watermark moves forward.
    """
    if not _rollup_enabled():
        return {
            "project": str(project.pk),
            "enabled": False,
            "through_day": None,
            "days": 0,
        }

    end = min(through_day or _complete_day(), _complete_day())
    state = TraceRollupState.objects.filter(project=project).first()

    if start_day is None:
        if state is not None:
            start = state.through_day + timedelta(days=1)
        else:
            earliest_trace = (
                Trace.objects.filter(project=project).aggregate(first=Min("started_at"))[
                    "first"
                ]
            )
            earliest_rollup = (
                TraceRollup.objects.filter(project=project).aggregate(first=Min("day"))[
                    "first"
                ]
            )
            candidates = [
                item.date() for item in (earliest_trace, earliest_rollup) if item
            ]
            if not candidates:
                return {
                    "project": str(project.pk),
                    "enabled": True,
                    "through_day": end.isoformat(),
                    "days": 0,
                }
            start = min(candidates)
    else:
        start = start_day

    days = 0
    current = start
    while current <= end:
        _build_day(project, current)
        days += 1
        current += timedelta(days=1)

    if state is None:
        TraceRollupState.objects.create(project=project, through_day=end)
    elif end > state.through_day:
        state.through_day = end
        state.save(update_fields=["through_day", "updated_at"])

    return {
        "project": str(project.pk),
        "enabled": True,
        "through_day": end.isoformat(),
        "days": days,
    }


def rollup_all(*, through_day: date | None = None) -> dict:
    """Roll up all projects that have trace data or an existing watermark."""
    if not _rollup_enabled():
        return {"enabled": False, "through_day": None, "projects": 0, "days": 0, "errors": 0}

    end = min(through_day or _complete_day(), _complete_day())
    projects = (
        Project.objects.filter(
            Q(traces__isnull=False)
            | Q(trace_rollups__isnull=False)
            | Q(trace_rollup_state__isnull=False)
        )
        .distinct()
        .order_by("created_at")
    )

    processed = 0
    days = 0
    errors = 0
    for project in projects.iterator():
        try:
            result = rollup_project(project=project, through_day=end)
        except Exception:  # noqa: BLE001 - one project must not stop the batch
            errors += 1
            logger.exception("Trace rollups failed for project %s.", project.pk)
            continue
        processed += 1
        days += result["days"]

    return {
        "enabled": True,
        "through_day": end.isoformat(),
        "projects": processed,
        "days": days,
        "errors": errors,
    }


def _delete_traces_before(*, project: Project, cutoff: datetime) -> int:
    """Delete raw traces (and their spans by cascade) in bounded batches."""
    queryset = Trace.objects.filter(project=project, started_at__lt=cutoff)
    deleted = 0
    while True:
        ids = list(queryset.values_list("pk", flat=True)[:ROLLUP_BATCH_SIZE])
        if not ids:
            return deleted
        Trace.objects.filter(pk__in=ids).delete()
        deleted += len(ids)


def purge_old_traces(
    *, retention_days: int | None = None, now: datetime | None = None
) -> dict:
    """Roll up then delete complete days older than the configured retention."""
    if not _rollup_enabled():
        return {
            "enabled": False,
            "reason": "Trace rollups are disabled; raw traces were not purged.",
            "deleted": 0,
        }

    days = configured_retention_days() if retention_days is None else int(retention_days)
    if days < 0:
        raise ValueError("Retention days cannot be negative.")
    if days == 0:
        return {"enabled": False, "reason": "Trace retention is disabled.", "deleted": 0}

    current = now or timezone.now()
    cutoff_day = current.date() - timedelta(days=days)
    cutoff = _day_start(cutoff_day)
    through_day = cutoff_day - timedelta(days=1)

    project_ids = list(
        Trace.objects.filter(started_at__lt=cutoff)
        .values_list("project_id", flat=True)
        .distinct()
    )
    deleted = 0
    rolled_projects = 0
    errors = 0
    for project in Project.objects.filter(pk__in=project_ids).order_by("created_at"):
        try:
            # A failed rollup must not be followed by deletion: the dashboard
            # would lose the only copy of that history.
            rollup_project(project=project, through_day=through_day)
            rolled_projects += 1
        except Exception:  # noqa: BLE001
            errors += 1
            logger.exception("Trace retention skipped project %s after rollup failure.", project.pk)
            continue
        deleted += _delete_traces_before(project=project, cutoff=cutoff)

    return {
        "enabled": True,
        "cutoff_day": cutoff_day.isoformat(),
        "through_day": through_day.isoformat(),
        "projects": rolled_projects,
        "deleted": deleted,
        "errors": errors,
    }
