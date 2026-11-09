"""Versioned API routing. Base path /api/v1/ per specification §8."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.playground.views import ExecutionViewSet
from apps.datasets.views import DatasetRecordViewSet, DatasetViewSet
from apps.evaluations.views import EvaluationMetricCatalogView, EvaluationViewSet
from apps.observability.views import (
    ProjectObservabilityView,
    ProjectTraceListView,
    TraceDetailView,
)
from apps.security.views import (
    ProjectSecurityCompareView,
    ProjectSecurityDashboardView,
    ProjectSecurityFindingView,
    ProjectSecurityScanView,
    SecurityCheckCatalogView,
    SecurityFindingViewSet,
    SecurityScanViewSet,
)
from apps.analytics.views import (
    AnalyticsReportDetailView,
    AnalyticsReportExportView,
    ProjectAnalyticsReportView,
    ProjectAnalyticsView,
    ProjectModelPerformanceView,
)
from apps.projects.views import ProjectViewSet
from apps.prompts.views import PromptViewSet
from apps.providers.views import ProviderViewSet
from apps.workspaces.views import WorkspaceViewSet
from common.health.views import HealthView, WorkerHealthView

router = DefaultRouter()
router.register("workspaces", WorkspaceViewSet, basename="workspace")
router.register("projects", ProjectViewSet, basename="project")
router.register("providers", ProviderViewSet, basename="provider")
router.register("prompts", PromptViewSet, basename="prompt")
router.register("executions", ExecutionViewSet, basename="execution")
router.register("datasets", DatasetViewSet, basename="dataset")
router.register("dataset-records", DatasetRecordViewSet, basename="dataset-record")
router.register("evaluations", EvaluationViewSet, basename="evaluation")
router.register("security-scans", SecurityScanViewSet, basename="security-scan")
router.register("security-findings", SecurityFindingViewSet, basename="security-finding")


def api_not_found(request, exception=None):
    """Keep the JSON error envelope consistent even for unrouted /api/ paths (§8)."""
    return JsonResponse(
        {
            "error": {
                "code": "not_found",
                "message": "Endpoint not found.",
                "details": None,
            }
        },
        status=404,
    )


api_v1_patterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("health/worker/", WorkerHealthView.as_view(), name="health-worker"),
    path(
        "evaluation-metrics/",
        EvaluationMetricCatalogView.as_view(),
        name="evaluation-metrics",
    ),
    path(
        "projects/<uuid:project_id>/analytics/",
        ProjectAnalyticsView.as_view(),
        name="project-analytics",
    ),
    path(
        "projects/<uuid:project_id>/analytics/models/",
        ProjectModelPerformanceView.as_view(),
        name="project-model-performance",
    ),
    path(
        "projects/<uuid:project_id>/analytics/reports/",
        ProjectAnalyticsReportView.as_view(),
        name="project-analytics-reports",
    ),
    path(
        "analytics-reports/<uuid:report_id>/",
        AnalyticsReportDetailView.as_view(),
        name="analytics-report",
    ),
    path(
        "analytics-reports/<uuid:report_id>/export/",
        AnalyticsReportExportView.as_view(),
        name="analytics-report-export",
    ),
    path(
        "projects/<uuid:project_id>/observability/",
        ProjectObservabilityView.as_view(),
        name="project-observability",
    ),
    path(
        "projects/<uuid:project_id>/observability/traces/",
        ProjectTraceListView.as_view(),
        name="project-observability-traces",
    ),
    path(
        "observability/traces/<uuid:trace_id>/",
        TraceDetailView.as_view(),
        name="observability-trace",
    ),
    path(
        "security/checks/",
        SecurityCheckCatalogView.as_view(),
        name="security-checks",
    ),
    path(
        "projects/<uuid:project_id>/security/",
        ProjectSecurityDashboardView.as_view(),
        name="project-security",
    ),
    path(
        "projects/<uuid:project_id>/security/scans/",
        ProjectSecurityScanView.as_view(),
        name="project-security-scans",
    ),
    path(
        "projects/<uuid:project_id>/security/findings/",
        ProjectSecurityFindingView.as_view(),
        name="project-security-findings",
    ),
    path(
        "projects/<uuid:project_id>/security/compare/",
        ProjectSecurityCompareView.as_view(),
        name="project-security-compare",
    ),
    path("auth/", include("apps.accounts.urls")),
    path("", include(router.urls)),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "v1"))),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

handler404 = "config.urls.api_not_found"
