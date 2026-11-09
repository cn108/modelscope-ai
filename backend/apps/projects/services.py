"""Project services; tenancy and edit rules live here (§1, §7)."""

from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.projects.models import Project
from apps.workspaces.models import Membership
from apps.workspaces.permissions import require_membership


def project_for_user(user, project_id, minimum_role=Membership.Role.VIEWER) -> Project:
    """Resolve a project the caller may see, or raise 404/403."""
    project = Project.objects.select_related("workspace").filter(pk=project_id).first()
    if project is None:
        raise NotFound("Project not found.")
    require_membership(user, project.workspace_id, minimum_role)
    return project


def projects_for_user(user):
    """Projects in workspaces the user belongs to, regardless of role."""
    return (
        Project.objects.filter(workspace__memberships__user=user)
        .select_related("workspace")
        .distinct()
        .order_by("-created_at")
    )


def list_projects(*, user, workspace_id=None):
    if workspace_id:
        workspace, _ = require_membership(user, workspace_id, Membership.Role.VIEWER)
        return (
            Project.objects.filter(workspace=workspace)
            .select_related("workspace")
            .order_by("-created_at")
        )
    return projects_for_user(user)


@transaction.atomic
def create_project(*, user, workspace_id, name: str, description: str = "") -> Project:
    workspace, _ = require_membership(user, workspace_id, Membership.Role.MEMBER)
    return Project.objects.create(
        workspace=workspace,
        name=name.strip(),
        description=description.strip(),
        created_by=user,
    )


def _require_editor(user, project: Project) -> None:
    membership = Membership.objects.filter(
        workspace=project.workspace, user=user
    ).first()
    if membership is None:
        raise NotFound("Project not found.")
    if membership.role == Membership.Role.VIEWER:
        raise PermissionDenied("Viewers cannot modify projects.")
    if (
        membership.role not in (Membership.Role.ADMIN, Membership.Role.OWNER)
        and project.created_by_id != user.id
    ):
        raise PermissionDenied("You can only modify projects you created.")


@transaction.atomic
def update_project(*, user, project: Project, validated_data) -> Project:
    _require_editor(user, project)
    fields = []
    for field in ("name", "description"):
        if field in validated_data:
            value = validated_data[field]
            if isinstance(value, str):
                value = value.strip()
            setattr(project, field, value)
            fields.append(field)
    if fields:
        project.save(update_fields=[*fields, "updated_at"])
    return project


@transaction.atomic
def delete_project(*, user, project: Project) -> None:
    _require_editor(user, project)
    project.delete()
