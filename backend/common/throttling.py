"""Rate limits for authentication and model-call surfaces (specification §11).

Rates are configurable through ``DEFAULT_THROTTLE_RATES``. Login is keyed by
both client address and a hash of the submitted email so one address cannot
rotate accounts indefinitely, and model-call limits are per authenticated user.
"""

from __future__ import annotations

import hashlib

from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    scope = "login"

    def get_cache_key(self, request, view):
        email = str(request.data.get("email", "")).strip().lower()
        digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
        return f"throttle_login_{self.get_ident(request)}_{digest}"


class ModelCallRateThrottle(UserRateThrottle):
    scope = "model_call"


class EvaluationCreateRateThrottle(UserRateThrottle):
    scope = "evaluation_create"
