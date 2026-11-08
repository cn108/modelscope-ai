"""Celery application (specification §5: config/celery.py)."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("modelscope_ai")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, name="common.debug_echo")
def debug_echo(self, message: str) -> str:
    """Round-trip task used by health checks and CI verification."""
    return message
