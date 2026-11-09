"""Projects belong to exactly one workspace (specification §7)."""

import uuid

from django.conf import settings
from django.db import models

from apps.workspaces.models import Workspace


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="projects"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "projects_project"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "created_at"]),
            models.Index(fields=["created_by", "created_at"]),
        ]

    def __str__(self) -> str:
        return self.name
