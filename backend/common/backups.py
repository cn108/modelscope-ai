"""Consistent PostgreSQL backups and retention (specification §9 hardening)."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError

BACKUP_PREFIX = "modelscope-"
BACKUP_SUFFIX = ".dump"


def backup_dir() -> Path:
    configured = getattr(settings, "BACKUP_DIR", "") or "backups"
    path = Path(configured)
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _database_settings() -> dict:
    db = settings.DATABASES["default"]
    if "postgresql" not in db["ENGINE"]:
        raise CommandError("Backups require the PostgreSQL database engine.")
    return db


def create_backup(*, label: str = "") -> Path:
    db = _database_settings()
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"-{label}" if label else ""
    destination = backup_dir() / f"{BACKUP_PREFIX}{stamp}{suffix}{BACKUP_SUFFIX}"
    env = os.environ.copy()
    env["PGPASSWORD"] = str(db.get("PASSWORD") or "")
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--file",
        str(destination),
        "--host",
        str(db.get("HOST") or "localhost"),
        "--port",
        str(db.get("PORT") or "5432"),
        "--username",
        str(db.get("USER") or ""),
        "--dbname",
        str(db.get("NAME") or ""),
    ]
    try:
        result = subprocess.run(
            command, env=env, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise CommandError(
            "pg_dump is not available in this runtime. Install the PostgreSQL client "
            "tools (postgresql-client) or run the backup from a host that has them."
        ) from exc
    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        # pg_dump stderr never contains the password because it is passed by env.
        detail = (result.stderr or "").strip()[:500]
        raise CommandError(f"pg_dump failed: {detail or 'unknown error'}")
    return destination


def apply_retention(*, days: int | None = None) -> list[Path]:
    retention = (
        getattr(settings, "BACKUP_RETENTION_DAYS", 30) if days is None else days
    )
    if retention <= 0:
        return []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention)
    removed: list[Path] = []
    for path in backup_dir().glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"):
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if modified < cutoff:
            path.unlink(missing_ok=True)
            removed.append(path)
    return removed
