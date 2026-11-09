"""Trace recording, workspace-scoped queries and dashboard aggregation.

Trace rows are written from the existing execution paths (playground, dataset
evaluation and the DeepEval judge).  The dashboard uses compact daily rollups
for completed days and raw traces for newer days, so it does not have to scan
the full history on every request.  A project watermark prevents raw and
rolled-up days from being counted twice.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Min, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import NotFound, ValidationError

from apps.observability.models import (
    Span,
    Trace,
    TraceRollup,
    TraceRollupState,
)
from apps.observability.rollups import configured_retention_days
from apps.projects.services import project_for_user
from apps.workspaces.models import Membership
from apps.workspaces.permissions import require_membership
from integrations.telemetry.logging import bind_trace_id
from integrations.telemetry.pricing import estimate_cost
from integrations.telemetry.tracing import tracing_status

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TraceFilters:
    started_from: datetime | None = None
    started_to: datetime | None = None
    provider_id: uuid.UUID | None = None
    model_id: str = ""
    status: str = ""
    source: str = ""
    role: str = ""

    @classmethod
    def from_params(cls, params) -> "TraceFilters":
        started_from = _parse_bound(params.get("from"), end_of_day=False)
        started_to = _parse_bound(params.get("to"), end_of_day=True)
        if started_from and started_to and started_from > started_to:
            raise ValidationError({"detail": "The start date must be before the end date."})

        provider_id = None
        raw_provider = (params.get("provider") or "").strip()
        if raw_provider:
            try:
                provider_id = uuid.UUID(raw_provider)
            except (TypeError, ValueError):
                raise ValidationError({"provider": "Provider must be a UUID."}) from None

        status = (params.get("status") or "").strip()
        if status and status not in Trace.Status.values:
            raise ValidationError({"status": "Unknown execution status."})
        source = (params.get("source") or "").strip()
        if source and source not in Trace.Source.values:
            raise ValidationError({"source": "Unknown execution source."})
        role = (params.get("role") or "").strip()
        if role and role not in Trace.Role.values:
            raise ValidationError({"role": "Unknown call role."})

        return cls(
            started_from=started_from,
            started_to=started_to,
            provider_id=provider_id,
            model_id=(params.get("model") or "").strip()[:200],
            status=status,
            source=source,
            role=role,
        )

    def apply(self, queryset):
        if self.started_from:
            queryset = queryset.filter(started_at__gte=self.started_from)
        if self.started_to:
            queryset = queryset.filter(started_at__lte=self.started_to)
        if self.provider_id:
            queryset = queryset.filter(provider_id=self.provider_id)
        if self.model_id:
            queryset = queryset.filter(model_id=self.model_id)
        if self.status:
            queryset = queryset.filter(status=self.status)
        if self.source:
            queryset = queryset.filter(source=self.source)
        if self.role:
            queryset = queryset.filter(role=self.role)
        return queryset


def _parse_bound(value: str | None, *, end_of_day: bool) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    day = parse_date(text)
    if day is not None:
        parsed = datetime.combine(day, dt_time.max if end_of_day else dt_time.min)
    else:
        parsed = parse_datetime(text)
    if parsed is None:
        raise ValidationError({"detail": "Dates must be ISO dates or timestamps."})
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _day_start(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, dt_time.min))


def _next_day_start(day: date) -> datetime:
    return _day_start(day + timedelta(days=1))


def _local_date(value: datetime) -> date:
    if timezone.is_aware(value):
        return timezone.localtime(value).date()
    return value.date()


def _local_time(value: datetime) -> dt_time:
    if timezone.is_aware(value):
        return timezone.localtime(value).time()
    return value.time()


def project_traces(*, user, project_id, params) -> tuple:
    """Resolve the project and return ``(project, filters, queryset)``."""
    project = project_for_user(user, project_id, Membership.Role.VIEWER)
    filters = TraceFilters.from_params(params)
    queryset = filters.apply(Trace.objects.filter(project=project))
    return project, filters, queryset


def trace_queryset(*, user, project_id, params):
    _, _, queryset = project_traces(user=user, project_id=project_id, params=params)
    return (
        queryset.select_related(
            "execution_result__execution",
            "evaluation_result__evaluation",
            "evaluation_result__model",
        )
        .prefetch_related("spans")
        .order_by("-started_at")
    )


def trace_for_user(user, trace_id) -> Trace:
    trace = (
        Trace.objects.select_related(
            "project",
            "project__workspace",
            "execution_result__execution",
            "evaluation_result__evaluation",
            "evaluation_result__model",
        )
        .prefetch_related("spans")
        .filter(pk=trace_id)
        .first()
    )
    if trace is None:
        raise NotFound("Trace not found.")
    require_membership(user, trace.project.workspace_id, Membership.Role.VIEWER)
    return trace


def _money(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return format(value.quantize(Decimal("0.000001")), "f")


def _n(value) -> int:
    return int(value or 0)


def _empty_totals() -> dict:
    return {
        "calls": 0,
        "succeeded": 0,
        "failed": 0,
        "latency_total": 0.0,
        "latency_count": 0,
        "duration_total": 0.0,
        "duration_count": 0,
        "input_token_total": 0,
        "output_token_total": 0,
        "token_calls": 0,
        "estimated_calls": 0,
        "unavailable_calls": 0,
        "first_seen": None,
        "last_seen": None,
        "costs": {},
        "roles": {},
    }


def _merge_cost_maps(*maps: dict) -> dict:
    merged = {}
    for source in maps:
        for currency, item in (source or {}).items():
            target = merged.setdefault(
                currency, {"amount": Decimal("0"), "calls": 0}
            )
            target["amount"] += item["amount"]
            target["calls"] += item["calls"]
    return merged


def _merge_role_maps(*maps: dict) -> dict:
    merged = {}
    for source in maps:
        for role, count in (source or {}).items():
            merged[role] = merged.get(role, 0) + count
    return merged


def _raw_totals(queryset) -> dict:
    row = queryset.aggregate(
        calls=Count("id"),
        succeeded=Count("id", filter=Q(status=Trace.Status.SUCCEEDED)),
        failed=Count("id", filter=Q(status=Trace.Status.FAILED)),
        latency_total=Sum(Coalesce("provider_latency_ms", "duration_ms")),
        latency_count=Count(
            "id",
            filter=Q(provider_latency_ms__isnull=False)
            | Q(duration_ms__isnull=False),
        ),
        duration_total=Sum("duration_ms"),
        duration_count=Count("id", filter=Q(duration_ms__isnull=False)),
        input_token_total=Sum("input_tokens"),
        output_token_total=Sum("output_tokens"),
        token_calls=Count(
            "id",
            filter=Q(input_tokens__isnull=False) | Q(output_tokens__isnull=False),
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
    costs = {}
    for cost_row in (
        queryset.filter(cost_status=Trace.CostStatus.ESTIMATED)
        .values("cost_currency")
        .annotate(amount=Sum("estimated_cost"), calls=Count("id"))
    ):
        costs[cost_row["cost_currency"] or ""] = {
            "amount": cost_row["amount"] or Decimal("0"),
            "calls": _n(cost_row["calls"]),
        }
    roles = {
        role_row["role"]: _n(role_row["count"])
        for role_row in queryset.values("role").annotate(count=Count("id"))
    }
    return {
        "calls": _n(row["calls"]),
        "succeeded": _n(row["succeeded"]),
        "failed": _n(row["failed"]),
        "latency_total": float(row["latency_total"] or 0),
        "latency_count": _n(row["latency_count"]),
        "duration_total": float(row["duration_total"] or 0),
        "duration_count": _n(row["duration_count"]),
        "input_token_total": _n(row["input_token_total"]),
        "output_token_total": _n(row["output_token_total"]),
        "token_calls": _n(row["token_calls"]),
        "estimated_calls": _n(row["estimated_calls"]),
        "unavailable_calls": _n(row["unavailable_calls"]),
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "costs": costs,
        "roles": roles,
    }


def _rollup_totals(queryset) -> dict:
    if queryset is None:
        return _empty_totals()
    row = queryset.aggregate(
        call_total=Sum("calls"),
        success_total=Sum("calls", filter=Q(status=Trace.Status.SUCCEEDED)),
        failed_total=Sum("calls", filter=Q(status=Trace.Status.FAILED)),
        latency_total=Sum("latency_total_ms"),
        latency_samples=Sum("latency_count"),
        duration_total=Sum("duration_total_ms"),
        duration_samples=Sum("duration_count"),
        input_token_total=Sum("input_tokens"),
        output_token_total=Sum("output_tokens"),
        token_call_total=Sum("token_calls"),
        estimated_call_total=Sum("estimated_calls"),
        unavailable_call_total=Sum("unavailable_calls"),
        first_seen_at=Min("first_seen"),
        last_seen_at=Max("last_seen"),
    )
    costs = {}
    for cost_row in (
        queryset.filter(estimated_calls__gt=0)
        .values("cost_currency")
        .annotate(
            amount=Sum("estimated_cost"),
            call_total=Sum("estimated_calls"),
        )
    ):
        costs[cost_row["cost_currency"] or ""] = {
            "amount": cost_row["amount"] or Decimal("0"),
            "calls": _n(cost_row["call_total"]),
        }
    roles = {
        role_row["role"]: _n(role_row["call_total"])
        for role_row in queryset.values("role").annotate(
            call_total=Sum("calls")
        )
    }
    return {
        "calls": _n(row["call_total"]),
        "succeeded": _n(row["success_total"]),
        "failed": _n(row["failed_total"]),
        "latency_total": float(row["latency_total"] or 0),
        "latency_count": _n(row["latency_samples"]),
        "duration_total": float(row["duration_total"] or 0),
        "duration_count": _n(row["duration_samples"]),
        "input_token_total": _n(row["input_token_total"]),
        "output_token_total": _n(row["output_token_total"]),
        "token_calls": _n(row["token_call_total"]),
        "estimated_calls": _n(row["estimated_call_total"]),
        "unavailable_calls": _n(row["unavailable_call_total"]),
        "first_seen": row["first_seen_at"],
        "last_seen": row["last_seen_at"],
        "costs": costs,
        "roles": roles,
    }


def _merge_totals(*sources: dict) -> dict:
    merged = _empty_totals()
    for source in sources:
        for key in (
            "calls",
            "succeeded",
            "failed",
            "latency_total",
            "latency_count",
            "duration_total",
            "duration_count",
            "input_token_total",
            "output_token_total",
            "token_calls",
            "estimated_calls",
            "unavailable_calls",
        ):
            merged[key] += source.get(key, 0) or 0
        for key in ("first_seen", "last_seen"):
            value = source.get(key)
            if value is not None and (
                merged[key] is None
                or (key == "first_seen" and value < merged[key])
                or (key == "last_seen" and value > merged[key])
            ):
                merged[key] = value
    merged["costs"] = _merge_cost_maps(
        *(source.get("costs", {}) for source in sources)
    )
    merged["roles"] = _merge_role_maps(
        *(source.get("roles", {}) for source in sources)
    )
    return merged


def _finalize_totals(totals: dict) -> dict:
    latency = (
        totals["latency_total"] / totals["latency_count"]
        if totals["latency_count"]
        else None
    )
    duration = (
        totals["duration_total"] / totals["duration_count"]
        if totals["duration_count"]
        else None
    )
    costs = [
        {
            "currency": currency or "Unspecified",
            "amount": _money(item["amount"]),
            "calls": item["calls"],
        }
        for currency, item in sorted(totals["costs"].items())
    ]
    return {
        "calls": totals["calls"],
        "succeeded": totals["succeeded"],
        "failed": totals["failed"],
        "avg_latency_ms": round(latency, 2) if latency is not None else None,
        "avg_duration_ms": round(duration, 2) if duration is not None else None,
        "input_tokens": (
            int(totals["input_token_total"]) if totals["token_calls"] else None
        ),
        "output_tokens": (
            int(totals["output_token_total"]) if totals["token_calls"] else None
        ),
        "token_calls": totals["token_calls"],
        "estimated_cost_calls": totals["estimated_calls"],
        "unavailable_cost_calls": totals["unavailable_calls"],
        "first_seen": totals["first_seen"].isoformat()
        if totals["first_seen"]
        else None,
        "last_seen": totals["last_seen"].isoformat() if totals["last_seen"] else None,
        "roles": totals["roles"],
        "costs": costs,
    }


BREAKDOWN_NUMERIC = (
    "count",
    "succeeded",
    "failed",
    "latency_total",
    "latency_count",
    "duration_total",
    "duration_count",
    "input_token_total",
    "output_token_total",
    "token_calls",
    "estimated_calls",
    "unavailable_calls",
)


def _normalise_field(field: str, value):
    if field == "provider_id" and value:
        return str(value)
    return value


def _row_key(row: dict, fields: tuple[str, ...]) -> tuple:
    return tuple(_normalise_field(field, row.get(field)) for field in fields)


def _raw_cost_map(queryset, fields: tuple[str, ...]) -> dict:
    costs: dict[tuple, dict] = defaultdict(dict)
    for row in (
        queryset.filter(cost_status=Trace.CostStatus.ESTIMATED)
        .values(*fields, "cost_currency")
        .annotate(amount=Sum("estimated_cost"), calls=Count("id"))
    ):
        costs[_row_key(row, fields)][row["cost_currency"] or ""] = {
            "amount": row["amount"] or Decimal("0"),
            "calls": _n(row["calls"]),
        }
    return costs


def _rollup_cost_map(queryset, fields: tuple[str, ...]) -> dict:
    costs: dict[tuple, dict] = defaultdict(dict)
    for row in (
        queryset.filter(estimated_calls__gt=0)
        .values(*fields, "cost_currency")
        .annotate(
            amount=Sum("estimated_cost"),
            call_total=Sum("estimated_calls"),
        )
    ):
        costs[_row_key(row, fields)][row["cost_currency"] or ""] = {
            "amount": row["amount"] or Decimal("0"),
            "calls": _n(row["call_total"]),
        }
    return costs


def _role_map(queryset, fields: tuple[str, ...], count_field: str) -> dict:
    roles: dict[tuple, dict[str, int]] = defaultdict(dict)
    for row in queryset.values(*fields, "role").annotate(
        count=Sum(count_field) if count_field != "id" else Count("id")
    ):
        roles[_row_key(row, fields)][row["role"]] = _n(row["count"])
    return roles


def _raw_breakdown(queryset, fields: tuple[str, ...]) -> list[dict]:
    rows = list(
        queryset.values(*fields).annotate(
            count=Count("id"),
            succeeded=Count("id", filter=Q(status=Trace.Status.SUCCEEDED)),
            failed=Count("id", filter=Q(status=Trace.Status.FAILED)),
            latency_total=Sum(Coalesce("provider_latency_ms", "duration_ms")),
            latency_count=Count(
                "id",
                filter=Q(provider_latency_ms__isnull=False)
                | Q(duration_ms__isnull=False),
            ),
            duration_total=Sum("duration_ms"),
            duration_count=Count("id", filter=Q(duration_ms__isnull=False)),
            input_token_total=Sum("input_tokens"),
            output_token_total=Sum("output_tokens"),
            token_calls=Count(
                "id",
                filter=Q(input_tokens__isnull=False)
                | Q(output_tokens__isnull=False),
            ),
            estimated_calls=Count(
                "id", filter=Q(cost_status=Trace.CostStatus.ESTIMATED)
            ),
            unavailable_calls=Count(
                "id", filter=Q(cost_status=Trace.CostStatus.UNAVAILABLE)
            ),
            last_seen=Max("started_at"),
        )
    )
    costs = _raw_cost_map(queryset, fields)
    roles = _role_map(queryset, fields, "id")
    for row in rows:
        key = _row_key(row, fields)
        row["_key"] = key
        row["_costs"] = costs.get(key, {})
        row["_roles"] = roles.get(key, {})
    return rows


def _rollup_breakdown(queryset, fields: tuple[str, ...]) -> list[dict]:
    if queryset is None:
        return []
    costs = _rollup_cost_map(queryset, fields)
    roles = _role_map(queryset, fields, "calls")
    rows = []
    for row in (
        queryset.values(*fields).annotate(
            count_total=Sum("calls"),
            success_total=Sum("calls", filter=Q(status=Trace.Status.SUCCEEDED)),
            failed_total=Sum("calls", filter=Q(status=Trace.Status.FAILED)),
            latency_total=Sum("latency_total_ms"),
            latency_samples=Sum("latency_count"),
            duration_total=Sum("duration_total_ms"),
            duration_samples=Sum("duration_count"),
            input_token_total=Sum("input_tokens"),
            output_token_total=Sum("output_tokens"),
            token_call_total=Sum("token_calls"),
            estimated_call_total=Sum("estimated_calls"),
            unavailable_call_total=Sum("unavailable_calls"),
            last_seen_at=Max("last_seen"),
        )
    ):
        row = {
            **row,
            "count": row.pop("count_total"),
            "succeeded": row.pop("success_total"),
            "failed": row.pop("failed_total"),
            "latency_count": row.pop("latency_samples"),
            "duration_count": row.pop("duration_samples"),
            "token_calls": row.pop("token_call_total"),
            "estimated_calls": row.pop("estimated_call_total"),
            "unavailable_calls": row.pop("unavailable_call_total"),
            "last_seen": row.pop("last_seen_at"),
        }
        key = _row_key(row, fields)
        row["_key"] = key
        row["_costs"] = costs.get(key, {})
        row["_roles"] = roles.get(key, {})
        rows.append(row)
    return rows


def _finalize_breakdown(rows: list[dict], fields: tuple[str, ...]) -> list[dict]:
    result = []
    for row in rows:
        latency = (
            row["latency_total"] / row["latency_count"]
            if row["latency_count"]
            else None
        )
        duration = (
            row["duration_total"] / row["duration_count"]
            if row["duration_count"]
            else None
        )
        estimated = _n(row["estimated_calls"])
        unavailable = _n(row["unavailable_calls"])
        costs = [
            {
                "currency": currency or "Unspecified",
                "amount": _money(item["amount"]),
                "calls": item["calls"],
            }
            for currency, item in sorted(row["_costs"].items())
        ]
        result.append(
            {
                **{field: _normalise_field(field, row.get(field)) for field in fields},
                "count": _n(row["count"]),
                "succeeded": _n(row["succeeded"]),
                "failed": _n(row["failed"]),
                "avg_latency_ms": round(latency, 2) if latency is not None else None,
                "avg_duration_ms": round(duration, 2) if duration is not None else None,
                "input_tokens": int(row["input_token_total"])
                if row["token_calls"]
                else None,
                "output_tokens": int(row["output_token_total"])
                if row["token_calls"]
                else None,
                "token_calls": _n(row["token_calls"]),
                "costs": costs,
                "estimated_calls": estimated,
                "cost_status": (
                    "unavailable"
                    if not estimated
                    else "partial"
                    if unavailable
                    else "estimated"
                ),
                "failure_rate": round(
                    _n(row["failed"]) / _n(row["count"]), 4
                )
                if row["count"]
                else 0,
                "roles": row["_roles"],
                "last_seen": row["last_seen"].isoformat()
                if row["last_seen"]
                else None,
            }
        )
    result.sort(
        key=lambda item: (
            -item["count"],
            item.get("provider_name") or "",
            item.get("model_id") or "",
        )
    )
    return result


def _merge_breakdown(
    raw_rows: list[dict], rollup_rows: list[dict], fields: tuple[str, ...]
) -> list[dict]:
    merged: dict[tuple, dict] = {}
    for row in [*raw_rows, *rollup_rows]:
        key = row["_key"]
        target = merged.setdefault(
            key,
            {
                **{field: _normalise_field(field, row.get(field)) for field in fields},
                **{name: 0 for name in BREAKDOWN_NUMERIC},
                "_costs": {},
                "_roles": {},
                "last_seen": None,
            },
        )
        for name in BREAKDOWN_NUMERIC:
            target[name] += row.get(name, 0) or 0
        if row.get("last_seen") and (
            target["last_seen"] is None or row["last_seen"] > target["last_seen"]
        ):
            target["last_seen"] = row["last_seen"]
        target["_costs"] = _merge_cost_maps(target["_costs"], row.get("_costs", {}))
        target["_roles"] = _merge_role_maps(target["_roles"], row.get("_roles", {}))
    return _finalize_breakdown(list(merged.values()), fields)


def _raw_trend(queryset) -> dict:
    rows = list(
        queryset.annotate(day=TruncDate("started_at"))
        .values("day")
        .annotate(
            count=Count("id"),
            succeeded=Count("id", filter=Q(status=Trace.Status.SUCCEEDED)),
            failed=Count("id", filter=Q(status=Trace.Status.FAILED)),
            latency_total=Sum(Coalesce("provider_latency_ms", "duration_ms")),
            latency_count=Count(
                "id",
                filter=Q(provider_latency_ms__isnull=False)
                | Q(duration_ms__isnull=False),
            ),
            input_token_total=Sum("input_tokens"),
            output_token_total=Sum("output_tokens"),
            token_calls=Count(
                "id",
                filter=Q(input_tokens__isnull=False)
                | Q(output_tokens__isnull=False),
            ),
        )
    )
    costs: dict[date, dict] = defaultdict(dict)
    for row in (
        queryset.filter(cost_status=Trace.CostStatus.ESTIMATED)
        .annotate(day=TruncDate("started_at"))
        .values("day", "cost_currency")
        .annotate(amount=Sum("estimated_cost"), calls=Count("id"))
    ):
        costs[row["day"]][row["cost_currency"] or ""] = {
            "amount": row["amount"] or Decimal("0"),
            "calls": _n(row["calls"]),
        }
    return {
        row["day"]: {
            "count": _n(row["count"]),
            "succeeded": _n(row["succeeded"]),
            "failed": _n(row["failed"]),
            "latency_total": float(row["latency_total"] or 0),
            "latency_count": _n(row["latency_count"]),
            "input_token_total": _n(row["input_token_total"]),
            "output_token_total": _n(row["output_token_total"]),
            "token_calls": _n(row["token_calls"]),
            "costs": costs.get(row["day"], {}),
        }
        for row in rows
    }


def _rollup_trend(queryset) -> dict:
    if queryset is None:
        return {}
    rows = []
    for row in (
        queryset.values("day").annotate(
            count_total=Sum("calls"),
            success_total=Sum("calls", filter=Q(status=Trace.Status.SUCCEEDED)),
            failed_total=Sum("calls", filter=Q(status=Trace.Status.FAILED)),
            latency_total=Sum("latency_total_ms"),
            latency_samples=Sum("latency_count"),
            input_token_total=Sum("input_tokens"),
            output_token_total=Sum("output_tokens"),
            token_call_total=Sum("token_calls"),
        )
    ):
        rows.append(
            {
                **row,
                "count": row.pop("count_total"),
                "succeeded": row.pop("success_total"),
                "failed": row.pop("failed_total"),
                "latency_count": row.pop("latency_samples"),
                "token_calls": row.pop("token_call_total"),
            }
        )
    costs: dict[date, dict] = defaultdict(dict)
    for row in (
        queryset.filter(estimated_calls__gt=0)
        .values("day", "cost_currency")
        .annotate(
            amount=Sum("estimated_cost"),
            call_total=Sum("estimated_calls"),
        )
    ):
        costs[row["day"]][row["cost_currency"] or ""] = {
            "amount": row["amount"] or Decimal("0"),
            "calls": _n(row["call_total"]),
        }
    return {
        row["day"]: {
            "count": _n(row["count"]),
            "succeeded": _n(row["succeeded"]),
            "failed": _n(row["failed"]),
            "latency_total": float(row["latency_total"] or 0),
            "latency_count": _n(row["latency_count"]),
            "input_token_total": _n(row["input_token_total"]),
            "output_token_total": _n(row["output_token_total"]),
            "token_calls": _n(row["token_calls"]),
            "costs": costs.get(row["day"], {}),
        }
        for row in rows
    }


def _trend(queryset, rollup_queryset, filters: TraceFilters) -> list[dict]:
    points = _raw_trend(queryset)
    merged = {day: dict(point) for day, point in points.items()}
    for day, point in _rollup_trend(rollup_queryset).items():
        target = merged.setdefault(
            day,
            {
                "count": 0,
                "succeeded": 0,
                "failed": 0,
                "latency_total": 0.0,
                "latency_count": 0,
                "input_token_total": 0,
                "output_token_total": 0,
                "token_calls": 0,
                "costs": {},
            },
        )
        for key in (
            "count",
            "succeeded",
            "failed",
            "latency_total",
            "latency_count",
            "input_token_total",
            "output_token_total",
            "token_calls",
        ):
            target[key] += point[key]
        target["costs"] = _merge_cost_maps(target["costs"], point["costs"])

    start = _local_date(filters.started_from) if filters.started_from else None
    end = _local_date(filters.started_to) if filters.started_to else None
    if start and end and (end - start).days <= 90:
        current = start
        while current <= end:
            merged.setdefault(
                current,
                {
                    "count": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "latency_total": 0.0,
                    "latency_count": 0,
                    "input_token_total": 0,
                    "output_token_total": 0,
                    "token_calls": 0,
                    "costs": {},
                },
            )
            current += timedelta(days=1)

    result = []
    for day in sorted(merged):
        point = merged[day]
        result.append(
            {
                "day": day.isoformat(),
                "count": point["count"],
                "succeeded": point["succeeded"],
                "failed": point["failed"],
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
                "costs": [
                    {
                        "currency": currency or "Unspecified",
                        "amount": _money(item["amount"]),
                        "calls": item["calls"],
                    }
                    for currency, item in sorted(point["costs"].items())
                ],
            }
        )
    return result


def _errors(queryset, rollup_queryset) -> list[dict]:
    counts = Counter()
    for row in (
        queryset.exclude(error__isnull=True)
        .values("error__category")
        .annotate(count=Count("id"))
    ):
        counts[row["error__category"] or "unknown"] += _n(row["count"])
    if rollup_queryset is not None:
        for error_counts in rollup_queryset.values_list("error_counts", flat=True):
            for category, count in (error_counts or {}).items():
                counts[str(category or "unknown")] += _n(count)
    return [
        {"category": category, "count": count}
        for category, count in counts.most_common(8)
    ]


def _facets(project) -> dict:
    providers = {}
    models = set()
    for row in (
        TraceRollup.objects.filter(project=project)
        .values("provider_id", "provider_name", "provider_kind")
        .distinct()
    ):
        provider_id = row["provider_id"] or None
        providers[(provider_id, row["provider_name"], row["provider_kind"])] = {
            "id": provider_id,
            "name": row["provider_name"],
            "kind": row["provider_kind"],
        }
    for row in (
        Trace.objects.filter(project=project)
        .values("provider_id", "provider_name", "provider_kind", "model_id")
        .distinct()
    ):
        provider_id = str(row["provider_id"]) if row["provider_id"] else None
        providers[(provider_id, row["provider_name"], row["provider_kind"])] = {
            "id": provider_id,
            "name": row["provider_name"],
            "kind": row["provider_kind"],
        }
        models.add(row["model_id"])
    for row in TraceRollup.objects.filter(project=project).values("model_id").distinct():
        models.add(row["model_id"])
    return {
        "providers": sorted(
            providers.values(), key=lambda item: (item["name"], item["kind"])
        ),
        "models": sorted(models),
    }


@dataclass(frozen=True)
class _Window:
    raw: object
    rollup: object | None
    through: date | None
    start: date | None
    end: date | None


def _apply_rollup_filters(queryset, filters: TraceFilters):
    if filters.provider_id:
        queryset = queryset.filter(provider_id=str(filters.provider_id))
    if filters.model_id:
        queryset = queryset.filter(model_id=filters.model_id)
    if filters.status:
        queryset = queryset.filter(status=filters.status)
    if filters.source:
        queryset = queryset.filter(source=filters.source)
    if filters.role:
        queryset = queryset.filter(role=filters.role)
    return queryset


def _window(project, filters: TraceFilters, traces):
    """Split the requested range into rolled-up days and live raw days."""
    state = TraceRollupState.objects.filter(project=project).first()
    if state is None:
        return _Window(raw=traces, rollup=None, through=None, start=None, end=None)

    through = state.through_day
    start = _local_date(filters.started_from) if filters.started_from else None
    end = _local_date(filters.started_to) if filters.started_to else through
    end = min(end, through)
    if filters.started_from and _local_time(filters.started_from) != dt_time.min:
        start = (start or through) + timedelta(days=1)
    if filters.started_to and _local_time(filters.started_to) != dt_time.max:
        end = (end or through) - timedelta(days=1)

    rollup = _apply_rollup_filters(
        TraceRollup.objects.filter(project=project, day__lte=end), filters
    )
    earliest = rollup.aggregate(first=Min("day"))["first"]
    if earliest is None:
        return _Window(raw=traces, rollup=None, through=through, start=None, end=None)

    if start is None or start < earliest:
        start = earliest
    if start > end:
        return _Window(raw=traces, rollup=None, through=through, start=None, end=None)

    rollup = rollup.filter(day__gte=start)
    raw = traces.exclude(
        started_at__gte=_day_start(start), started_at__lt=_next_day_start(end)
    )
    return _Window(
        raw=raw, rollup=rollup, through=through, start=start, end=end
    )


def dashboard(*, user, project_id, params) -> dict:
    project, filters, queryset = project_traces(
        user=user, project_id=project_id, params=params
    )
    window = _window(project, filters, queryset)

    totals = _finalize_totals(
        _merge_totals(_raw_totals(window.raw), _rollup_totals(window.rollup))
    )
    costs = totals.pop("costs")
    estimated_calls = totals["estimated_cost_calls"]
    unavailable_calls = totals["unavailable_cost_calls"]

    if not totals["calls"]:
        cost_status = "unavailable"
        cost_detail = "No model calls match these filters."
    elif not estimated_calls:
        cost_status = "unavailable"
        cost_detail = (
            "Estimated costs are unavailable: no pricing is configured and/or "
            "the provider did not report token usage."
        )
    elif unavailable_calls:
        cost_status = "partial"
        cost_detail = (
            f"Estimated for {estimated_calls} of {totals['calls']} calls; "
            f"{unavailable_calls} have no reliable pricing or token data."
        )
    else:
        cost_status = "estimated"
        cost_detail = (
            f"Estimated from configured token pricing for all {estimated_calls} calls."
        )

    model_fields = ("provider_id", "provider_name", "provider_kind", "model_id")
    provider_fields = ("provider_id", "provider_name", "provider_kind")
    models = _merge_breakdown(
        _raw_breakdown(window.raw, model_fields),
        _rollup_breakdown(window.rollup, model_fields),
        model_fields,
    )
    providers = _merge_breakdown(
        _raw_breakdown(window.raw, provider_fields),
        _rollup_breakdown(window.rollup, provider_fields),
        provider_fields,
    )

    slowest = list(
        queryset.select_related(
            "execution_result__execution",
            "evaluation_result__evaluation",
            "evaluation_result__model",
        )
        .exclude(duration_ms__isnull=True)
        .order_by("-duration_ms")[:8]
    )

    return {
        "project": str(project.pk),
        "totals": totals,
        "costs": costs,
        "cost_status": cost_status,
        "cost_detail": cost_detail,
        "models": models,
        "providers": providers,
        "trend": _trend(window.raw, window.rollup, filters),
        "errors": _errors(window.raw, window.rollup),
        "slowest": slowest,
        "facets": _facets(project),
        "rollups": {
            "enabled": bool(
                getattr(settings, "OBSERVABILITY_ROLLUP_ENABLED", True)
            ),
            "through": window.through.isoformat() if window.through else None,
            "from": window.start.isoformat() if window.start else None,
            "to": window.end.isoformat() if window.end else None,
            "retention_days": configured_retention_days(),
        },
        "telemetry": tracing_status(),
    }


def record_model_call(
    *,
    project,
    source: str,
    provider=None,
    provider_name: str,
    provider_kind: str,
    model_id: str,
    status: str,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    duration_ms: float | None = None,
    provider_latency_ms: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    error: dict | None = None,
    attributes: dict | None = None,
    request_text: str = "",
    response_text: str = "",
    otel_trace_id: str = "",
    role: str = Trace.Role.MODEL,
    execution_result=None,
    evaluation_result=None,
    spans: list[dict] | None = None,
) -> Trace | None:
    """Persist one model call and its span tree.

    Telemetry failures must never break a user-visible execution, so all errors
    are logged and swallowed.  Callers can still assert on the returned row in
    tests.
    """
    now = timezone.now()
    started_at = started_at or now
    ended_at = ended_at or now
    if duration_ms is None:
        duration_ms = max((ended_at - started_at).total_seconds() * 1000, 0.0)
    cost = estimate_cost(
        provider_kind=provider_kind,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    try:
        with transaction.atomic():
            trace = Trace.objects.create(
                project=project,
                source=source,
                role=role,
                execution_result=execution_result,
                evaluation_result=evaluation_result,
                provider=provider,
                provider_name=provider_name[:120],
                provider_kind=provider_kind[:16],
                model_id=model_id[:200],
                status=status,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=round(duration_ms, 2),
                provider_latency_ms=(
                    round(provider_latency_ms, 2)
                    if provider_latency_ms is not None
                    else None
                ),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=cost.amount,
                cost_currency=cost.currency,
                cost_status=cost.status,
                cost_detail=cost.detail[:240],
                error=error or None,
                attributes=attributes or {},
                request_text=(request_text or "")[:4000],
                response_text=(response_text or "")[:4000],
                otel_trace_id=(otel_trace_id or "")[:64],
            )
            created: dict[int, Span] = {}
            for index, spec in enumerate(spans or []):
                parent_index = spec.get("parent")
                parent = created.get(parent_index) if parent_index is not None else None
                created[index] = Span.objects.create(
                    trace=trace,
                    parent=parent,
                    sequence=index,
                    name=str(spec.get("name", "operation"))[:120],
                    kind=spec.get("kind", Span.Kind.INTERNAL),
                    status=spec.get("status", Span.Status.UNSET),
                    started_at=spec.get("started_at") or started_at,
                    ended_at=spec.get("ended_at") or ended_at,
                    duration_ms=(
                        round(spec["duration_ms"], 2)
                        if spec.get("duration_ms") is not None
                        else None
                    ),
                    attributes=spec.get("attributes") or {},
                    error=spec.get("error") or None,
                )

        if cost.amount is not None and execution_result is not None:
            from apps.playground.models import ExecutionResult

            ExecutionResult.objects.filter(pk=execution_result.pk).update(
                estimated_cost=cost.amount,
                cost_currency=cost.currency,
            )

        with bind_trace_id(str(trace.pk)):
            logger.info(
                "model call recorded source=%s role=%s provider=%s model=%s "
                "status=%s duration_ms=%s input_tokens=%s output_tokens=%s cost=%s",
                source,
                role,
                provider_name,
                model_id,
                status,
                round(duration_ms, 2),
                input_tokens,
                output_tokens,
                cost.amount if cost.amount is not None else "unavailable",
            )
        return trace
    except Exception:  # noqa: BLE001 - observability must not break executions
        logger.exception("A model call trace could not be recorded.")
        return None
