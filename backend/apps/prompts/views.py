from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.prompts.models import Prompt
from apps.prompts.serializers import (
    PromptSerializer,
    PromptUpdateSerializer,
    PromptVersionSerializer,
    RestoreVersionSerializer,
)
from apps.prompts.services import (
    delete_prompt,
    duplicate_prompt,
    get_prompt,
    restore_version,
    update_prompt,
)
from apps.workspaces.permissions import UUID_RE


class PromptViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE
    serializer_class = PromptSerializer

    def get_queryset(self):
        return Prompt.objects.filter(
            project__workspace__memberships__user=self.request.user
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        prompt = get_prompt(user=request.user, prompt_id=kwargs["pk"])
        return Response(PromptSerializer(prompt).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        get_prompt(user=request.user, prompt_id=kwargs["pk"])
        serializer = PromptUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        prompt = update_prompt(
            actor=request.user,
            prompt_id=kwargs["pk"],
            validated_data=serializer.validated_data,
        )
        return Response(PromptSerializer(prompt).data)

    def destroy(self, request, *args, **kwargs):
        delete_prompt(actor=request.user, prompt_id=kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request, pk=None):
        prompt = get_prompt(user=request.user, prompt_id=pk)
        rows = prompt.versions.select_related("created_by").order_by("-version_number")
        return Response(PromptVersionSerializer(rows, many=True).data)

    @action(detail=True, methods=["post"], url_path="versions/restore")
    def restore(self, request, pk=None):
        serializer = RestoreVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prompt = restore_version(
            actor=request.user,
            prompt_id=pk,
            version_number=serializer.validated_data["version_number"],
        )
        return Response(PromptSerializer(prompt).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate(self, request, pk=None):
        prompt = duplicate_prompt(actor=request.user, prompt_id=pk)
        return Response(
            PromptSerializer(get_prompt(user=request.user, prompt_id=prompt.pk)).data,
            status=status.HTTP_201_CREATED,
        )
