"""Workspace-scoped API for controlled AI security testing (M9)."""

from uuid import UUID

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.workspaces.permissions import UUID_RE
from common.pagination import DefaultPagination
from common.throttling import EvaluationCreateRateThrottle
from integrations.security_testing import registry

from .models import SecurityTestResult, SecurityTestRun
from .testing_serializers import (
    SecurityTestResultDetailSerializer,
    SecurityTestResultListSerializer,
    SecurityTestRunCreateSerializer,
    SecurityTestRunSerializer,
)
from .testing_services import (
    compare_runs,
    create_run,
    dashboard,
    enqueue_run,
    history,
    list_results,
    list_runs,
    rerun_run,
    result_for_user,
    run_for_user,
)


class SecurityTestCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(registry.catalog())


class ProjectSecurityTestingDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        data = dashboard(user=request.user, project_id=project_id)
        data["recent_runs"] = SecurityTestRunSerializer(
            data["recent_runs"], many=True
        ).data
        data["recent_failures"] = SecurityTestResultListSerializer(
            data["recent_failures"], many=True
        ).data
        return Response(data)


class ProjectSecurityTestRunView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EvaluationCreateRateThrottle]

    def get(self, request, project_id):
        rows = list_runs(
            user=request.user,
            project_id=project_id,
            status=request.query_params.get("status"),
        )
        return Response(SecurityTestRunSerializer(rows, many=True).data)

    def post(self, request, project_id):
        serializer = SecurityTestRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = create_run(
            actor=request.user,
            project_id=project_id,
            validated_data=serializer.validated_data,
        )
        run = enqueue_run(run)
        run = run_for_user(request.user, run.pk)
        return Response(
            SecurityTestRunSerializer(run).data,
            status=status.HTTP_201_CREATED,
        )


def _comparison_payload(data: dict) -> dict:
    data["baseline"] = SecurityTestRunSerializer(data.pop("baseline")).data
    data["current"] = SecurityTestRunSerializer(data.pop("current")).data
    for key in ("new_failures", "resolved_failures", "persisting", "changed"):
        data[key] = [
            {
                "case_key": item["case_key"],
                "model": item["model"],
                "baseline": SecurityTestResultDetailSerializer(
                    item["baseline"]
                ).data
                if item["baseline"] is not None
                else None,
                "current": SecurityTestResultDetailSerializer(item["current"]).data
                if item["current"] is not None
                else None,
            }
            for item in data[key]
        ]
    return data


class ProjectSecurityTestCompareView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        baseline_id = request.query_params.get("baseline")
        current_id = request.query_params.get("current")
        if not baseline_id or not current_id:
            raise ValidationError(
                {
                    "baseline": "Provide baseline and current run ids.",
                    "current": "Provide baseline and current run ids.",
                }
            )
        for field, value in (("baseline", baseline_id), ("current", current_id)):
            try:
                UUID(str(value))
            except (TypeError, ValueError) as exc:
                raise ValidationError({field: "Invalid security test run id."}) from exc
        data = compare_runs(
            user=request.user,
            project_id=project_id,
            baseline_id=baseline_id,
            current_id=current_id,
        )
        return Response(_comparison_payload(data))


class ProjectSecurityTestHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        rows = history(
            user=request.user,
            project_id=project_id,
            model_id=request.query_params.get("model"),
            provider_id=request.query_params.get("provider"),
        )
        return Response(
            [
                {
                    "run": str(row.run_id),
                    "run_status": row.run.status,
                    "run_created_at": row.run.created_at,
                    "model": str(row.pk),
                    "provider": str(row.provider_id) if row.provider_id else None,
                    "provider_name": row.provider_name,
                    "provider_kind": row.provider_kind,
                    "model_id": row.model_id,
                    "summary": row.summary,
                }
                for row in rows
            ]
        )


class SecurityTestRunViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE
    serializer_class = SecurityTestRunSerializer

    def get_queryset(self):
        return SecurityTestRun.objects.filter(
            project__workspace__memberships__user=self.request.user
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        run = run_for_user(request.user, kwargs["pk"])
        return Response(SecurityTestRunSerializer(run).data)

    @action(detail=True, methods=["get"], url_path="results")
    def results(self, request, pk=None):
        run = run_for_user(request.user, pk)
        rows = list_results(
            user=request.user,
            run_id=run.pk,
            model_id=request.query_params.get("model"),
            category=request.query_params.get("category"),
            verdict=request.query_params.get("verdict"),
            status=request.query_params.get("status"),
        )
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(
                SecurityTestResultListSerializer(page, many=True).data
            )
        return Response(SecurityTestResultListSerializer(rows, many=True).data)

    @action(detail=True, methods=["post"], url_path="rerun")
    def rerun(self, request, pk=None):
        run = rerun_run(actor=request.user, run_id=pk)
        run = run_for_user(request.user, run.pk)
        return Response(
            SecurityTestRunSerializer(run).data,
            status=status.HTTP_201_CREATED,
        )


class SecurityTestResultViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE
    serializer_class = SecurityTestResultDetailSerializer

    def get_queryset(self):
        return SecurityTestResult.objects.filter(
            run__project__workspace__memberships__user=self.request.user
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        result = result_for_user(request.user, kwargs["pk"])
        return Response(SecurityTestResultDetailSerializer(result).data)
