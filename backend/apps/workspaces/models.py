"""Tenant boundary models (specification §7)."""

import uuid

from django.conf import settings
from django.db import models


class Workspace(models.Model):
    """Tenant boundary. Projects, memberships and audit rows belong to one."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_workspaces",
    )
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workspaces_workspace"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    """User-to-workspace relation and role (specification §7)."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_memberships",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workspaces_membership"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "user"],
                name="uniq_membership_workspace_user",
            )
        ]
        indexes = [
            models.Index(fields=["workspace", "role"]),
            models.Index(fields=["user", "role"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} in {self.workspace} ({self.role})"
