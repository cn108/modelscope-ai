"""Workspace, membership and RBAC services (§1: logic outside views)."""

from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.workspaces.models import Membership, Workspace
from apps.workspaces.permissions import parse_uuid, require_membership
from common.audit.services import record_event
from common.exceptions import Conflict


def workspaces_for_user(user):
    """Workspaces visible to a user, with the caller's membership prefetched."""
    return (
        Workspace.objects.filter(memberships__user=user)
        .prefetch_related(
            Prefetch(
                "memberships",
                queryset=Membership.objects.filter(user=user),
                to_attr="current_memberships",
            )
        )
        .distinct()
        .order_by("-created_at")
    )


@transaction.atomic
def create_workspace(*, user, name: str, settings: dict | None = None) -> Workspace:
    workspace = Workspace.objects.create(
        name=name.strip(), owner=user, settings=settings or {}
    )
    Membership.objects.create(
        workspace=workspace, user=user, role=Membership.Role.OWNER
    )
    record_event(
        actor=user,
        action="workspace.created",
        workspace=workspace,
        target_type="workspace",
        target_id=workspace.pk,
    )
    return workspace


@transaction.atomic
def update_workspace(*, user, workspace_id, validated_data) -> Workspace:
    workspace, _ = require_membership(user, workspace_id, Membership.Role.ADMIN)
    fields = []
    for field in ("name", "settings"):
        if field in validated_data:
            value = validated_data[field]
            if field == "name":
                value = value.strip()
            setattr(workspace, field, value)
            fields.append(field)
    if fields:
        workspace.save(update_fields=[*fields, "updated_at"])
        record_event(
            actor=user,
            action="workspace.updated",
            workspace=workspace,
            target_type="workspace",
            target_id=workspace.pk,
            metadata={"fields": fields},
        )
    return workspace


@transaction.atomic
def delete_workspace(*, user, workspace_id) -> None:
    workspace, _ = require_membership(user, workspace_id, Membership.Role.OWNER)
    record_event(
        actor=user,
        action="workspace.deleted",
        workspace=workspace,
        target_type="workspace",
        target_id=workspace.pk,
    )
    workspace.delete()


def list_members(*, user, workspace_id):
    workspace, _ = require_membership(user, workspace_id, Membership.Role.VIEWER)
    return (
        Membership.objects.filter(workspace=workspace)
        .select_related("user")
        .order_by("created_at")
    )


def _get_membership(workspace, membership_id) -> Membership:
    membership = (
        Membership.objects.select_related("user")
        .filter(
            workspace=workspace,
            pk=parse_uuid(membership_id, message="Membership not found."),
        )
        .first()
    )
    if membership is None:
        raise NotFound("Membership not found.")
    return membership


@transaction.atomic
def add_member(*, actor, workspace_id, email: str, role: str) -> Membership:
    workspace, actor_membership = require_membership(
        actor, workspace_id, Membership.Role.ADMIN
    )
    role = str(role)
    if role == Membership.Role.OWNER:
        raise ValidationError(
            {"role": ["Ownership cannot be granted; transfer is not supported."]}
        )
    if (
        role == Membership.Role.ADMIN
        and actor_membership.role != Membership.Role.OWNER
    ):
        raise PermissionDenied("Only the workspace owner can add administrators.")

    user = User.objects.filter(email=email.strip().lower(), is_active=True).first()
    if user is None:
        raise ValidationError(
            {"email": ["No active account found with this email address."]}
        )
    if Membership.objects.filter(workspace=workspace, user=user).exists():
        raise Conflict("This user is already a member of the workspace.")

    try:
        with transaction.atomic():
            membership = Membership.objects.create(
                workspace=workspace, user=user, role=role
            )
    except IntegrityError as exc:
        raise Conflict("This user is already a member of the workspace.") from exc

    record_event(
        actor=actor,
        action="membership.added",
        workspace=workspace,
        target_type="membership",
        target_id=membership.pk,
        metadata={"user_id": str(user.pk), "role": membership.role},
    )
    return membership


@transaction.atomic
def update_member_role(*, actor, workspace_id, membership_id, role: str) -> Membership:
    workspace, actor_membership = require_membership(
        actor, workspace_id, Membership.Role.ADMIN
    )
    target = _get_membership(workspace, membership_id)
    role = str(role)

    if target.role == Membership.Role.OWNER:
        raise PermissionDenied("The workspace owner's role cannot be changed.")
    if role == Membership.Role.OWNER:
        raise ValidationError(
            {"role": ["Ownership cannot be granted; transfer is not supported."]}
        )
    if actor_membership.role == Membership.Role.ADMIN and (
        target.role == Membership.Role.ADMIN or role == Membership.Role.ADMIN
    ):
        raise PermissionDenied("Only the workspace owner can manage administrators.")
    if target.role == role:
        return target

    previous = target.role
    target.role = role
    target.save(update_fields=["role", "updated_at"])
    record_event(
        actor=actor,
        action="membership.role_changed",
        workspace=workspace,
        target_type="membership",
        target_id=target.pk,
        metadata={
            "from": previous,
            "to": role,
            "user_id": str(target.user_id),
        },
    )
    return target


@transaction.atomic
def remove_member(*, actor, workspace_id, membership_id) -> None:
    workspace, actor_membership = require_membership(
        actor, workspace_id, Membership.Role.ADMIN
    )
    target = _get_membership(workspace, membership_id)

    if target.role == Membership.Role.OWNER:
        raise PermissionDenied("The workspace owner cannot be removed.")
    if (
        actor_membership.role == Membership.Role.ADMIN
        and target.role == Membership.Role.ADMIN
    ):
        raise PermissionDenied("Only the workspace owner can remove administrators.")

    record_event(
        actor=actor,
        action="membership.removed",
        workspace=workspace,
        target_type="membership",
        target_id=target.pk,
        metadata={"user_id": str(target.user_id), "role": target.role},
    )
    target.delete()
