"""Playground execution services.

Design rules for M4:
- Prompts and settings are snapshotted on the execution before any provider is
  called, so later prompt edits can never rewrite history.
- Each selected model gets its own result row. A failure in one model is stored
  as that model's result and never discards the other model's response.
- Provider calls reuse the M3 adapters through ``adapter_for``; no vendor SDK or
  hardcoded response is used here.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.observability.models import Trace
from apps.observability.services import record_model_call
from apps.playground.models import Execution, ExecutionResult
from apps.prompts.services import project_for_user, prompt_for_user
from apps.providers.models import ProviderConfig
from apps.providers.services import adapter_for
from apps.workspaces.models import Membership
from apps.workspaces.permissions import require_membership
from common.exceptions import ServiceUnavailable
from integrations.providers.base import GenerationRequest
from integrations.telemetry.tracing import model_call_span

MAX_PROMPT_LENGTH = 20_000


def _clean_error(exc: Exception) -> dict[str, str]:
    """Describe a pre-call failure without echoing secrets or raw payloads."""
    if isinstance(exc, ValidationError):
        detail = exc.detail
        if isinstance(detail, dict):
            message = "; ".join(
                f"{key}: {value[0] if isinstance(value, list) and value else value}"
                for key, value in detail.items()
            )
        else:
            message = str(detail)
        return {"category": "invalid_provider", "message": message[:400]}
    if isinstance(exc, ServiceUnavailable):
        return {"category": "service_unavailable", "message": str(exc.detail)[:400]}
    if isinstance(exc, ValueError):
        return {"category": "invalid_request", "message": str(exc)[:400]}
    return {
        "category": "provider_error",
        "message": "The provider call failed unexpectedly.",
    }


def _prepare(provider, model_id, model_parameters, position):
    """Build the adapter on the request thread; decryption touches the DB."""
    started_at = timezone.now()
    started = time.monotonic()
    adapter = None
    error = None
    try:
        adapter = adapter_for(provider)
    except (ValidationError, ServiceUnavailable, ValueError) as exc:
        error = _clean_error(exc)
    ended_at = timezone.now()
    return {
        "position": position,
        "provider": provider,
        "adapter": adapter,
        "model_id": model_id,
        "model_parameters": model_parameters,
        "error": error,
        "prepare_started_at": started_at,
        "prepare_ended_at": ended_at,
        "prepare_ms": round((time.monotonic() - started) * 1000, 2),
    }


def _generate(item, messages, parameters):
    timing = {
        "started_at": None,
        "ended_at": None,
        "duration_ms": None,
        "otel_trace_id": "",
    }
    if item["error"]:
        return item, None, item["error"], timing

    started_at = timezone.now()
    started = time.monotonic()
    result = None
    error = None
    try:
        with model_call_span(
            "provider.generate",
            attributes={
                "gen_ai.provider.name": item["provider"].kind,
                "gen_ai.request.model": item["model_id"],
            },
        ) as span:
            try:
                result = item["adapter"].generate(
                    GenerationRequest(
                        model_id=item["model_id"],
                        messages=messages,
                        parameters=parameters,
                    )
                )
            except Exception:  # noqa: BLE001 - never leak provider SDK details
                error = {
                    "category": "provider_error",
                    "message": "The provider call failed unexpectedly.",
                }
            if error:
                span.record_error(error)
            elif result is not None and result.error:
                span.record_error(result.error)
            timing["otel_trace_id"] = span.trace_id
    finally:
        ended_at = timezone.now()
        timing["started_at"] = started_at
        timing["ended_at"] = ended_at
        timing["duration_ms"] = round((time.monotonic() - started) * 1000, 2)

    if error is None and result is not None and result.error:
        error = {
            "category": str(result.error.get("category", "provider_error"))[:80],
            "message": str(result.error.get("message", "Provider call failed."))[:400],
        }
    if error is not None:
        # Match the existing contract: a failed call has no usable result row.
        result = None
    return item, result, error, timing


def _persist(
    *,
    actor,
    project,
    prompt,
    prompt_version,
    mode,
    system_prompt,
    user_prompt,
    parameters,
    entries,
):
    succeeded = sum(
        1 for entry in entries if entry["status"] == ExecutionResult.Status.SUCCEEDED
    )
    if succeeded == len(entries):
        status = Execution.Status.SUCCEEDED
    elif succeeded == 0:
        status = Execution.Status.FAILED
    else:
        status = Execution.Status.PARTIAL

    with transaction.atomic():
        execution = Execution.objects.create(
            project=project,
            prompt=prompt,
            prompt_version=prompt_version,
            mode=mode,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            parameters=parameters,
            status=status,
            created_by=actor,
        )
        result_rows = ExecutionResult.objects.bulk_create(
            [
                ExecutionResult(
                    execution=execution,
                    position=entry["position"],
                    provider=entry["provider"],
                    provider_name=entry["provider"].name,
                    provider_kind=entry["provider"].kind,
                    model_id=entry["model_id"],
                    content=(entry["result"].content or "") if entry["result"] else "",
                    input_tokens=entry["result"].input_tokens if entry["result"] else None,
                    output_tokens=entry["result"].output_tokens if entry["result"] else None,
                    tokens_are_provider_reported=(
                        entry["result"].tokens_are_provider_reported
                        if entry["result"]
                        else False
                    ),
                    latency_ms=entry["result"].latency_ms if entry["result"] else None,
                    finish_reason=(
                        (entry["result"].finish_reason or "")[:80]
                        if entry["result"]
                        else ""
                    ),
                    request_id=(
                        str(entry["result"].request_id)[:200]
                        if entry["result"] and entry["result"].request_id
                        else ""
                    ),
                    # Providers in M3 report no pricing, so cost stays unknown
                    # rather than being fabricated.
                    estimated_cost=None,
                    cost_currency="",
                    status=(
                        ExecutionResult.Status.SUCCEEDED
                        if entry["result"]
                        else ExecutionResult.Status.FAILED
                    ),
                    error=entry["error"],
                )
                for entry in entries
            ]
        )
        by_position = {row.position: row for row in result_rows}
        for entry in entries:
            _record_entry_trace(
                project=project,
                mode=mode,
                entry=entry,
                result_row=by_position[entry["position"]],
            )
    return execution


def _record_entry_trace(*, project, mode, entry, result_row):
    """Persist the trace for one model call, including its span tree."""
    item = entry["item"]
    timing = entry["timing"]
    spans = [
        {
            "name": "provider.prepare",
            "kind": "internal",
            "status": "error" if item["error"] else "ok",
            "started_at": item["prepare_started_at"],
            "ended_at": item["prepare_ended_at"],
            "duration_ms": item["prepare_ms"],
            "attributes": {
                "provider.kind": item["provider"].kind,
                "provider.name": item["provider"].name,
                "gen_ai.request.model": item["model_id"],
            },
            "error": item["error"],
        }
    ]
    if not item["error"]:
        result = entry["result"]
        generate_ms = timing["duration_ms"]
        if result is not None and result.latency_ms is not None:
            generate_ms = result.latency_ms
        spans.append(
            {
                "name": "provider.generate",
                "kind": "client",
                "status": "error" if entry["error"] else "ok",
                "started_at": timing["started_at"],
                "ended_at": timing["ended_at"],
                "duration_ms": generate_ms,
                "attributes": {
                    "gen_ai.request.model": item["model_id"],
                    "gen_ai.usage.input_tokens": (
                        result.input_tokens if result else None
                    ),
                    "gen_ai.usage.output_tokens": (
                        result.output_tokens if result else None
                    ),
                    "finish_reason": result.finish_reason if result else None,
                    "request_id": result.request_id if result else None,
                },
                "error": entry["error"],
            }
        )

    started_at = item["prepare_started_at"]
    ended_at = timing["ended_at"] or item["prepare_ended_at"]
    duration_ms = max((ended_at - started_at).total_seconds() * 1000, 0.0)
    record_model_call(
        project=project,
        source=Trace.Source.PLAYGROUND,
        role=Trace.Role.MODEL,
        provider=item["provider"],
        provider_name=item["provider"].name,
        provider_kind=item["provider"].kind,
        model_id=item["model_id"],
        status=(
            Trace.Status.SUCCEEDED if entry["result"] else Trace.Status.FAILED
        ),
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        provider_latency_ms=(
            entry["result"].latency_ms
            if entry["result"] is not None
            else timing["duration_ms"]
        ),
        input_tokens=(
            entry["result"].input_tokens if entry["result"] else None
        ),
        output_tokens=(
            entry["result"].output_tokens if entry["result"] else None
        ),
        error=entry["error"],
        attributes={"mode": mode, "model_position": entry["position"]},
        otel_trace_id=timing["otel_trace_id"],
        execution_result=result_row,
        spans=spans,
    )


def _run(*, actor, project, snapshot, selections):
    prepared = [
        _prepare(provider, model_id, model_parameters, position)
        for position, (provider, model_id, model_parameters) in enumerate(selections)
    ]

    messages = []
    if snapshot["system_prompt"].strip():
        messages.append({"role": "system", "content": snapshot["system_prompt"]})
    messages.append({"role": "user", "content": snapshot["user_prompt"]})

    def parameters_for(item):
        return {
            **(item["provider"].settings or {}),
            **(snapshot["parameters"] or {}),
            **(item["model_parameters"] or {}),
        }

    with ThreadPoolExecutor(max_workers=len(prepared)) as pool:
        futures = [
            pool.submit(_generate, item, messages, parameters_for(item))
            for item in prepared
        ]
        outcomes = [future.result() for future in futures]

    entries = [
        {
            "position": item["position"],
            "provider": item["provider"],
            "model_id": item["model_id"],
            "item": item,
            "result": result,
            "error": error,
            "timing": timing,
            "status": (
                ExecutionResult.Status.SUCCEEDED
                if result
                else ExecutionResult.Status.FAILED
            ),
        }
        for item, result, error, timing in outcomes
    ]
    entries.sort(key=lambda entry: entry["position"])
    return _persist(
        actor=actor,
        project=project,
        prompt=snapshot["prompt"],
        prompt_version=snapshot["prompt_version"],
        mode=snapshot["mode"],
        system_prompt=snapshot["system_prompt"],
        user_prompt=snapshot["user_prompt"],
        parameters=snapshot["parameters"],
        entries=entries,
    )


def _selections(project, models):
    providers = {
        provider.pk: provider
        for provider in ProviderConfig.objects.filter(
            pk__in=[item["provider"] for item in models], project=project
        )
    }
    resolved = []
    for item in models:
        provider = providers.get(item["provider"])
        if provider is None:
            raise ValidationError(
                {"models": "A selected provider does not belong to this project."}
            )
        resolved.append((provider, item["model_id"], item.get("parameters") or {}))
    return resolved


def create_execution(*, actor, project_id, validated_data):
    # Deliberately not wrapped in a transaction: provider calls are slow and
    # only the final snapshot/result write needs atomicity (see _persist).
    project = project_for_user(actor, project_id, Membership.Role.MEMBER)
    system_prompt = validated_data.get("system_prompt") or ""
    user_prompt = validated_data["user_prompt"]
    if len(system_prompt) > MAX_PROMPT_LENGTH or len(user_prompt) > MAX_PROMPT_LENGTH:
        raise ValidationError({"user_prompt": "Prompts may be at most 20000 characters."})

    prompt = None
    prompt_version = None
    prompt_id = validated_data.get("prompt")
    if prompt_id:
        prompt = prompt_for_user(actor, prompt_id, Membership.Role.VIEWER)
        if prompt.project_id != project.id:
            raise NotFound("Prompt not found.")
        latest = prompt.versions.order_by("-version_number").first()
        prompt_version = latest.version_number if latest else None

    selections = _selections(project, validated_data["models"])
    snapshot = {
        "prompt": prompt,
        "prompt_version": prompt_version,
        "mode": (
            Execution.Mode.COMPARE if len(selections) == 2 else Execution.Mode.SINGLE
        ),
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "parameters": validated_data.get("parameters") or {},
    }
    return _run(actor=actor, project=project, snapshot=snapshot, selections=selections)


def execution_for_user(user, execution_id):
    execution = (
        Execution.objects.select_related("project", "project__workspace")
        .prefetch_related("results")
        .filter(pk=execution_id)
        .first()
    )
    if execution is None:
        raise NotFound("Execution not found.")
    require_membership(user, execution.project.workspace_id, Membership.Role.VIEWER)
    return execution


def list_executions(*, user, project_id, limit=50):
    project = project_for_user(user, project_id, Membership.Role.VIEWER)
    return (
        Execution.objects.filter(project=project)
        .prefetch_related("results")
        .order_by("-created_at")[:limit]
    )


def rerun_execution(*, actor, execution_id):
    """Replay a stored experiment under its original prompts and settings."""
    source = execution_for_user(actor, execution_id)
    project = project_for_user(actor, source.project_id, Membership.Role.MEMBER)
    selections = []
    for result in source.results.all().order_by("position"):
        if result.provider_id is None:
            raise ValidationError(
                {"models": "A provider used by this execution no longer exists."}
            )
        selections.append((result.provider, result.model_id, {}))
    if not selections:
        raise ValidationError({"models": "This execution has no model results to rerun."})

    snapshot = {
        "prompt": None,
        "prompt_version": source.prompt_version,
        "mode": source.mode,
        "system_prompt": source.system_prompt,
        "user_prompt": source.user_prompt,
        "parameters": source.parameters or {},
    }
    return _run(actor=actor, project=project, snapshot=snapshot, selections=selections)
