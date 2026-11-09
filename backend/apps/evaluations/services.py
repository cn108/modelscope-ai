"""Evaluation services: queueing, background execution and repeatable reruns.

Model execution goes through ``apps.providers.services.generate_once``, which
reuses the M3 adapters. Metric computation goes through the registry, so adding
a metric never requires touching this module or any page.
"""

from __future__ import annotations

from statistics import mean
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.datasets.services import dataset_for_user
from apps.evaluations.models import Evaluation, EvaluationModel, EvaluationResult
from apps.projects.services import project_for_user
from apps.prompts.serializers import validate_parameters
from apps.providers.models import ProviderConfig
from apps.providers.services import generate_once
from apps.workspaces.models import Membership
from apps.workspaces.permissions import require_membership
from integrations.evaluation.registry import (
    MetricDefinition,
    evaluate as evaluate_metric,
    resolve_metrics,
)

MAX_MODELS_PER_RUN = 5
TERMINAL_STATUSES = (Evaluation.Status.COMPLETED, Evaluation.Status.FAILED)


def evaluation_for_user(
    user, evaluation_id, minimum_role=Membership.Role.VIEWER
) -> Evaluation:
    evaluation = (
        Evaluation.objects.select_related(
            "project", "project__workspace", "dataset", "judge_provider"
        )
        .filter(pk=evaluation_id)
        .first()
    )
    if evaluation is None:
        raise NotFound("Evaluation not found.")
    require_membership(user, evaluation.project.workspace_id, minimum_role)
    return evaluation


def evaluation_detail(*, user, evaluation_id) -> Evaluation:
    evaluation = evaluation_for_user(user, evaluation_id)
    return (
        Evaluation.objects.select_related(
            "project", "dataset", "judge_provider", "created_by"
        )
        .prefetch_related("models")
        .get(pk=evaluation.pk)
    )


def list_evaluations(*, user, project_id, limit=50):
    project = project_for_user(user, project_id)
    return (
        Evaluation.objects.filter(project=project)
        .select_related("dataset")
        .prefetch_related("models")
        .order_by("-created_at")[:limit]
    )


def _resolve_models(project, selections) -> list[tuple[ProviderConfig, str, dict]]:
    if not 1 <= len(selections) <= MAX_MODELS_PER_RUN:
        raise ValidationError(
            {"models": f"Select between 1 and {MAX_MODELS_PER_RUN} models."}
        )
    seen: set[tuple[str, str]] = set()
    for item in selections:
        key = (str(item["provider"]), item["model_id"])
        if key in seen:
            raise ValidationError({"models": "Each selected model must be different."})
        seen.add(key)

    providers = {
        provider.pk: provider
        for provider in ProviderConfig.objects.filter(
            pk__in=[item["provider"] for item in selections], project=project
        )
    }
    resolved = []
    for item in selections:
        provider = providers.get(item["provider"])
        if provider is None:
            raise ValidationError(
                {"models": "A selected provider does not belong to this project."}
            )
        resolved.append(
            (provider, item["model_id"], item.get("parameters") or {})
        )
    return resolved


@transaction.atomic
def create_evaluation(*, actor, project_id, validated_data) -> Evaluation:
    project = project_for_user(actor, project_id, Membership.Role.MEMBER)
    dataset = dataset_for_user(actor, validated_data["dataset"], Membership.Role.MEMBER)
    if dataset.project_id != project.id:
        raise ValidationError({"dataset": "This dataset belongs to another project."})

    records = list(dataset.records.order_by("position"))
    if not records:
        raise ValidationError(
            {"dataset": "Add at least one record before running an evaluation."}
        )
    definitions = resolve_metrics(validated_data["metrics"])
    selections = _resolve_models(project, validated_data["models"])
    parameters = validate_parameters(validated_data.get("parameters") or {})

    judge_data = validated_data.get("judge") or None
    judge_provider = None
    judge_model_id = ""
    judge_parameters: dict[str, Any] = {}
    if any(definition.requires_judge for definition in definitions):
        if not judge_data or not judge_data.get("model_id"):
            raise ValidationError(
                {
                    "judge": "Choose a provider and model to judge the selected metrics."
                }
            )
        judge_provider = (
            ProviderConfig.objects.filter(
                pk=judge_data["provider"], project=project
            ).first()
        )
        if judge_provider is None:
            raise ValidationError(
                {"judge": "The judge provider does not belong to this project."}
            )
        judge_model_id = judge_data["model_id"].strip()
        judge_parameters = validate_parameters(judge_data.get("parameters") or {})
    elif judge_data:
        raise ValidationError(
            {"judge": "A judge model is only used by judge-based metrics."}
        )

    evaluation = Evaluation.objects.create(
        project=project,
        dataset=dataset,
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        metrics=[definition.key for definition in definitions],
        parameters=parameters,
        judge_provider=judge_provider,
        judge_provider_name=judge_provider.name if judge_provider else "",
        judge_model_id=judge_model_id,
        judge_parameters=judge_parameters,
        total_cases=len(records),
        created_by=actor,
    )

    model_rows = [
        EvaluationModel.objects.create(
            evaluation=evaluation,
            position=position,
            provider=provider,
            provider_name=provider.name,
            provider_kind=provider.kind,
            model_id=model_id,
            parameters=model_parameters,
        )
        for position, (provider, model_id, model_parameters) in enumerate(selections)
    ]
    EvaluationResult.objects.bulk_create(
        [
            EvaluationResult(
                evaluation=evaluation,
                model=model_row,
                record_position=record.position,
                input=record.input,
                expected_output=record.expected_output,
                context=record.context or [],
            )
            for model_row in model_rows
            for record in records
        ]
    )
    return evaluation


def _mark_failed(evaluation_id, error: dict[str, Any]) -> None:
    Evaluation.objects.filter(pk=evaluation_id).exclude(
        status__in=TERMINAL_STATUSES
    ).update(
        status=Evaluation.Status.FAILED,
        error=error,
        completed_at=timezone.now(),
    )


def enqueue_evaluation(evaluation: Evaluation) -> Evaluation:
    """Queue the Celery task; a broker failure is surfaced as a failed run."""
    from apps.evaluations.tasks import run_evaluation

    try:
        async_result = run_evaluation.delay(str(evaluation.pk))
    except Exception:  # noqa: BLE001 - broker/transport failures stay user-visible
        _mark_failed(
            evaluation.pk,
            {
                "category": "queue_unavailable",
                "message": "The evaluation could not be queued. Check the worker and broker.",
            },
        )
        evaluation.refresh_from_db()
        return evaluation

    task_id = getattr(async_result, "id", None)
    if task_id:
        Evaluation.objects.filter(
            pk=evaluation.pk, status=Evaluation.Status.QUEUED
        ).update(task_id=str(task_id)[:200])
    evaluation.refresh_from_db()
    return evaluation


def _build_judge(evaluation: Evaluation, definitions: list[MetricDefinition]):
    if not any(definition.requires_judge for definition in definitions):
        return None
    if evaluation.judge_provider_id is None or not evaluation.judge_model_id:
        return None
    try:
        from integrations.evaluation.judge import build_judge

        return build_judge(
            evaluation.judge_provider,
            evaluation.judge_model_id,
            evaluation.judge_parameters or {},
        )
    except Exception:  # noqa: BLE001 - judge unavailability becomes a metric error
        return None


def _fail_result(result: EvaluationResult, error: dict[str, Any]) -> None:
    result.status = EvaluationResult.Status.FAILED
    result.error = error
    result.save(update_fields=["status", "error", "updated_at"])


def _model_summary(model_row: EvaluationModel, rows: list[EvaluationResult]) -> dict:
    succeeded = sum(
        1 for row in rows if row.status == EvaluationResult.Status.SUCCEEDED
    )
    failed = sum(1 for row in rows if row.status == EvaluationResult.Status.FAILED)
    scores: dict[str, float] = {}
    counts: dict[str, int] = {}
    for row in rows:
        for key, value in (row.scores or {}).items():
            if isinstance(value, (int, float)):
                scores[key] = scores.get(key, 0.0) + float(value)
                counts[key] = counts.get(key, 0) + 1
    averages = {
        key: round(scores[key] / counts[key], 4) for key in scores if counts[key]
    }
    latencies = [row.latency_ms for row in rows if row.latency_ms is not None]
    input_tokens = [row.input_tokens for row in rows if row.input_tokens is not None]
    output_tokens = [row.output_tokens for row in rows if row.output_tokens is not None]
    return {
        "id": str(model_row.pk),
        "position": model_row.position,
        "provider": str(model_row.provider_id) if model_row.provider_id else None,
        "provider_name": model_row.provider_name,
        "provider_kind": model_row.provider_kind,
        "model_id": model_row.model_id,
        "cases": len(rows),
        "succeeded": succeeded,
        "failed": failed,
        "avg_latency_ms": round(mean(latencies), 2) if latencies else None,
        "total_input_tokens": sum(input_tokens) if input_tokens else None,
        "total_output_tokens": sum(output_tokens) if output_tokens else None,
        "metric_averages": averages,
        "metric_scored_counts": counts,
    }


def _run_model(
    evaluation: Evaluation,
    model_row: EvaluationModel,
    definitions: list[MetricDefinition],
    judge,
) -> dict:
    model_row.status = EvaluationModel.Status.RUNNING
    model_row.save(update_fields=["status"])

    rows = list(model_row.results.order_by("record_position"))
    if model_row.provider_id is None or model_row.provider is None:
        error = {
            "category": "provider_missing",
            "message": "The provider used by this model no longer exists.",
        }
        for row in rows:
            if row.status == EvaluationResult.Status.PENDING:
                _fail_result(row, error)
        model_row.status = EvaluationModel.Status.FAILED
        model_row.error = error
        model_row.summary = _model_summary(model_row, rows)
        model_row.save(update_fields=["status", "error", "summary"])
        return model_row.summary

    parameters = {
        **(model_row.provider.settings or {}),
        **(evaluation.parameters or {}),
        **(model_row.parameters or {}),
    }

    for row in rows:
        if row.status != EvaluationResult.Status.PENDING:
            continue
        generation, error = generate_once(
            provider=model_row.provider,
            model_id=model_row.model_id,
            messages=[{"role": "user", "content": row.input}],
            parameters=parameters,
        )
        if error:
            _fail_result(row, error)
        else:
            content = generation.content or ""
            row.generated_response = content
            row.latency_ms = generation.latency_ms
            row.input_tokens = generation.input_tokens
            row.output_tokens = generation.output_tokens
            case = {
                "input": row.input,
                "actual_output": content,
                "expected_output": row.expected_output,
                "context": row.context or [],
            }
            metric_results = [
                evaluate_metric(definition, case=case, judge=judge)
                for definition in definitions
            ]
            row.metric_results = metric_results
            row.scores = {
                item["metric"]: item["score"]
                for item in metric_results
                if item["score"] is not None
            }
            row.status = EvaluationResult.Status.SUCCEEDED
            row.error = None
            row.save(
                update_fields=[
                    "generated_response",
                    "latency_ms",
                    "input_tokens",
                    "output_tokens",
                    "metric_results",
                    "scores",
                    "status",
                    "error",
                    "updated_at",
                ]
            )

        Evaluation.objects.filter(pk=evaluation.pk).update(
            completed_cases=F("completed_cases") + 1,
            failed_cases=F("failed_cases")
            + (1 if row.status == EvaluationResult.Status.FAILED else 0),
        )
        evaluation.refresh_from_db(fields=["completed_cases", "failed_cases"])

    summary = _model_summary(model_row, rows)
    model_row.summary = summary
    model_row.status = (
        EvaluationModel.Status.COMPLETED
        if summary["succeeded"]
        else EvaluationModel.Status.FAILED
    )
    model_row.save(update_fields=["status", "summary"])
    return summary


def _finalize(evaluation: Evaluation, model_summaries: list[dict], judge) -> None:
    totals = {
        "models": len(model_summaries),
        "records": evaluation.total_cases,
        "case_results": sum(
            summary["succeeded"] + summary["failed"] for summary in model_summaries
        ),
        "succeeded": sum(summary["succeeded"] for summary in model_summaries),
        "failed": sum(summary["failed"] for summary in model_summaries),
    }
    succeeded = totals["succeeded"] > 0
    evaluation.completed_cases = totals["succeeded"] + totals["failed"]
    evaluation.failed_cases = totals["failed"]
    evaluation.status = (
        Evaluation.Status.COMPLETED if succeeded else Evaluation.Status.FAILED
    )
    evaluation.error = (
        None
        if succeeded
        else {
            "category": "all_cases_failed",
            "message": "No model produced a successful result. Inspect the per-case errors.",
        }
    )
    evaluation.summary = {
        "metrics": evaluation.metrics,
        "models": model_summaries,
        "totals": totals,
        "judge": (
            {
                "provider_name": evaluation.judge_provider_name,
                "model_id": evaluation.judge_model_id,
            }
            if evaluation.judge_model_id
            else None
        ),
        "judge_calls": getattr(judge, "calls", 0) if judge is not None else 0,
    }
    evaluation.completed_at = timezone.now()
    evaluation.save(
        update_fields=[
            "completed_cases",
            "failed_cases",
            "status",
            "error",
            "summary",
            "completed_at",
        ]
    )


def execute_evaluation(*, evaluation_id, task_id: str = "") -> dict:
    """Run a queued evaluation. Safe to re-invoke for a finished run."""
    evaluation = (
        Evaluation.objects.select_related("project", "judge_provider")
        .filter(pk=evaluation_id)
        .first()
    )
    if evaluation is None:
        return {"evaluation": str(evaluation_id), "status": "missing"}
    if evaluation.status in TERMINAL_STATUSES:
        return {"evaluation": str(evaluation.pk), "status": evaluation.status}

    evaluation.status = Evaluation.Status.RUNNING
    evaluation.started_at = timezone.now()
    evaluation.error = None
    if task_id:
        evaluation.task_id = str(task_id)[:200]
    evaluation.save(update_fields=["status", "started_at", "error", "task_id"])

    judge = None
    try:
        definitions = resolve_metrics(evaluation.metrics)
        judge = _build_judge(evaluation, definitions)
        model_summaries = []
        for model_row in evaluation.models.select_related("provider").order_by("position"):
            model_summaries.append(
                _run_model(evaluation, model_row, definitions, judge)
            )
        _finalize(evaluation, model_summaries, judge)
    except Exception:  # noqa: BLE001 - the run must always reach a terminal state
        _mark_failed(
            evaluation.pk,
            {
                "category": "evaluation_error",
                "message": "The evaluation stopped unexpectedly. Start a new run to retry.",
            },
        )
    evaluation.refresh_from_db()
    return {"evaluation": str(evaluation.pk), "status": evaluation.status}


@transaction.atomic
def rerun_evaluation(*, actor, evaluation_id) -> Evaluation:
    """Create a new evaluation from a previous run's frozen case snapshots."""
    source = evaluation_for_user(actor, evaluation_id, Membership.Role.MEMBER)
    project = project_for_user(actor, source.project_id, Membership.Role.MEMBER)
    model_rows = list(source.models.select_related("provider").order_by("position"))
    if not model_rows:
        raise ValidationError({"evaluation": "This evaluation has no models to rerun."})
    if any(row.provider_id is None for row in model_rows):
        raise ValidationError(
            {"evaluation": "A provider used by this evaluation no longer exists."}
        )
    template_rows = list(
        source.results.filter(model=model_rows[0]).order_by("record_position")
    )
    if not template_rows:
        raise ValidationError({"evaluation": "This evaluation has no cases to rerun."})

    evaluation = Evaluation.objects.create(
        project=project,
        dataset=source.dataset,
        dataset_name=source.dataset_name,
        dataset_version=source.dataset_version,
        metrics=source.metrics,
        metric_options=source.metric_options,
        parameters=source.parameters,
        judge_provider=source.judge_provider,
        judge_provider_name=source.judge_provider_name,
        judge_model_id=source.judge_model_id,
        judge_parameters=source.judge_parameters,
        total_cases=len(template_rows),
        created_by=actor,
    )
    new_models = [
        EvaluationModel.objects.create(
            evaluation=evaluation,
            position=row.position,
            provider=row.provider,
            provider_name=row.provider_name,
            provider_kind=row.provider_kind,
            model_id=row.model_id,
            parameters=row.parameters,
        )
        for row in model_rows
    ]
    EvaluationResult.objects.bulk_create(
        [
            EvaluationResult(
                evaluation=evaluation,
                model=new_model,
                record_position=template.record_position,
                input=template.input,
                expected_output=template.expected_output,
                context=template.context or [],
            )
            for new_model in new_models
            for template in template_rows
        ]
    )
    return evaluation
