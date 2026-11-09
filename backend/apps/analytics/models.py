"""Reproducible analytics report snapshots (Milestone 8).

Reports are generated from the platform's existing execution traces,
evaluation summaries and security findings.  The report stores a snapshot of
the exact figures and scope used, rather than rebuilding a report from data
that may have changed later.
"""

import uuid

from django.conf import settings
from django.db import models


class AnalyticsReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="analytics_reports"
    )
    title = models.CharField(max_length=200)
    sections = models.JSONField(default=list, blank=True)
    period_from = models.DateField()
    period_to = models.DateField()
    filters = models.JSONField(default=dict, blank=True)
    scope = models.JSONField(default=dict, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    schema_version = models.PositiveSmallIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="analytics_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "analytics_report"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["created_by", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.period_from} to {self.period_to})"
