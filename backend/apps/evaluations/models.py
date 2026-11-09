"""Evaluation runs: immutable, per-case results for datasets against models.

Design rules for M5:
- An evaluation snapshots the dataset version, metrics, judge and model
  selections when it is created. Result rows copy the record text, so editing
  the dataset later never rewrites an existing run.
- Each model gets its own row per dataset record, and metric failures are stored
  per metric instead of discarding the model's answer.
- A rerun always creates a new evaluation; previous results are never modified.
"""

import uuid

from django.conf import settings
from django.db import models


class Evaluation(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="evaluations"
    )
    dataset = models.ForeignKey(
        "datasets.Dataset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evaluations",
    )
    dataset_name = models.CharField(max_length=160)
    dataset_version = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.QUEUED
    )
    metrics = models.JSONField(default=list, blank=True)
    metric_options = models.JSONField(default=dict, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    judge_provider = models.ForeignKey(
        "providers.ProviderConfig",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="judge_evaluations",
    )
    judge_provider_name = models.CharField(max_length=120, blank=True)
    judge_model_id = models.CharField(max_length=200, blank=True)
    judge_parameters = models.JSONField(default=dict, blank=True)
    total_cases = models.PositiveIntegerField(default=0)
    completed_cases = models.PositiveIntegerField(default=0)
    failed_cases = models.PositiveIntegerField(default=0)
    task_id = models.CharField(max_length=200, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    error = models.JSONField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evaluations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "evaluations_evaluation"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Evaluation {self.pk} ({self.status})"


class EvaluationModel(models.Model):
    """One model selection captured for a run."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="models"
    )
    position = models.PositiveSmallIntegerField()
    provider = models.ForeignKey(
        "providers.ProviderConfig",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evaluation_models",
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
        db_table = "evaluations_model"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation", "position"], name="uniq_evaluation_model_position"
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider_name}:{self.model_id}"


class EvaluationResult(models.Model):
    """One dataset case evaluated by one model, with frozen record content."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="results"
    )
    model = models.ForeignKey(
        EvaluationModel, on_delete=models.CASCADE, related_name="results"
    )
    record_position = models.PositiveIntegerField()
    input = models.TextField()
    expected_output = models.TextField(blank=True)
    context = models.JSONField(default=list, blank=True)
    generated_response = models.TextField(blank=True)
    latency_ms = models.FloatField(null=True, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    scores = models.JSONField(default=dict, blank=True)
    metric_results = models.JSONField(default=list, blank=True)
    error = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "evaluations_result"
        ordering = ["record_position"]
        constraints = [
            models.UniqueConstraint(
                fields=["model", "record_position"],
                name="uniq_evaluation_result_record",
            )
        ]
        indexes = [models.Index(fields=["evaluation", "record_position"])]

    def __str__(self) -> str:
        return f"{self.model.model_id} #{self.record_position} ({self.status})"
