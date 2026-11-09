"""Immutable playground executions and per-model results (specification M4).

Every execution stores the exact prompts and settings that were sent, plus a
separate result row per model. A failed model never prevents the other model's
result from being persisted, and one execution cannot be mutated afterwards.
"""

import uuid

from django.conf import settings
from django.db import models


class Execution(models.Model):
    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        PARTIAL = "partial", "Partially succeeded"
        FAILED = "failed", "Failed"

    class Mode(models.TextChoices):
        SINGLE = "single", "Single model"
        COMPARE = "compare", "Compare models"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="executions"
    )
    prompt = models.ForeignKey(
        "prompts.Prompt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="executions",
    )
    prompt_version = models.PositiveIntegerField(null=True, blank=True)
    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.SINGLE)
    system_prompt = models.TextField(blank=True)
    user_prompt = models.TextField()
    parameters = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="executions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "playground_execution"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "created_at"])]

    def __str__(self) -> str:
        return f"Execution {self.pk} ({self.status})"


class ExecutionResult(models.Model):
    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(
        Execution, on_delete=models.CASCADE, related_name="results"
    )
    position = models.PositiveSmallIntegerField()
    provider = models.ForeignKey(
        "providers.ProviderConfig",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="execution_results",
    )
    provider_name = models.CharField(max_length=120)
    provider_kind = models.CharField(max_length=16)
    model_id = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    tokens_are_provider_reported = models.BooleanField(default=False)
    latency_ms = models.FloatField(null=True, blank=True)
    finish_reason = models.CharField(max_length=80, blank=True)
    request_id = models.CharField(max_length=200, blank=True)
    estimated_cost = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    cost_currency = models.CharField(max_length=8, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    error = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "playground_execution_result"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["execution", "position"], name="uniq_execution_result_position"
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider_name}:{self.model_id} ({self.status})"
