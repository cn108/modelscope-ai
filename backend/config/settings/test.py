"""Deterministic unit-test settings: SQLite + eager Celery + local-memory cache.

Integration verification against real PostgreSQL/Redis runs in Docker Compose
(see README); these settings only make pure-logic smoke tests hermetic.
"""

from .base import *  # noqa: F401,F403
from .base import DATABASES, CACHES

SECRET_KEY = "test-only-key-not-a-real-secret-0123456789abcdef"
DEBUG = False
ALLOWED_HOSTS = ["testserver"]

DATABASES["default"] = {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": ":memory:",
}

CACHES["default"] = {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
}

# Celery: execute tasks inline; no broker needed for unit tests.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

PROVIDER_SECRET_KEYS = []
