"""Celery maintenance for trace rollups and retention."""

from __future__ import annotations

from datetime import date

from celery import shared_task

from apps.observability import rollups


@shared_task(name="apps.observability.rollup_traces")
def rollup_traces(through_day: str | None = None) -> dict:
    parsed = date.fromisoformat(through_day) if through_day else None
    return rollups.rollup_all(through_day=parsed)


@shared_task(name="apps.observability.purge_traces")
def purge_traces() -> dict:
    return rollups.purge_old_traces()


@shared_task(name="apps.observability.maintain")
def maintain() -> dict:
    """Daily entry point: roll up complete days, then apply retention."""
    return {
        "rollups": rollups.rollup_all(),
        "retention": rollups.purge_old_traces(),
    }
