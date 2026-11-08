"""Versioned API routing. Base path /api/v1/ per specification §8."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from common.health.views import HealthView, WorkerHealthView


def api_not_found(request, exception=None):
    """Keep the JSON error envelope consistent even for unrouted /api/ paths (§8)."""
    return JsonResponse(
        {"error": {"code": "not_found", "message": "Endpoint not found.", "details": None}},
        status=404,
    )

api_v1_patterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("health/worker/", WorkerHealthView.as_view(), name="health-worker"),
    # Feature routes are added from Milestone 2 onward:
    # path("auth/", include("apps.accounts.urls")),
    # path("workspaces/", include("apps.workspaces.urls")),
    # ...
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "v1"))),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

handler404 = "config.urls.api_not_found"
