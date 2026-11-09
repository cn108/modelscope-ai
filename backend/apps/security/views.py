"""Workspace-scoped security API: scans, findings, review and dashboard."""

from uuid import UUID

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.workspaces.permissions import UUID_RE
from common.pagination import DefaultPagination
from integrations.security.registry import catalog

from .models import SecurityFinding, SecurityScan
from .serializers import (
    SecurityFindingSerializer,
    SecurityFindingUpdateSerializer,
    SecurityScanCreateSerializer,
    SecurityScanSerializer,
)
from .services import (
    compare_scans,
    create_scan,
    dashboard,
    enqueue_scan,
    finding_for_user,
    list_findings,
    list_scans,
    rerun_scan,
    scan_for_user,
    update_finding,
)


class SecurityCheckCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(catalog())


class ProjectSecurityDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        data = dashboard(user=request.user, project_id=project_id)
        data["recent_scans"] = SecurityScanSerializer(
            data["recent_scans"], many=True
        ).data
        data["recent_findings"] = SecurityFindingSerializer(
            data["recent_findings"], many=True
        ).data
        return Response(data)


class ProjectSecurityScanView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        rows = list_scans(
            user=request.user,
            project_id=project_id,
            status=request.query_params.get("status"),
        )
        return Response(SecurityScanSerializer(rows, many=True).data)

    def post(self, request, project_id):
        serializer = SecurityScanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scan = create_scan(
            actor=request.user,
            project_id=project_id,
            validated_data=serializer.validated_data,
        )
        scan = enqueue_scan(scan)
        scan = scan_for_user(request.user, scan.pk)
        return Response(
            SecurityScanSerializer(scan).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectSecurityCompareView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        baseline_id = request.query_params.get("baseline")
        current_id = request.query_params.get("current")
        if not baseline_id or not current_id:
            raise ValidationError(
                {
                    "baseline": "Provide baseline and current scan ids.",
                    "current": "Provide baseline and current scan ids.",
                }
            )
        for field, value in (("baseline", baseline_id), ("current", current_id)):
            try:
                UUID(str(value))
            except (TypeError, ValueError) as exc:
                raise ValidationError({field: "Invalid security scan id."}) from exc
        data = compare_scans(
            user=request.user,
            project_id=project_id,
            baseline_id=baseline_id,
            current_id=current_id,
        )
        data["baseline"] = SecurityScanSerializer(data.pop("baseline_scan")).data
        data["current"] = SecurityScanSerializer(data.pop("current_scan")).data
        data["new_findings"] = SecurityFindingSerializer(
            data["new_findings"], many=True
        ).data
        data["resolved_findings"] = SecurityFindingSerializer(
            data["resolved_findings"], many=True
        ).data
        data["persisting"] = [
            {
                "baseline": SecurityFindingSerializer(item["baseline"]).data,
                "current": SecurityFindingSerializer(item["current"]).data,
                "changed_fields": item["changed_fields"],
            }
            for item in data["persisting"]
        ]
        return Response(data)


class ProjectSecurityFindingView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = DefaultPagination

    def get(self, request, project_id):
        rows = list_findings(
            user=request.user,
            project_id=project_id,
            status=request.query_params.get("status"),
            severity=request.query_params.get("severity"),
            category=request.query_params.get("category"),
            check=request.query_params.get("check"),
            scan_id=request.query_params.get("scan"),
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(rows, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(
                SecurityFindingSerializer(page, many=True).data
            )
        return Response(SecurityFindingSerializer(rows, many=True).data)


class SecurityScanViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE
    serializer_class = SecurityScanSerializer

    def get_queryset(self):
        return SecurityScan.objects.filter(
            project__workspace__memberships__user=self.request.user
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        scan = scan_for_user(request.user, kwargs["pk"])
        return Response(SecurityScanSerializer(scan).data)

    @action(detail=True, methods=["get"], url_path="findings")
    def findings(self, request, pk=None):
        scan = scan_for_user(request.user, pk)
        rows = list_findings(
            user=request.user,
            project_id=scan.project_id,
            status=request.query_params.get("status"),
            severity=request.query_params.get("severity"),
            category=request.query_params.get("category"),
            check=request.query_params.get("check"),
            scan_id=scan.pk,
        )
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(
                SecurityFindingSerializer(page, many=True).data
            )
        return Response(SecurityFindingSerializer(rows, many=True).data)

    @action(detail=True, methods=["post"], url_path="rerun")
    def rerun(self, request, pk=None):
        scan = rerun_scan(actor=request.user, scan_id=pk)
        scan = scan_for_user(request.user, scan.pk)
        return Response(
            SecurityScanSerializer(scan).data, status=status.HTTP_201_CREATED
        )


class SecurityFindingViewSet(
    mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE
    serializer_class = SecurityFindingSerializer

    def get_queryset(self):
        return SecurityFinding.objects.filter(
            project__workspace__memberships__user=self.request.user
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        finding = finding_for_user(request.user, kwargs["pk"])
        return Response(SecurityFindingSerializer(finding).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        finding_for_user(request.user, kwargs["pk"])
        serializer = SecurityFindingUpdateSerializer(
            data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        finding = update_finding(
            actor=request.user,
            finding_id=kwargs["pk"],
            validated_data=serializer.validated_data,
        )
        return Response(SecurityFindingSerializer(finding).data)
