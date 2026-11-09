"""Execution traces and spans (Milestone 6).

A ``Trace`` is one actual model call: a playground result, an evaluation case
result, or a DeepEval judge call made for an evaluation.  It deliberately does
not duplicate the prompt/response text already stored on those result rows; the
explorer resolves the linked record at read time.  Judge prompts are not stored
anywhere else, so those traces keep a truncated copy.

``Span`` records the operations inside a call (adapter preparation, the provider
request, metric scoring and its per-metric children).  Spans form a tree via
``parent`` and preserve a deterministic ``sequence`` for display.
"""

import uuid

from django.db import models


class Trace(models.Model):
    class Source(models.TextChoices):
        PLAYGROUND = "playground", "Playground"
        EVALUATION = "evaluation", "Evaluation"

    class Role(models.TextChoices):
        MODEL = "model", "Model call"
        JUDGE = "judge", "Judge call"

    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    class CostStatus(models.TextChoices):
        ESTIMATED = "estimated", "Estimated"
        UNAVAILABLE = "unavailable", "Unavailable"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="traces"
    )
    source = models.CharField(max_length=16, choices=Source.choices)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MODEL)
    execution_result = models.ForeignKey(
        "playground.ExecutionResult",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="traces",
    )
    evaluation_result = models.ForeignKey(
        "evaluations.EvaluationResult",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="traces",
    )

    provider = models.ForeignKey(
        "providers.ProviderConfig",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="traces",
    )
    provider_name = models.CharField(max_length=120)
    provider_kind = models.CharField(max_length=16)
    model_id = models.CharField(max_length=200)

    status = models.CharField(max_length=16, choices=Status.choices)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    duration_ms = models.FloatField(null=True, blank=True)
    # Provider response time, excluding metric scoring / persistence. The full
    # call wall time remains in ``duration_ms``.
    provider_latency_ms = models.FloatField(null=True, blank=True)

    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)

    estimated_cost = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    cost_currency = models.CharField(max_length=8, blank=True)
    cost_status = models.CharField(
        max_length=16,
        choices=CostStatus.choices,
        default=CostStatus.UNAVAILABLE,
    )
    cost_detail = models.CharField(max_length=240, blank=True)

    error = models.JSONField(null=True, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    # Only populated when the source record does not retain the text (judge calls).
    request_text = models.TextField(blank=True)
    response_text = models.TextField(blank=True)
    otel_trace_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "observability_trace"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["project", "started_at"]),
            models.Index(fields=["project", "status"]),
            models.Index(fields=["provider", "model_id"]),
            models.Index(fields=["source", "role"]),
            # The dashboard's slowest-call list orders retained raw traces by
            # duration; project first keeps the index workspace-scoped.
            models.Index(fields=["project", "duration_ms"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(
                        source="playground",
                        execution_result__isnull=False,
                        evaluation_result__isnull=True,
                    )
                    | models.Q(
                        source="evaluation",
                        execution_result__isnull=True,
                        evaluation_result__isnull=False,
                    )
                ),
                name="trace_links_exactly_one_result",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider_name}:{self.model_id} ({self.status})"


class TraceRollup(models.Model):
    """Daily aggregates of completed model calls for dashboard reads.

    One row represents one combination of day, execution source, call role,
    status, provider and model.  ``TraceRollupState`` records the last day that
    has been completely rolled up for a project, so the dashboard can use raw
    traces for newer days without double counting.

    Provider identity is stored as a string rather than a foreign key so a
    deleted provider does not remove historical aggregates.
    """

    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="trace_rollups"
    )
    day = models.DateField()
    source = models.CharField(max_length=16, choices=Trace.Source.choices)
    role = models.CharField(max_length=16, choices=Trace.Role.choices)
    status = models.CharField(max_length=16, choices=Trace.Status.choices)
    provider_id = models.CharField(max_length=36, blank=True)
    provider_name = models.CharField(max_length=120)
    provider_kind = models.CharField(max_length=16)
    model_id = models.CharField(max_length=200)
    cost_currency = models.CharField(max_length=8, blank=True)

    calls = models.PositiveIntegerField(default=0)
    input_tokens = models.BigIntegerField(default=0)
    output_tokens = models.BigIntegerField(default=0)
    token_calls = models.PositiveIntegerField(default=0)
    latency_total_ms = models.FloatField(default=0)
    latency_count = models.PositiveIntegerField(default=0)
    duration_total_ms = models.FloatField(default=0)
    duration_count = models.PositiveIntegerField(default=0)
    estimated_cost = models.DecimalField(
        max_digits=18, decimal_places=6, default=0
    )
    estimated_calls = models.PositiveIntegerField(default=0)
    unavailable_calls = models.PositiveIntegerField(default=0)
    error_counts = models.JSONField(default=dict, blank=True)

    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "observability_trace_rollup"
        ordering = ["day"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "project",
                    "day",
                    "source",
                    "role",
                    "status",
                    "provider_id",
                    "provider_name",
                    "provider_kind",
                    "model_id",
                    "cost_currency",
                ],
                name="uniq_trace_rollup_bucket",
            )
        ]
        indexes = [
            models.Index(fields=["project", "day"]),
            models.Index(fields=["project", "day", "model_id"]),
            models.Index(fields=["project", "day", "provider_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.day} {self.provider_name}:{self.model_id} ({self.calls})"


class TraceRollupState(models.Model):
    """The last fully aggregated day for a project's trace rollups."""

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="trace_rollup_state",
    )
    through_day = models.DateField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "observability_trace_rollup_state"

    def __str__(self) -> str:
        return f"Rollups through {self.through_day}"


class Span(models.Model):
    class Kind(models.TextChoices):
        INTERNAL = "internal", "Internal"
        CLIENT = "client", "Provider request"
        TASK = "task", "Background task"

    class Status(models.TextChoices):
        OK = "ok", "OK"
        ERROR = "error", "Error"
        UNSET = "unset", "Unset"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trace = models.ForeignKey(Trace, on_delete=models.CASCADE, related_name="spans")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    sequence = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.INTERNAL)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.UNSET
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    duration_ms = models.FloatField(null=True, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    error = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "observability_span"
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["trace", "sequence"], name="uniq_trace_span_sequence"
            )
        ]
        indexes = [models.Index(fields=["trace", "sequence"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"
