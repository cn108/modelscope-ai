"""Celery entry point for controlled security scans."""

from celery import shared_task


@shared_task(bind=True, name="apps.security.run_scan")
def run_security_scan(self, scan_id: str) -> dict:
    from .services import execute_scan

    task_id = getattr(self.request, "id", "") or ""
    return execute_scan(scan_id=scan_id, task_id=task_id)
