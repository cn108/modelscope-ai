"""Workspace-scoped analytics and reporting API (Milestone 8)."""

from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .reporting import (
    create_report,
    list_reports,
    report_csv,
    report_for_user,
    report_pdf,
)
from .serializers import (
    AnalyticsReportCreateSerializer,
    AnalyticsReportDetailSerializer,
    AnalyticsReportListSerializer,
)
from .services import dashboard, model_performance

EXPORT_FORMATS = {"csv", "pdf"}


class ProjectAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        return Response(
            dashboard(
                user=request.user,
                project_id=project_id,
                params=request.query_params,
            )
        )


class ProjectModelPerformanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        return Response(
            model_performance(
                user=request.user,
                project_id=project_id,
                params=request.query_params,
            )
        )


class ProjectAnalyticsReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        rows = list_reports(user=request.user, project_id=project_id)
        return Response(AnalyticsReportListSerializer(rows, many=True).data)

    def post(self, request, project_id):
        serializer = AnalyticsReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        validated["from"] = validated.pop("from_date", None)
        validated["to"] = validated.pop("to_date", None)
        report = create_report(
            actor=request.user,
            project_id=project_id,
            validated_data=validated,
        )
        return Response(
            AnalyticsReportDetailSerializer(report).data,
            status=status.HTTP_201_CREATED,
        )


class AnalyticsReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, report_id):
        report = report_for_user(request.user, report_id)
        return Response(AnalyticsReportDetailSerializer(report).data)


class AnalyticsReportExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, report_id):
        # ``format`` is reserved by DRF's content-negotiation override, so the
        # export selector intentionally uses ``export_format`` instead.
        export_format = (
            request.query_params.get("export_format") or ""
        ).strip().lower()
        if export_format not in EXPORT_FORMATS:
            raise ValidationError(
                {"export_format": "Choose csv or pdf for the report export."}
            )
        report = report_for_user(request.user, report_id)
        if export_format == "csv":
            payload = report_csv(report)
            content_type = "text/csv; charset=utf-8"
        else:
            payload = report_pdf(report)
            content_type = "application/pdf"
        response = HttpResponse(payload, content_type=content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="analytics-report-{report.pk}.{export_format}"'
        )
        response["X-Report-Snapshot"] = report.created_at.isoformat()
        return response
