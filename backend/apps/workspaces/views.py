"""Workspace API (specification §8: /workspaces, /workspaces/{id}/members)."""

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.workspaces.permissions import UUID_RE
from apps.workspaces.serializers import (
    AddMemberSerializer,
    MembershipSerializer,
    UpdateMemberRoleSerializer,
    WorkspaceCreateSerializer,
    WorkspaceSerializer,
    WorkspaceUpdateSerializer,
)
from apps.workspaces.services import (
    add_member,
    create_workspace,
    delete_workspace,
    list_members,
    remove_member,
    update_member_role,
    update_workspace,
    workspaces_for_user,
)


class WorkspaceViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    lookup_value_regex = UUID_RE

    def get_queryset(self):
        return workspaces_for_user(self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return WorkspaceCreateSerializer
        if self.action in {"update", "partial_update"}:
            return WorkspaceUpdateSerializer
        return WorkspaceSerializer

    def create(self, request, *args, **kwargs):
        serializer = WorkspaceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        workspace = create_workspace(
            user=request.user,
            name=data["name"],
            settings=data.get("settings"),
        )
        output = WorkspaceSerializer(
            workspace, context=self.get_serializer_context()
        )
        return Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        serializer = WorkspaceUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        workspace = update_workspace(
            user=request.user,
            workspace_id=kwargs["pk"],
            validated_data=serializer.validated_data,
        )
        output = WorkspaceSerializer(
            workspace, context=self.get_serializer_context()
        )
        return Response(output.data)

    def destroy(self, request, *args, **kwargs):
        delete_workspace(user=request.user, workspace_id=kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, pk=None):
        if request.method == "POST":
            serializer = AddMemberSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            membership = add_member(
                actor=request.user,
                workspace_id=pk,
                email=data["email"],
                role=data["role"],
            )
            output = MembershipSerializer(
                membership, context=self.get_serializer_context()
            )
            return Response(output.data, status=status.HTTP_201_CREATED)

        members = list_members(user=request.user, workspace_id=pk)
        page = self.paginate_queryset(members)
        if page is not None:
            serializer = MembershipSerializer(
                page, many=True, context=self.get_serializer_context()
            )
            return self.get_paginated_response(serializer.data)
        serializer = MembershipSerializer(
            members, many=True, context=self.get_serializer_context()
        )
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path=f"members/(?P<membership_id>{UUID_RE})",
    )
    def member_detail(self, request, pk=None, membership_id=None):
        if request.method == "DELETE":
            remove_member(
                actor=request.user,
                workspace_id=pk,
                membership_id=membership_id,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = UpdateMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = update_member_role(
            actor=request.user,
            workspace_id=pk,
            membership_id=membership_id,
            role=serializer.validated_data["role"],
        )
        output = MembershipSerializer(
            membership, context=self.get_serializer_context()
        )
        return Response(output.data)
