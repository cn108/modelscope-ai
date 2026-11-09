"""Playground execution services.

Design rules for M4:
- Prompts and settings are snapshotted on the execution before any provider is
  called, so later prompt edits can never rewrite history.
- Each selected model gets its own result row. A failure in one model is stored
  as that model's result and never discards the other model's response.
- Provider calls reuse the M3 adapters through ``adapter_for``; no vendor SDK or
  hardcoded response is used here.
"""

from concurrent.futures import ThreadPoolExecutor

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from apps.playground.models import Execution, ExecutionResult
from apps.prompts.services import project_for_user, prompt_for_user
from apps.providers.models import ProviderConfig
from apps.providers.services import adapter_for
from apps.workspaces.models import Membership
from apps.workspaces.permissions import require_membership
from common.exceptions import ServiceUnavailable
from integrations.providers.base import GenerationRequest

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
    try:
        adapter = adapter_for(provider)
    except (ValidationError, ServiceUnavailable, ValueError) as exc:
        return {
            "position": position,
            "provider": provider,
            "adapter": None,
            "model_id": model_id,
            "model_parameters": model_parameters,
            "error": _clean_error(exc),
        }
    return {
        "position": position,
        "provider": provider,
        "adapter": adapter,
        "model_id": model_id,
        "model_parameters": model_parameters,
        "error": None,
    }


def _generate(item, messages, parameters):
    if item["error"]:
        return item, None, item["error"]
    try:
        result = item["adapter"].generate(
            GenerationRequest(
                model_id=item["model_id"], messages=messages, parameters=parameters
            )
        )
    except Exception:  # noqa: BLE001 - never leak provider SDK/transport details
        return item, None, {
            "category": "provider_error",
            "message": "The provider call failed unexpectedly.",
        }
    if result.error:
        return item, None, {
            "category": str(result.error.get("category", "provider_error"))[:80],
            "message": str(result.error.get("message", "Provider call failed."))[:400],
        }
    return item, result, None


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
        ExecutionResult.objects.bulk_create(
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
    return execution


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
            "result": result,
            "error": error,
            "status": (
                ExecutionResult.Status.SUCCEEDED
                if result
                else ExecutionResult.Status.FAILED
            ),
        }
        for item, result, error in outcomes
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
