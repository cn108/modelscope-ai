"""Local development settings.

If no PostgreSQL server is reachable you may set DATABASE_ENGINE=sqlite for
unit-test convenience only; integration verification targets PostgreSQL (§7).
"""

from .base import *  # noqa: F401,F403
from .base import DATABASES, SECRET_KEY, env, env_bool

DEBUG = env_bool("DJANGO_DEBUG", True)

if not SECRET_KEY:
    # Dev-only fallback so onboarding works before generating real secrets.
    import warnings

    warnings.warn("DJANGO_SECRET_KEY unset; using an insecure development key.")

    SECRET_KEY = "dev-insecure-key-do-not-use-in-production"

if env("DATABASE_ENGINE", "postgresql") == "sqlite":
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
