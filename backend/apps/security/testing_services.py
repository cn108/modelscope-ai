"""Controlled AI security testing: orchestration, classification and summaries.

M9 reuses the existing provider adapter and encrypted credential path.  It does
not accept arbitrary prompts, endpoints or external targets: a run can only
select reviewed cases from the registry and models configured in the project.
"""

from __future__ import annotations

import logging
from collections import Counter
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.projects.services import project_for_user
from apps.prompts.serializers import validate_parameters
from apps.providers.models import ModelConfig, ProviderConfig
from apps.providers.services import generate_observed
from apps.workspaces.models import Membership
from apps.workspaces.permissions import require_membership
from integrations.security.base import SEVERITY_RANK
from integrations.security_testing import registry
from integrations.security_testing.base import FAILED, INCONCLUSIVE, PASSED, RenderedCase
from integrations.security_testing.cases import CASES_BY_KEY
from integrations.security_testing.detectors import classify, severity_for

from .models import (
    SecuritySeverity,
    SecurityTestModel,
    SecurityTestResult,
    SecurityTestRun,
)

TERMINAL_STATUSES = (SecurityTestRun.Status.COMPLETED, SecurityTestRun.Status.FAILED)
SEVERITY_ORDER = [value for value, _ in SecuritySeverity.choices]
MAX_MODELS = max(int(getattr(settings, "SECURITY_TEST_MAX_MODELS", 5) or 5), 1)
MAX_RESULTS = max(int(getattr(settings, "SECURITY_TEST_MAX_RESULTS", 120) or 120), 1)
logger = logging.getLogger(__name__)


def _project(actor, project_id):
    return project_for_user(actor, project_id, Membership.Role.VIEWER)


def run_for_user(user, run_id, minimum_role=Membership.Role.VIEWER) -> SecurityTestRun:
    run = (
        SecurityTestRun.objects.select_related(
            "project", "project__workspace", "created_by"
        )
        .prefetch_related("models")
        .filter(pk=run_id)
        .first()
    )
    if run is None:
        raise NotFound("Security test run not found.")
    require_membership(user, run.project.workspace_id, minimum_role)
    return run


def result_for_user(user, result_id) -> SecurityTestResult:
    result = (
        SecurityTestResult.objects.select_related(
            "run", "run__project", "run__project__workspace", "model"
        )
        .filter(pk=result_id)
        .first()
    )
    if result is None:
        raise NotFound("Security test result not found.")
    require_membership(user, result.run.project.workspace_id, Membership.Role.VIEWER)
    return result


def list_runs(*, user, project_id, status=None, limit=100):
    project = _project(user, project_id)
    rows = SecurityTestRun.objects.filter(project=project).select_related(
        "created_by"
    ).prefetch_related("models")
    if status in SecurityTestRun.Status.values:
        rows = rows.filter(status=status)
    return rows.order_by("-created_at")[:limit]


def list_results(
    *,
    user,
    run_id,
    model_id=None,
    category=None,
    verdict=None,
    status=None,
    limit=500,
):
    run = run_for_user(user, run_id)
    rows = SecurityTestResult.objects.filter(run=run).select_related("model")
    if model_id:
        rows = rows.filter(model_id=model_id)
    if category:
        rows = rows.filter(category=category[:64])
    if verdict in SecurityTestResult.Verdict.values:
        rows = rows.filter(verdict=verdict)
    if status in SecurityTestResult.Status.values:
        rows = rows.filter(status=status)
    return rows.order_by("model__position", "category", "case_key")[:limit]


def _resolve_models(project, selections) -> list[tuple[ProviderConfig, str, dict]]:
    if not 1 <= len(selections) <= MAX_MODELS:
        raise ValidationError(
            {"models": f"Select between 1 and {MAX_MODELS} models."}
        )
    seen = set()
    for item in selections:
        key = (str(item["provider"]), item["model_id"].strip())
        if key in seen:
            raise ValidationError({"models": "Each selected model must be different."})
        seen.add(key)
    providers = {
        provider.pk: provider
        for provider in ProviderConfig.objects.filter(
            pk__in=[item["provider"] for item in selections], project=project
        )
    }
    configured = set(
        ModelConfig.objects.filter(
            provider_id__in=providers.keys(),
            model_id__in=[item["model_id"].strip() for item in selections],
        ).values_list("provider_id", "model_id")
    )
    resolved = []
    for item in selections:
        provider = providers.get(item["provider"])
        if provider is None:
            raise ValidationError(
                {"models": "A selected provider does not belong to this project."}
            )
        model_id = item["model_id"].strip()
        if not model_id:
            raise ValidationError({"models": "A model id is required for each model."})
        if (provider.pk, model_id) not in configured:
            raise ValidationError(
                {
                    "models": (
                        f"Model '{model_id}' is not configured for provider "
                        f"'{provider.name}'. Add or discover it before testing."
                    )
                }
            )
        resolved.append((provider, model_id, item.get("parameters") or {}))
    return resolved


def _case_keys(validated_data) -> tuple[str, ...]:
    raw_cases = validated_data.get("cases") or []
    raw_categories = validated_data.get("categories") or []
    try:
        if raw_cases:
            keys = registry.validate_cases(raw_cases)
            if raw_categories:
                allowed = set(registry.cases_for_categories(raw_categories))
                keys = tuple(key for key in keys if key in allowed)
        elif raw_categories:
            keys = registry.cases_for_categories(raw_categories)
        else:
            raise ValueError("Select at least one security test case or category.")
    except ValueError as exc:
        raise ValidationError({"cases": str(exc)}) from exc
    if not keys:
        raise ValidationError({"cases": "Select at least one security test case."})
    return keys


def _rendered_result(case) -> dict:
    return {
        "case_key": case.key,
        "case_name": case.name,
        "category": case.category,
        "category_label": case.category_label,
        "technique": case.technique,
        "system_prompt": case.system_prompt,
        "attack_input": case.prompt,
        "detector": case.detector,
        "detector_config": case.detector_config,
        "severity": case.severity,
        "criteria": case.criteria,
        "mitigation": case.mitigation,
        "references": list(case.references),
        "canary": case.canary,
    }


@transaction.atomic
def create_run(*, actor, project_id, validated_data) -> SecurityTestRun:
    project = project_for_user(actor, project_id, Membership.Role.MEMBER)
    case_keys = _case_keys(validated_data)
    selections = _resolve_models(project, validated_data["models"])
    parameters = validate_parameters(validated_data.get("parameters") or {})
    if len(selections) * len(case_keys) > MAX_RESULTS:
        raise ValidationError(
            {
                "cases": (
                    f"This run would create {len(selections) * len(case_keys)} results; "
                    f"the limit is {MAX_RESULTS}. Select fewer cases or models."
                )
            }
        )
    categories = list(
        dict.fromkeys(CASES_BY_KEY[key].category for key in case_keys)
    )
    run = SecurityTestRun.objects.create(
        project=project,
        case_keys=list(case_keys),
        categories=categories,
        parameters=parameters,
        total_models=len(selections),
        total_cases=len(case_keys),
        total_results=len(selections) * len(case_keys),
        created_by=actor,
    )
    model_rows = [
        SecurityTestModel.objects.create(
            run=run,
            position=position,
            provider=provider,
            provider_name=provider.name,
            provider_kind=provider.kind,
            model_id=model_id,
            parameters=model_parameters,
        )
        for position, (provider, model_id, model_parameters) in enumerate(selections)
    ]
    results = []
    for model_row in model_rows:
        for case_key in case_keys:
            case = registry.render_case(CASES_BY_KEY[case_key], registry.canary_token())
            results.append(
                SecurityTestResult(
                    run=run,
                    model=model_row,
                    **{
                        **_rendered_result(case),
                        "case_key": case.key,
                        "status": SecurityTestResult.Status.PENDING,
                    },
                )
            )
    SecurityTestResult.objects.bulk_create(results)
    return run


def _mark_failed(run: SecurityTestRun, category: str, message: str) -> None:
    now = timezone.now()
    SecurityTestRun.objects.filter(pk=run.pk).exclude(
        status__in=TERMINAL_STATUSES
    ).update(
        status=SecurityTestRun.Status.FAILED,
        error={"category": category, "message": message},
        completed_at=now,
    )
    SecurityTestModel.objects.filter(run=run).exclude(
        status=SecurityTestModel.Status.COMPLETED
    ).update(status=SecurityTestModel.Status.FAILED, error={"category": category, "message": message})
    SecurityTestResult.objects.filter(
        run=run, status=SecurityTestResult.Status.PENDING
    ).update(
        status=SecurityTestResult.Status.FAILED,
        verdict=SecurityTestResult.Verdict.INCONCLUSIVE,
        error={"category": category, "message": message},
        rationale="The run stopped before this case could be evaluated.",
        executed_at=now,
    )
    run.refresh_from_db()


def enqueue_run(run: SecurityTestRun) -> SecurityTestRun:
    from .tasks import run_security_test

    try:
        async_result = run_security_test.delay(str(run.pk))
    except Exception:  # noqa: BLE001 - broker failures stay visible to the user
        _mark_failed(
            run,
            "queue_unavailable",
            "The security test could not be queued. Check the worker and broker.",
        )
        return run
    task_id = getattr(async_result, "id", None)
    if task_id:
        SecurityTestRun.objects.filter(
            pk=run.pk, status=SecurityTestRun.Status.QUEUED
        ).update(task_id=str(task_id)[:200])
    run.refresh_from_db()
    return run


def _summary(rows: list[SecurityTestResult]) -> dict:
    total = len(rows)
    passed = sum(1 for row in rows if row.verdict == PASSED)
    failed = sum(1 for row in rows if row.verdict == FAILED)
    inconclusive = sum(1 for row in rows if row.verdict == INCONCLUSIVE)
    errors = sum(1 for row in rows if row.status == SecurityTestResult.Status.FAILED)
    decisive = passed + failed
    severity_counts = {value: 0 for value in SEVERITY_ORDER}
    category_counts: dict[str, dict] = {}
    for row in rows:
        if row.verdict == FAILED and row.severity:
            severity_counts[row.severity] = severity_counts.get(row.severity, 0) + 1
        bucket = category_counts.setdefault(
            row.category,
            {
                "category": row.category,
                "label": row.category_label,
                "total": 0,
                "passed": 0,
                "failed": 0,
                "inconclusive": 0,
            },
        )
        bucket["total"] += 1
        if row.verdict in {PASSED, FAILED, INCONCLUSIVE}:
            bucket[row.verdict] += 1
    highest = ""
    for value in SEVERITY_ORDER:
        if severity_counts.get(value):
            highest = value
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "inconclusive": inconclusive,
        "vulnerabilities": failed,
        "errors": errors,
        "decisive": decisive,
        "pass_rate": round(passed / decisive, 4) if decisive else None,
        "fail_rate": round(failed / decisive, 4) if decisive else None,
        "coverage": round(decisive / total, 4) if total else 0,
        "severity_counts": severity_counts,
        "highest_severity": highest,
        "categories": sorted(category_counts.values(), key=lambda item: item["category"]),
    }


def _model_key(row: SecurityTestModel) -> str:
    return "::".join(
        [
            str(row.provider_id) if row.provider_id else "none",
            row.provider_name,
            row.provider_kind,
            row.model_id,
        ]
    )


def _model_summary(row: SecurityTestModel, rows: list[SecurityTestResult]) -> dict:
    summary = _summary(rows)
    return {
        "id": str(row.pk),
        "position": row.position,
        "provider": str(row.provider_id) if row.provider_id else None,
        "provider_name": row.provider_name,
        "provider_kind": row.provider_kind,
        "model_id": row.model_id,
        "parameters": row.parameters,
        "status": row.status,
        **summary,
    }


def _run_summary(run: SecurityTestRun, model_summaries: list[dict]) -> dict:
    rows = list(SecurityTestResult.objects.filter(run=run))
    overall = _summary(rows)
    return {
        "totals": {
            key: overall[key]
            for key in (
                "total",
                "passed",
                "failed",
                "inconclusive",
                "vulnerabilities",
                "errors",
                "decisive",
                "pass_rate",
                "fail_rate",
                "coverage",
            )
        },
        "severity_counts": overall["severity_counts"],
        "highest_severity": overall["highest_severity"],
        "categories": overall["categories"],
        "models": model_summaries,
        "cases": len(run.case_keys or []),
        "limitations": registry.catalog()["limitations"],
    }


def _rendered_from_result(result: SecurityTestResult) -> RenderedCase:
    return RenderedCase(
        key=result.case_key,
        category=result.category,
        category_label=result.category_label,
        name=result.case_name,
        description="",
        technique=result.technique,
        severity=result.severity,
        system_prompt=result.system_prompt,
        prompt=result.attack_input,
        detector=result.detector,
        detector_config=result.detector_config or {},
        criteria=result.criteria,
        mitigation=result.mitigation,
        references=tuple(result.references or []),
        canary=result.canary,
    )


def _execute_result(*, result: SecurityTestResult, provider, parameters) -> None:
    result.status = SecurityTestResult.Status.FAILED
    result.error = None
    messages = []
    if result.system_prompt.strip():
        messages.append({"role": "system", "content": result.system_prompt})
    messages.append({"role": "user", "content": result.attack_input})
    generation, error, timing = generate_observed(
        provider=provider,
        model_id=result.model.model_id,
        messages=messages,
        parameters=parameters,
    )
    now = timezone.now()
    result.executed_at = now
    if error:
        result.error = error
        result.verdict = SecurityTestResult.Verdict.INCONCLUSIVE
        result.severity = ""
        result.rationale = (
            "The provider call failed, so the model response could not be evaluated."
        )
        result.evidence = ""
        result.matched_rules = ["provider_error"]
        result.duration_ms = timing.get("duration_ms")
        result.save(
            update_fields=[
                "status",
                "verdict",
                "severity",
                "rationale",
                "evidence",
                "matched_rules",
                "error",
                "duration_ms",
                "executed_at",
                "updated_at",
            ]
        )
        return

    content = generation.content or ""
    result.response_text = content
    result.status = SecurityTestResult.Status.SUCCEEDED
    result.duration_ms = (
        generation.latency_ms
        if generation.latency_ms is not None
        else timing.get("duration_ms")
    )
    result.input_tokens = generation.input_tokens
    result.output_tokens = generation.output_tokens
    result.provider_request_id = str(generation.request_id or "")[:200]
    outcome = classify(_rendered_from_result(result), content, error=None)
    result.verdict = outcome.verdict
    result.rationale = outcome.rationale
    result.evidence = outcome.evidence
    result.matched_rules = list(outcome.matched_rules)
    result.severity = severity_for(_rendered_from_result(result), outcome)
    result.save(
        update_fields=[
            "response_text",
            "status",
            "verdict",
            "severity",
            "rationale",
            "evidence",
            "matched_rules",
            "duration_ms",
            "input_tokens",
            "output_tokens",
            "provider_request_id",
            "executed_at",
            "updated_at",
        ]
    )


def execute_run(*, run_id, task_id: str = "") -> dict:
    """Execute a queued run. Every model/case result records an actual response."""
    run = (
        SecurityTestRun.objects.select_related("project")
        .filter(pk=run_id)
        .first()
    )
    if run is None:
        return {"run": str(run_id), "status": "missing"}
    if run.status in TERMINAL_STATUSES:
        return {"run": str(run.pk), "status": run.status}

    run.status = SecurityTestRun.Status.RUNNING
    run.started_at = timezone.now()
    run.error = None
    if task_id:
        run.task_id = str(task_id)[:200]
    run.save(update_fields=["status", "started_at", "error", "task_id"])

    model_summaries = []
    try:
        for model_row in run.models.select_related("provider").order_by("position"):
            if model_row.provider_id is None or model_row.provider is None:
                error = {
                    "category": "provider_missing",
                    "message": "The provider used by this model no longer exists.",
                }
                rows = list(model_row.results.all())
                for result in rows:
                    result.status = SecurityTestResult.Status.FAILED
                    result.verdict = SecurityTestResult.Verdict.INCONCLUSIVE
                    result.error = error
                    result.rationale = error["message"]
                    result.matched_rules = ["provider_missing"]
                    result.executed_at = timezone.now()
                    result.save(
                        update_fields=[
                            "status",
                            "verdict",
                            "error",
                            "rationale",
                            "matched_rules",
                            "executed_at",
                            "updated_at",
                        ]
                    )
                model_row.status = SecurityTestModel.Status.FAILED
                model_row.error = error
                model_row.summary = _model_summary(model_row, rows)
                model_row.save(update_fields=["status", "error", "summary"])
                model_summaries.append(model_row.summary)
                SecurityTestRun.objects.filter(pk=run.pk).update(
                    completed_results=(
                        SecurityTestRun.objects.get(pk=run.pk).completed_results
                        + len(rows)
                    )
                )
                continue

            model_row.status = SecurityTestModel.Status.RUNNING
            model_row.save(update_fields=["status"])
            parameters = {
                **(model_row.provider.settings or {}),
                **(run.parameters or {}),
                **(model_row.parameters or {}),
            }
            rows = list(model_row.results.order_by("case_key"))
            for result in rows:
                if result.status != SecurityTestResult.Status.PENDING:
                    continue
                _execute_result(
                    result=result, provider=model_row.provider, parameters=parameters
                )
                SecurityTestRun.objects.filter(pk=run.pk).update(
                    completed_results=F("completed_results") + 1
                )
            rows = list(model_row.results.order_by("case_key"))
            succeeded = any(
                row.status == SecurityTestResult.Status.SUCCEEDED for row in rows
            )
            model_row.status = (
                SecurityTestModel.Status.COMPLETED
                if succeeded
                else SecurityTestModel.Status.FAILED
            )
            model_row.error = (
                None
                if succeeded
                else {
                    "category": "all_cases_failed",
                    "message": "No case produced a usable model response.",
                }
            )
            model_row.summary = _model_summary(model_row, rows)
            model_row.save(update_fields=["status", "summary", "error"])
            model_summaries.append(model_row.summary)

        run.refresh_from_db()
        summary = _run_summary(run, model_summaries)
        succeeded = (
            summary["totals"]["total"] > 0
            and summary["totals"]["errors"] < summary["totals"]["total"]
        )
        run.summary = summary
        run.completed_results = SecurityTestResult.objects.filter(
            run=run
        ).exclude(status=SecurityTestResult.Status.PENDING).count()
        run.status = (
            SecurityTestRun.Status.COMPLETED
            if succeeded
            else SecurityTestRun.Status.FAILED
        )
        run.error = (
            None
            if succeeded
            else {
                "category": "no_model_responses",
                "message": (
                    "No model produced a usable response. Inspect the per-case "
                    "provider errors."
                ),
            }
        )
        run.completed_at = timezone.now()
        run.save(
            update_fields=[
                "summary",
                "completed_results",
                "status",
                "error",
                "completed_at",
            ]
        )
    except Exception:  # noqa: BLE001 - the run must reach a terminal state
        logger.exception("Security test run %s failed", run.pk)
        _mark_failed(
            run,
            "security_test_error",
            "The security test stopped unexpectedly. Start a new run to retry.",
        )
    run.refresh_from_db()
    return {"run": str(run.pk), "status": run.status}


@transaction.atomic
def rerun_run(*, actor, run_id) -> SecurityTestRun:
    source = run_for_user(actor, run_id, Membership.Role.MEMBER)
    models = []
    for row in source.models.select_related("provider").order_by("position"):
        if row.provider_id is None:
            raise ValidationError(
                {"models": "A provider used by this run no longer exists."}
            )
        models.append(
            {
                "provider": row.provider_id,
                "model_id": row.model_id,
                "parameters": row.parameters or {},
            }
        )
    if not models:
        raise ValidationError({"models": "This run has no models to rerun."})
    new_run = create_run(
        actor=actor,
        project_id=source.project_id,
        validated_data={
            "models": models,
            "cases": source.case_keys,
            "categories": source.categories,
            "parameters": source.parameters,
        },
    )
    return enqueue_run(new_run)


def dashboard(*, user, project_id) -> dict:
    project = _project(user, project_id)
    runs = SecurityTestRun.objects.filter(project=project)
    results = SecurityTestResult.objects.filter(run__project=project).exclude(
        status=SecurityTestResult.Status.PENDING
    )
    summary = _summary(list(results))
    model_rows = []
    grouped: dict[str, dict] = {}
    for row in SecurityTestResult.objects.filter(run__project=project).exclude(
        status=SecurityTestResult.Status.PENDING
    ).select_related("model"):
        key = _model_key(row.model)
        bucket = grouped.setdefault(key, {"model": row.model, "rows": []})
        bucket["rows"].append(row)
    for bucket in grouped.values():
        model = bucket["model"]
        model_rows.append(
            {
                "provider": str(model.provider_id) if model.provider_id else None,
                "provider_name": model.provider_name,
                "provider_kind": model.provider_kind,
                "model_id": model.model_id,
                **_summary(bucket["rows"]),
            }
        )
    model_rows.sort(
        key=lambda item: (
            -(item["pass_rate"] if item["pass_rate"] is not None else -1),
            -item["total"],
            item["provider_name"],
            item["model_id"],
        )
    )
    recent_runs = list(runs.select_related("created_by")[:10])
    recent_failures = list(
        results.filter(verdict=SecurityTestResult.Verdict.FAILED)
        .select_related("model")
        .order_by("-executed_at")[:10]
    )
    return {
        "project": str(project.pk),
        "runs": runs.count(),
        "completed_runs": runs.filter(
            status=SecurityTestRun.Status.COMPLETED
        ).count(),
        "failed_runs": runs.filter(status=SecurityTestRun.Status.FAILED).count(),
        "running_runs": runs.filter(
            status__in=[
                SecurityTestRun.Status.QUEUED,
                SecurityTestRun.Status.RUNNING,
            ]
        ).count(),
        "tests_performed": summary["total"],
        "passed": summary["passed"],
        "failed": summary["failed"],
        "inconclusive": summary["inconclusive"],
        "vulnerabilities": summary["vulnerabilities"],
        "decisive": summary["decisive"],
        "pass_rate": summary["pass_rate"],
        "fail_rate": summary["fail_rate"],
        "coverage": summary["coverage"],
        "severity_counts": summary["severity_counts"],
        "highest_severity": summary["highest_severity"],
        "categories": summary["categories"],
        "models": model_rows,
        "recent_runs": recent_runs,
        "recent_failures": recent_failures,
        "disclaimer": registry.catalog()["disclaimer"],
        "limitations": registry.catalog()["limitations"],
    }


def _result_map(run: SecurityTestRun) -> dict:
    rows = (
        SecurityTestResult.objects.filter(run=run)
        .exclude(status=SecurityTestResult.Status.PENDING)
        .select_related("model")
    )
    return {
        (_model_key(row.model), row.case_key): row for row in rows
    }


def _run_models(run: SecurityTestRun) -> dict:
    return {_model_key(row): row for row in run.models.all()}


def compare_runs(*, user, project_id, baseline_id, current_id) -> dict:
    project = _project(user, project_id)
    baseline = run_for_user(user, baseline_id)
    current = run_for_user(user, current_id)
    if baseline.project_id != project.pk or current.project_id != project.pk:
        raise NotFound("Security test run not found.")
    if baseline.pk == current.pk:
        raise ValidationError(
            {"current": "Choose two different security test runs to compare."}
        )
    baseline_map = _result_map(baseline)
    current_map = _result_map(current)
    new_failures = []
    resolved_failures = []
    persisting = []
    changed = []
    all_keys = set(baseline_map) | set(current_map)
    for key in sorted(all_keys, key=lambda item: (item[0], item[1])):
        before = baseline_map.get(key)
        after = current_map.get(key)
        before_failed = bool(before and before.verdict == FAILED)
        after_failed = bool(after and after.verdict == FAILED)
        item = {
            "case_key": key[1],
            "model": str(after.model_id) if after else None,
            "baseline": before,
            "current": after,
        }
        if after_failed and not before_failed:
            new_failures.append(item)
        elif before_failed and not after_failed:
            resolved_failures.append(item)
        elif before_failed and after_failed:
            persisting.append(item)
        if before and after and before.verdict != after.verdict:
            changed.append(item)

    before_summary = _summary(list(baseline_map.values()))
    after_summary = _summary(list(current_map.values()))
    warnings = []
    if set(baseline.case_keys or []) != set(current.case_keys or []):
        warnings.append(
            "The runs used different case selections, so differences can come from "
            "the selection rather than the model."
        )
    if set(_run_models(baseline)) != set(_run_models(current)):
        warnings.append(
            "The runs tested different models. Compare only common models for a "
            "like-for-like result."
        )
    if (baseline.parameters or {}) != (current.parameters or {}):
        warnings.append("The inference parameters differ between the runs.")
    warnings.append(
        "Inconclusive results are excluded from pass/fail rates. A change in a "
        "heuristic detector or model version can change a verdict without a real "
        "security improvement."
    )
    return {
        "project": str(project.pk),
        "baseline": baseline,
        "current": current,
        "counts": {
            "baseline_total": before_summary["total"],
            "current_total": after_summary["total"],
            "baseline_failed": before_summary["failed"],
            "current_failed": after_summary["failed"],
            "new_failures": len(new_failures),
            "resolved_failures": len(resolved_failures),
            "persisting_failures": len(persisting),
            "changed_verdicts": len(changed),
        },
        "baseline_summary": before_summary,
        "current_summary": after_summary,
        "models": {
            "baseline": [
                _model_summary(row, list(row.results.exclude(status=SecurityTestResult.Status.PENDING)))
                for row in baseline.models.select_related("provider").order_by("position")
            ],
            "current": [
                _model_summary(row, list(row.results.exclude(status=SecurityTestResult.Status.PENDING)))
                for row in current.models.select_related("provider").order_by("position")
            ],
        },
        "warnings": warnings,
        "new_failures": new_failures,
        "resolved_failures": resolved_failures,
        "persisting": persisting,
        "changed": changed,
    }


def history(*, user, project_id, model_id=None, provider_id=None, limit=100):
    project = _project(user, project_id)
    rows = SecurityTestModel.objects.filter(run__project=project).select_related(
        "run", "provider"
    )
    if model_id:
        rows = rows.filter(model_id=model_id[:200])
    if provider_id:
        try:
            rows = rows.filter(provider_id=UUID(str(provider_id)))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"provider": "Provider must be a UUID."}) from exc
    return rows.order_by("-run__created_at", "position")[:limit]
