"""Workspace role checks shared by workspace and project services (§7, §11).

Cross-tenant access is reported as 404 so the resource is not disclosed;
insufficient role inside a workspace is reported as 403.
"""

import uuid

from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import BasePermission

from apps.workspaces.models import Membership, Workspace

UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

ROLE_RANK = {
    Membership.Role.VIEWER: 0,
    Membership.Role.MEMBER: 1,
    Membership.Role.ADMIN: 2,
    Membership.Role.OWNER: 3,
}


def parse_uuid(value, *, message: str = "Resource not found.") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise NotFound(message) from exc


def membership_for(user, workspace):
    if not getattr(user, "is_authenticated", False):
        return None
    return Membership.objects.filter(workspace=workspace, user=user).first()


def require_membership(user, workspace_id, minimum_role=Membership.Role.VIEWER):
    """Resolve a workspace the caller belongs to, or raise 404/403."""
    workspace = (
        Workspace.objects.filter(pk=parse_uuid(workspace_id, message="Workspace not found."))
        .first()
    )
    if workspace is None:
        raise NotFound("Workspace not found.")
    membership = membership_for(user, workspace)
    if membership is None:
        raise NotFound("Workspace not found.")
    if ROLE_RANK[membership.role] < ROLE_RANK[minimum_role]:
        raise PermissionDenied("You do not have permission to perform this action.")
    return workspace, membership


class IsWorkspaceMember(BasePermission):
    """Object-level permission: caller belongs to the workspace at any role."""

    minimum_role = Membership.Role.VIEWER

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        workspace = obj if isinstance(obj, Workspace) else getattr(obj, "workspace", None)
        if workspace is None:
            return False
        membership = membership_for(request.user, workspace)
        return bool(
            membership and ROLE_RANK[membership.role] >= ROLE_RANK[self.minimum_role]
        )


class IsWorkspaceManager(IsWorkspaceMember):
    minimum_role = Membership.Role.ADMIN


class IsWorkspaceOwner(IsWorkspaceMember):
    minimum_role = Membership.Role.OWNER
