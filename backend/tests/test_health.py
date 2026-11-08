from django.urls import reverse
from rest_framework.test import APIClient


def test_health_reports_database_ok(db):
    client = APIClient()
    resp = client.get(reverse("v1:health"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"]["status"] == "ok"


def test_worker_health_degrades_without_broker(monkeypatch):
    """Honesty rule: unavailable dependency must degrade, never fake ok."""
    import common.health.views as views

    monkeypatch.setattr(views, "_check_redis", lambda: {"status": "error", "detail": "unreachable"})
    client = APIClient()
    resp = client.get(reverse("v1:health-worker"))
    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"


def test_worker_health_celery_roundtrip_eager():
    """With CELERY_TASK_ALWAYS_EAGER the probe executes in-process."""
    client = APIClient()
    resp = client.get(reverse("v1:health-worker") + "?probe=1")
    body = resp.json()
    assert body["worker"]["echo"] == "ping"
