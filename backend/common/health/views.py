"""Health endpoints (acceptance checklist section 17).

- /api/v1/health/         : liveness + database connectivity check.
- /api/v1/health/worker/  : Redis broker ping (and optional Celery round trip).

Never report a component as healthy when it could not be verified; unavailable
checks are reported explicitly (specification section 1 honesty rule).
"""

import django.db
from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


def _check_database() -> dict:
    try:
        with django.db.connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        engine = settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1]
        return {"status": "ok", "engine": engine}
    except Exception as exc:  # noqa: BLE001 - report, never mask
        return {"status": "error", "detail": str(exc)}


def _check_redis() -> dict:
    try:
        import redis

        client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2)
        client.ping()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": str(exc)}


class HealthView(APIView):
    """Liveness/readiness: process up and database reachable."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        db = _check_database()
        overall = "ok" if db["status"] == "ok" else "degraded"
        return Response(
            {"status": overall, "service": "modelscope-api", "database": db},
            status=200 if overall == "ok" else 503,
        )


class WorkerHealthView(APIView):
    """Broker connectivity, plus an optional live Celery round trip.

    With ?probe=1 the view enqueues common.debug_echo and waits briefly for the
    result - requires a running worker; failures are reported honestly.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        broker = _check_redis()
        payload = {"status": "ok" if broker["status"] == "ok" else "degraded",
                   "broker": broker}

        if request.query_params.get("probe") == "1":
            payload["worker"] = self._celery_round_trip()
            if payload["worker"]["status"] != "ok":
                payload["status"] = "degraded"

        code = 200 if payload["status"] == "ok" else 503
        return Response(payload, status=code)

    @staticmethod
    def _celery_round_trip() -> dict:
        try:
            from config.celery import debug_echo

            result = debug_echo.delay("ping")
            value = result.get(timeout=5, propagate=True)
            return {"status": "ok", "echo": value}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "detail": str(exc)}
