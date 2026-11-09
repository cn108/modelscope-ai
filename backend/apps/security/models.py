"""Workspace-scoped security scans, findings and review history (M7).

A scan is an explicit, repeatable configuration.  It points at an existing
dataset, prompt or playground execution; it does not create another user,
model or dataset system.  Findings keep redacted evidence and a status history
so later reviews never erase the original detection.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class SecuritySeverity(models.TextChoices):
    INFO = "info", "Informational"
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class SecurityDisposition(models.TextChoices):
    INFORMATIONAL = "informational", "Informational"
    WARNING = "warning", "Warning"
    BLOCKING = "blocking", "Blocking"


class SecurityClassification(models.TextChoices):
    RISK = "risk", "Potential risk"
    VULNERABILITY = "confirmed_vulnerability", "Confirmed vulnerability"


class SecurityScan(models.Model):
    class TargetType(models.TextChoices):
        DATASET = "dataset", "Dataset"
        PROMPT = "prompt", "Prompt"
        EXECUTION = "execution", "Execution record"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="security_scans"
    )
    target_type = models.CharField(max_length=16, choices=TargetType.choices)
    dataset = models.ForeignKey(
        "datasets.Dataset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="security_scans",
    )
    prompt = models.ForeignKey(
        "prompts.Prompt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="security_scans",
    )
    execution = models.ForeignKey(
        "playground.Execution",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="security_scans",
    )
    target_label = models.CharField(max_length=240)
    target_identifier = models.CharField(max_length=64, blank=True)
    target_version = models.CharField(max_length=80, blank=True)
    checks = models.JSONField(default=list, blank=True)
    config = models.JSONField(default=dict, blank=True)
    blocking_enabled = models.BooleanField(default=False)
    blocking_severity = models.CharField(
        max_length=16, choices=SecuritySeverity.choices, default=SecuritySeverity.HIGH
    )
    blocking_reason = models.TextField(
        blank=True,
        help_text="Required when a scan opts into blocking disposition.",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.QUEUED
    )
    total_items = models.PositiveIntegerField(default=0)
    scanned_items = models.PositiveIntegerField(default=0)
    finding_count = models.PositiveIntegerField(default=0)
    highest_severity = models.CharField(
        max_length=16, choices=SecuritySeverity.choices, blank=True
    )
    summary = models.JSONField(default=dict, blank=True)
    error = models.JSONField(null=True, blank=True)
    task_id = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="security_scans",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "security_scan"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["project", "status"]),
        ]

    def __str__(self) -> str:
        return f"Security scan {self.pk} ({self.status})"


class SecurityFinding(models.Model):
    class ResourceType(models.TextChoices):
        DATASET_RECORD = "dataset_record", "Dataset record"
        PROMPT_VERSION = "prompt_version", "Prompt version"
        EXECUTION = "execution", "Execution record"
        EXECUTION_RESULT = "execution_result", "Execution result"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEWED = "reviewed", "Reviewed"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scan = models.ForeignKey(
        SecurityScan, on_delete=models.CASCADE, related_name="findings"
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="security_findings",
    )
    check_key = models.CharField(max_length=32)
    category = models.CharField(max_length=100)
    title = models.CharField(max_length=240)
    description = models.TextField()
    severity = models.CharField(max_length=16, choices=SecuritySeverity.choices)
    disposition = models.CharField(
        max_length=16, choices=SecurityDisposition.choices
    )
    classification = models.CharField(
        max_length=24,
        choices=SecurityClassification.choices,
        default=SecurityClassification.RISK,
    )
    resource_type = models.CharField(max_length=24, choices=ResourceType.choices)
    resource_id = models.CharField(max_length=64)
    resource_label = models.CharField(max_length=240)
    location = models.CharField(max_length=64, blank=True)
    evidence = models.TextField(help_text="Redacted evidence only.")
    remediation = models.TextField()
    rule_id = models.CharField(max_length=120, blank=True)
    detected_at = models.DateTimeField(default=timezone.now)
    execution = models.ForeignKey(
        "playground.Execution",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="security_findings",
    )
    execution_result = models.ForeignKey(
        "playground.ExecutionResult",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="security_findings",
    )
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.OPEN
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_security_findings",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "security_finding"
        ordering = ["-detected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "scan",
                    "resource_type",
                    "resource_id",
                    "location",
                    "check_key",
                    "category",
                ],
                name="uniq_security_finding_detection",
            )
        ]
        indexes = [
            models.Index(fields=["project", "status", "detected_at"]),
            models.Index(fields=["project", "severity"]),
            models.Index(fields=["scan", "severity"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.severity}, {self.status})"


class SecurityFindingEvent(models.Model):
    """Append-only review/status trail for a finding."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    finding = models.ForeignKey(
        SecurityFinding, on_delete=models.CASCADE, related_name="events"
    )
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(
        max_length=16, choices=SecurityFinding.Status.choices
    )
    note = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="security_finding_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "security_finding_event"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["finding", "created_at"])]

    def __str__(self) -> str:
        return f"{self.finding_id}: {self.from_status or 'detected'} -> {self.to_status}"
