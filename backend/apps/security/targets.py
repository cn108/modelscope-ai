"""Adapters that expose existing resources as security scan segments.

The security app does not duplicate dataset, prompt or execution storage.  It
reads the records that already exist and labels each segment so findings can
link back to the source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from django.conf import settings
from rest_framework.exceptions import ValidationError

from apps.datasets.models import Dataset
from apps.datasets.services import dataset_for_user
from apps.playground.models import Execution
from apps.playground.services import execution_for_user
from apps.prompts.models import Prompt
from apps.prompts.services import prompt_for_user
from apps.workspaces.models import Membership

from .models import SecurityFinding, SecurityScan


@dataclass(frozen=True)
class ScanSegment:
    resource_type: str
    resource_id: str
    resource_label: str
    location: str
    kind: str
    text: str
    execution: Execution | None = None
    execution_result: object | None = None


@dataclass(frozen=True)
class ScanTarget:
    target_type: str
    target: object
    target_id: str
    target_label: str
    target_version: str
    segments: tuple[ScanSegment, ...]
    truncated: bool


def _clean_text(value) -> str:
    return str(value or "").strip()


def _dataset_segments(dataset: Dataset) -> Iterator[ScanSegment]:
    for record in dataset.records.order_by("position").iterator():
        label = f"{dataset.name} · record #{record.position}"
        resource_id = str(record.pk)
        if _clean_text(record.input):
            yield ScanSegment(
                resource_type=SecurityFinding.ResourceType.DATASET_RECORD,
                resource_id=resource_id,
                resource_label=label,
                location="input",
                kind="input",
                text=_clean_text(record.input),
            )
        if _clean_text(record.expected_output):
            yield ScanSegment(
                resource_type=SecurityFinding.ResourceType.DATASET_RECORD,
                resource_id=resource_id,
                resource_label=label,
                location="expected_output",
                kind="output",
                text=_clean_text(record.expected_output),
            )
        for index, passage in enumerate(record.context or []):
            if _clean_text(passage):
                yield ScanSegment(
                    resource_type=SecurityFinding.ResourceType.DATASET_RECORD,
                    resource_id=resource_id,
                    resource_label=label,
                    location=f"context[{index}]",
                    kind="context",
                    text=_clean_text(passage),
                )


def _prompt_segments(prompt: Prompt) -> Iterator[ScanSegment]:
    version = prompt.versions.order_by("-version_number").first()
    if version is None:
        return
    label = f"{prompt.name} · v{version.version_number}"
    resource_id = str(version.pk)
    if _clean_text(version.system_prompt):
        yield ScanSegment(
            resource_type=SecurityFinding.ResourceType.PROMPT_VERSION,
            resource_id=resource_id,
            resource_label=label,
            location="system_prompt",
            kind="system",
            text=_clean_text(version.system_prompt),
        )
    if _clean_text(version.user_prompt):
        yield ScanSegment(
            resource_type=SecurityFinding.ResourceType.PROMPT_VERSION,
            resource_id=resource_id,
            resource_label=label,
            location="user_prompt",
            kind="input",
            text=_clean_text(version.user_prompt),
        )


def _execution_segments(execution: Execution) -> Iterator[ScanSegment]:
    short = str(execution.pk)[:8]
    if _clean_text(execution.system_prompt):
        yield ScanSegment(
            resource_type=SecurityFinding.ResourceType.EXECUTION,
            resource_id=str(execution.pk),
            resource_label=f"Execution {short} · system prompt",
            location="system_prompt",
            kind="system",
            text=_clean_text(execution.system_prompt),
            execution=execution,
        )
    if _clean_text(execution.user_prompt):
        yield ScanSegment(
            resource_type=SecurityFinding.ResourceType.EXECUTION,
            resource_id=str(execution.pk),
            resource_label=f"Execution {short} · user prompt",
            location="user_prompt",
            kind="input",
            text=_clean_text(execution.user_prompt),
            execution=execution,
        )
    for result in execution.results.order_by("position").iterator():
        if not _clean_text(result.content):
            continue
        yield ScanSegment(
            resource_type=SecurityFinding.ResourceType.EXECUTION_RESULT,
            resource_id=str(result.pk),
            resource_label=(
                f"Execution {short} · {result.provider_name}:{result.model_id} response"
            ),
            location="response",
            kind="output",
            text=_clean_text(result.content),
            execution=execution,
            execution_result=result,
        )


def _segments(target_type: str, target) -> Iterator[ScanSegment]:
    if target_type == SecurityScan.TargetType.DATASET:
        yield from _dataset_segments(target)
    elif target_type == SecurityScan.TargetType.PROMPT:
        yield from _prompt_segments(target)
    elif target_type == SecurityScan.TargetType.EXECUTION:
        yield from _execution_segments(target)
    else:
        raise ValidationError({"target_type": "Unsupported security scan target."})


def collect_segments(target_type: str, target) -> tuple[tuple[ScanSegment, ...], bool]:
    """Collect a target's scan segments, stopping at the configured cap."""
    limit = max(int(getattr(settings, "SECURITY_MAX_SCAN_ITEMS", 10000)), 1)
    collected: list[ScanSegment] = []
    truncated = False
    for segment in _segments(target_type, target):
        if len(collected) >= limit:
            truncated = True
            break
        collected.append(segment)
    return tuple(collected), truncated


def resolve_target(
    *, user, project_id, target_type: str, target_id
) -> ScanTarget:
    """Resolve an existing resource and cap the number of scanned segments."""
    if target_type == SecurityScan.TargetType.DATASET:
        target = dataset_for_user(user, target_id, Membership.Role.VIEWER)
        if str(target.project_id) != str(project_id):
            raise ValidationError(
                {"target_id": "This dataset belongs to another project."}
            )
        label = target.name
        version = f"v{target.version}"
    elif target_type == SecurityScan.TargetType.PROMPT:
        target = prompt_for_user(user, target_id, Membership.Role.VIEWER)
        if str(target.project_id) != str(project_id):
            raise ValidationError(
                {"target_id": "This prompt belongs to another project."}
            )
        label = target.name
        latest = target.versions.order_by("-version_number").first()
        version = f"v{latest.version_number}" if latest else ""
        if latest is None:
            raise ValidationError({"target_id": "This prompt has no saved version."})
    elif target_type == SecurityScan.TargetType.EXECUTION:
        target = execution_for_user(user, target_id)
        if str(target.project_id) != str(project_id):
            raise ValidationError(
                {"target_id": "This execution belongs to another project."}
            )
        label = f"Execution {str(target.pk)[:8]}"
        version = ""
    else:
        raise ValidationError({"target_type": "Unsupported security scan target."})

    segments, truncated = collect_segments(target_type, target)
    return ScanTarget(
        target_type=target_type,
        target=target,
        target_id=str(target.pk),
        target_label=label,
        target_version=version,
        segments=segments,
        truncated=truncated,
    )
