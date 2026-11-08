"""Production/container settings. Fails fast on missing secrets (§11)."""

from django.core.exceptions import ImproperlyConfigured

from .base import env, env_bool  # noqa: F401
from .base import *  # noqa: F401,F403
from .base import SECRET_KEY

DEBUG = False

if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
