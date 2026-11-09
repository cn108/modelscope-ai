"""Audit records for security-sensitive actions (specification §7, §11)."""

import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "common_audit_event"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} at {self.created_at:%Y-%m-%d %H:%M:%S}"
