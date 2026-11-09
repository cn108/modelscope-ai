from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.playground.models import Execution
from apps.playground.serializers import ExecutionSerializer
from apps.playground.services import execution_for_user, rerun_execution
from apps.workspaces.permissions import UUID_RE


class ExecutionViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE
    serializer_class = ExecutionSerializer

    def get_queryset(self):
        return Execution.objects.filter(
            project__workspace__memberships__user=self.request.user
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        execution = execution_for_user(request.user, kwargs["pk"])
        return Response(ExecutionSerializer(execution).data)

    @action(detail=True, methods=["post"], url_path="rerun")
    def rerun(self, request, pk=None):
        execution = rerun_execution(actor=request.user, execution_id=pk)
        execution = execution_for_user(request.user, execution.pk)
        return Response(
            ExecutionSerializer(execution).data, status=status.HTTP_201_CREATED
        )
