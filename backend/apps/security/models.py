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


class SecurityTestRun(models.Model):
    """One controlled adversarial test run against configured project models."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="security_test_runs"
    )
    case_keys = models.JSONField(default=list, blank=True)
    categories = models.JSONField(default=list, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.QUEUED
    )
    total_models = models.PositiveSmallIntegerField(default=0)
    total_cases = models.PositiveSmallIntegerField(default=0)
    total_results = models.PositiveIntegerField(default=0)
    completed_results = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    error = models.JSONField(null=True, blank=True)
    task_id = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="security_test_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "security_test_run"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["project", "status"]),
        ]

    def __str__(self) -> str:
        return f"Security test run {self.pk} ({self.status})"


class SecurityTestModel(models.Model):
    """One model selection and its progress within a test run."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        SecurityTestRun, on_delete=models.CASCADE, related_name="models"
    )
    position = models.PositiveSmallIntegerField()
    provider = models.ForeignKey(
        "providers.ProviderConfig",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="security_test_models",
    )
    provider_name = models.CharField(max_length=120)
    provider_kind = models.CharField(max_length=16)
    model_id = models.CharField(max_length=200)
    parameters = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    summary = models.JSONField(default=dict, blank=True)
    error = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "security_test_model"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "position"], name="uniq_security_test_model_position"
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider_name}:{self.model_id}"


class SecurityTestResult(models.Model):
    """One actual model response classified against one reviewed attack case."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    class Verdict(models.TextChoices):
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"
        INCONCLUSIVE = "inconclusive", "Inconclusive"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        SecurityTestRun, on_delete=models.CASCADE, related_name="results"
    )
    model = models.ForeignKey(
        SecurityTestModel, on_delete=models.CASCADE, related_name="results"
    )
    case_key = models.CharField(max_length=120)
    case_name = models.CharField(max_length=240)
    category = models.CharField(max_length=64)
    category_label = models.CharField(max_length=120)
    technique = models.CharField(max_length=160)
    system_prompt = models.TextField(blank=True)
    attack_input = models.TextField()
    detector = models.CharField(max_length=40, blank=True)
    detector_config = models.JSONField(default=dict, blank=True)
    response_text = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    verdict = models.CharField(max_length=16, choices=Verdict.choices, blank=True)
    severity = models.CharField(
        max_length=16, choices=SecuritySeverity.choices, blank=True
    )
    rationale = models.TextField(blank=True)
    evidence = models.TextField(blank=True)
    mitigation = models.TextField(blank=True)
    criteria = models.TextField(blank=True)
    matched_rules = models.JSONField(default=list, blank=True)
    references = models.JSONField(default=list, blank=True)
    canary = models.CharField(max_length=80, blank=True)
    duration_ms = models.FloatField(null=True, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    provider_request_id = models.CharField(max_length=200, blank=True)
    error = models.JSONField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "security_test_result"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["model", "case_key"], name="uniq_security_test_model_case"
            )
        ]
        indexes = [
            models.Index(fields=["run", "category"]),
            models.Index(fields=["model", "verdict"]),
            models.Index(fields=["run", "verdict"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_key} · {self.model} ({self.verdict or self.status})"
