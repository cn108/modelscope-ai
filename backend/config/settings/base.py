"""Shared base settings for all environments.

Conventions enforced here per specification:
- PostgreSQL is the source of truth (§3, §4).
- UUID primary keys and UTC timestamps (§7).
- No secrets in source control; everything sensitive comes from the environment (§11).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BASE_DIR.parent

# Load .env from the repository root if present (never committed).
load_dotenv(REPO_ROOT / ".env")


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(key: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(key, default).split(",") if item.strip()]


# --- Core ---------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY")  # required; validated in dev/prod modules
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"  # apps override with UUID PKs (§7)
USE_TZ = True
TIME_ZONE = "UTC"

LANGUAGE_CODE = "en-us"

# Safe, public product metadata for the Settings → About panel.
APP_VERSION = env("APP_VERSION", "1.0.0")
ENVIRONMENT = env(
    "DJANGO_ENVIRONMENT", "development" if env_bool("DJANGO_DEBUG", True) else "production"
)
SUPPORT_URL = env("SUPPORT_URL", "")
DOCUMENTATION_URL = env("DOCUMENTATION_URL", "")

# --- Apps ---------------------------------------------------------------
# Milestone 1 ships the foundation only; feature apps under apps/ are added
# starting Milestone 2 (identity/tenancy) per the roadmap in §13.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    # local
    "common",
    "apps.accounts",
    "apps.workspaces",
    "apps.projects",
    "apps.providers",
    "apps.prompts",
    "apps.playground",
    "apps.datasets",
    "apps.evaluations",
    "apps.observability",
    "apps.security",
    "apps.analytics",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "common.middleware.ContentSecurityPolicyMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database (§3, §7): PostgreSQL is the source of truth ---------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "modelscope"),
        "USER": env("POSTGRES_USER", "modelscope"),
        "PASSWORD": env("POSTGRES_PASSWORD", ""),
        "HOST": env("POSTGRES_HOST", "db"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

# --- Cache / broker: Redis (§4) — never the only store for results ------
REDIS_URL = env("REDIS_URL", "redis://redis:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# --- Celery ---------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TRACK_STARTED = True
CELERY_TIMEZONE = "UTC"

# --- Auth: custom user + JWT (§11) ----------------------------------------
AUTH_USER_MODEL = "accounts.User"

PASSWORD_HASHERS = [
    # Argon2 where configured (§11); fallbacks keep old hashes verifiable.
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

from datetime import timedelta  # noqa: E402  (settings-local import for JWT lifetimes)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    # SIGNING_KEY intentionally omitted: SimpleJWT defaults to SECRET_KEY at
    # request time, so environment-specific SECRET_KEY overrides are honoured.
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# --- API / DRF ------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",  # endpoints opt in explicitly (§11)
    ],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.DefaultPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "login": env("RATE_LIMIT_LOGIN", "10/min"),
        "model_call": env("RATE_LIMIT_MODEL_CALL", "30/min"),
        "evaluation_create": env("RATE_LIMIT_EVALUATION_CREATE", "30/hour"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ModelScope AI API",
    "DESCRIPTION": "AI Model Evaluation & Observability Platform — versioned REST API.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}

# CORS — explicit allow-list only (§11)
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:4200,http://localhost:8080"
)
CORS_ALLOW_CREDENTIALS = False
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:4200,http://localhost:8080"
)

# --- Provider secret encryption (§11) --------------------------------------
# Key lives outside DB and source control; rotate by adding a new key and
# re-encrypting (see docs/adr/ADR-0003-secret-encryption.md).
PROVIDER_SECRET_KEYS = env_list("PROVIDER_SECRET_KEYS")  # Fernet keys, current first

# Provider transport hardening: a single call is bounded, transient failures
# are retried with exponential backoff, and each worker process caps in-flight
# provider calls. Concurrency is per process; scale workers for more throughput.
PROVIDER_TIMEOUT_SECONDS = float(env("PROVIDER_TIMEOUT_SECONDS", "60") or 60)
PROVIDER_MAX_RETRIES = int(env("PROVIDER_MAX_RETRIES", "2") or 0)
PROVIDER_RETRY_BACKOFF_SECONDS = float(env("PROVIDER_RETRY_BACKOFF_SECONDS", "0.25") or 0)
PROVIDER_MAX_CONCURRENCY = int(env("PROVIDER_MAX_CONCURRENCY", "8") or 8)
PROVIDER_CONCURRENCY_WAIT_SECONDS = float(
    env("PROVIDER_CONCURRENCY_WAIT_SECONDS", "5") or 5
)

# --- Evaluation metrics -----------------------------------------------------
# Judge-based metrics (DeepEval) need a configured provider/model to score and
# are hidden entirely when this flag is off or DeepEval is not installed.
EVALUATION_JUDGE_METRICS_ENABLED = env_bool("EVALUATION_JUDGE_METRICS_ENABLED", True)

# --- Observability / OpenTelemetry (M6) ------------------------------------
# Database traces always record. OTel spans are created in-process; an OTLP/HTTP
# endpoint is optional and only exports when explicitly configured.
OTEL_TRACING_ENABLED = env_bool("OTEL_TRACING_ENABLED", True)
OTEL_SERVICE_NAME = env("OTEL_SERVICE_NAME", "modelscope-ai")
OTEL_EXPORTER_OTLP_ENDPOINT = env("OTEL_EXPORTER_OTLP_ENDPOINT")

# Explicit per-model pricing, JSON keyed by "<provider kind>:<model id>".
# Costs stay unavailable unless this is configured and the provider reports
# token usage; see integrations/telemetry/pricing.py.
EXECUTION_PRICING = env("EXECUTION_PRICING", "")

# Completed days are aggregated into TraceRollup so the dashboard does not scan
# the entire raw trace history. 0 keeps raw traces forever (the safe default);
# set a positive number to delete raw traces after that many complete days.
# Rollups are retained regardless of raw-trace retention.
OBSERVABILITY_ROLLUP_ENABLED = env_bool("OBSERVABILITY_ROLLUP_ENABLED", True)
OBSERVABILITY_TRACE_RETENTION_DAYS = int(
    env("OBSERVABILITY_TRACE_RETENTION_DAYS", "0") or 0
)

# Security scans are explicit and asynchronous. A scan is capped so a very large
# dataset cannot occupy a worker indefinitely; the limit is visible in the API.
SECURITY_MAX_SCAN_ITEMS = int(env("SECURITY_MAX_SCAN_ITEMS", "10000") or 10000)

# AI security testing is bounded so an authorised workspace member cannot turn
# the reviewed case catalog into an unbounded model-call or cost surface.
SECURITY_TEST_MAX_MODELS = int(env("SECURITY_TEST_MAX_MODELS", "5") or 5)
SECURITY_TEST_MAX_RESULTS = int(env("SECURITY_TEST_MAX_RESULTS", "120") or 120)

BACKUP_ENABLED = env_bool("BACKUP_ENABLED", False)
BACKUP_DIR = env("BACKUP_DIR", "backups")
BACKUP_RETENTION_DAYS = int(env("BACKUP_RETENTION_DAYS", "30") or 30)

CELERY_BEAT_SCHEDULE = {}
if OBSERVABILITY_ROLLUP_ENABLED or BACKUP_ENABLED:
    from celery.schedules import crontab

    if OBSERVABILITY_ROLLUP_ENABLED:
        CELERY_BEAT_SCHEDULE["observability-maintenance"] = {
            "task": "apps.observability.maintain",
            "schedule": crontab(minute=15, hour=1),
        }
    if BACKUP_ENABLED:
        CELERY_BEAT_SCHEDULE["database-backup"] = {
            "task": "common.backup_database",
            "schedule": crontab(minute=30, hour=2),
        }

# --- Security hardening (§11) ----------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Request size limits (§11)
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

# --- Static -----------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Logging: structured-ish with correlation id support (§10) --------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "trace_id": {"()": "integrations.telemetry.logging.TraceIdFilter"},
    },
    "formatters": {
        "simple": {
            "format": "%(levelname)s %(asctime)s %(name)s trace=%(trace_id)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["trace_id"],
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
