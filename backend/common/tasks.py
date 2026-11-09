"""Scheduled operational tasks owned by the common app."""

from celery import shared_task

from common.backups import apply_retention, create_backup


@shared_task(name="common.backup_database")
def backup_database() -> dict:
    path = create_backup()
    removed = apply_retention()
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "removed": len(removed),
    }
