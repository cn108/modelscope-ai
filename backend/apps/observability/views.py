"""Workspace-scoped observability API: summary, trace list and trace detail."""

from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.observability.serializers import (
    TraceDetailSerializer,
    TraceListSerializer,
)
from apps.observability.services import (
    dashboard,
    trace_for_user,
    trace_queryset,
)
from common.pagination import DefaultPagination


class ProjectObservabilityView(APIView):
    """Dashboard aggregates for one project; filters are query parameters."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        data = dashboard(
            user=request.user, project_id=project_id, params=request.query_params
        )
        data["slowest"] = TraceListSerializer(
            data.pop("slowest"), many=True
        ).data
        return Response(data)


class ProjectTraceListView(GenericAPIView):
    """Paginated trace explorer, newest first, with the same filters."""

    permission_classes = [IsAuthenticated]
    serializer_class = TraceListSerializer
    pagination_class = DefaultPagination

    def get(self, request, project_id):
        queryset = trace_queryset(
            user=request.user, project_id=project_id, params=request.query_params
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(
                TraceListSerializer(page, many=True).data
            )
        return Response(TraceListSerializer(queryset, many=True).data)


class TraceDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TraceDetailSerializer

    def get(self, request, trace_id):
        trace = trace_for_user(request.user, trace_id)
        return Response(TraceDetailSerializer(trace).data)
