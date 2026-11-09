"""Project API (specification §8: /projects)."""

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.playground.serializers import ExecutionCreateSerializer, ExecutionSerializer
from apps.playground.services import create_execution, list_executions
from apps.prompts.serializers import PromptCreateSerializer, PromptSerializer
from apps.prompts.services import create_prompt, list_prompts
from apps.providers.serializers import ProviderConfigSerializer, ProviderCreateSerializer
from apps.providers.services import create_provider, list_providers
from apps.projects.serializers import (
    ProjectCreateSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
)
from apps.projects.services import (
    create_project,
    delete_project,
    list_projects,
    projects_for_user,
    update_project,
)
from apps.workspaces.permissions import UUID_RE


class ProjectViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE

    def get_queryset(self):
        return projects_for_user(self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return ProjectCreateSerializer
        if self.action in {"update", "partial_update"}:
            return ProjectUpdateSerializer
        return ProjectSerializer

    def list(self, request, *args, **kwargs):
        projects = list_projects(
            user=request.user, workspace_id=request.query_params.get("workspace")
        )
        page = self.paginate_queryset(projects)
        if page is not None:
            return self.get_paginated_response(
                ProjectSerializer(page, many=True).data
            )
        return Response(ProjectSerializer(projects, many=True).data)

    def create(self, request, *args, **kwargs):
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        project = create_project(
            user=request.user,
            workspace_id=data["workspace"],
            name=data["name"],
            description=data.get("description", ""),
        )
        return Response(
            ProjectSerializer(project).data, status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        project = self.get_object()
        serializer = ProjectUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        project = update_project(
            user=request.user,
            project=project,
            validated_data=serializer.validated_data,
        )
        return Response(ProjectSerializer(project).data)

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        delete_project(user=request.user, project=project)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="providers")
    def providers(self, request, pk=None):
        project = self.get_object()
        if request.method == "POST":
            serializer = ProviderCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            provider = create_provider(
                actor=request.user,
                project_id=project.pk,
                validated_data=serializer.validated_data,
            )
            return Response(
                ProviderConfigSerializer(provider).data,
                status=status.HTTP_201_CREATED,
            )

        providers = list_providers(user=request.user, project_id=project.pk)
        return Response(ProviderConfigSerializer(providers, many=True).data)

    @action(detail=True, methods=["get", "post"], url_path="prompts")
    def prompts(self, request, pk=None):
        project = self.get_object()
        if request.method == "POST":
            serializer = PromptCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            prompt = create_prompt(
                actor=request.user,
                project_id=project.pk,
                validated_data=serializer.validated_data,
            )
            from apps.prompts.services import get_prompt

            prompt = get_prompt(user=request.user, prompt_id=prompt.pk)
            return Response(
                PromptSerializer(prompt).data, status=status.HTTP_201_CREATED
            )

        prompts = list_prompts(user=request.user, project_id=project.pk)
        return Response(PromptSerializer(prompts, many=True).data)

    @action(detail=True, methods=["get", "post"], url_path="executions")
    def executions(self, request, pk=None):
        project = self.get_object()
        if request.method == "POST":
            serializer = ExecutionCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            execution = create_execution(
                actor=request.user,
                project_id=project.pk,
                validated_data=serializer.validated_data,
            )
            from apps.playground.services import execution_for_user

            execution = execution_for_user(request.user, execution.pk)
            return Response(
                ExecutionSerializer(execution).data, status=status.HTTP_201_CREATED
            )

        executions = list_executions(user=request.user, project_id=project.pk)
        return Response(ExecutionSerializer(executions, many=True).data)
