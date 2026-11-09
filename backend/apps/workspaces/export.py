"""Workspace data export (specification §9 retention/export workflow).

The export is an operator/user convenience, not a database dump: it contains
workspace content and metadata without provider credentials, password hashes or
other authentication secrets. Large workspaces can produce a large JSON file;
streaming and object storage are deliberately left to the deployment layer.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from django.db.models import QuerySet
from django.utils import timezone

from apps.datasets.models import Dataset, DatasetRecord
from apps.evaluations.models import Evaluation, EvaluationModel, EvaluationResult
from apps.playground.models import Execution, ExecutionResult
from apps.projects.models import Project
from apps.prompts.models import Prompt, PromptVersion
from apps.providers.models import ModelConfig, ProviderConfig
from apps.security.models import (
    SecurityFinding,
    SecurityScan,
    SecurityTestModel,
    SecurityTestResult,
    SecurityTestRun,
)
from apps.workspaces.models import Membership, Workspace
from apps.workspaces.permissions import require_membership
from common.audit.services import record_event


def _value(value):
    if isinstance(value, (UUID, datetime, date)):
        return str(value)
    return value


def _row(instance, *, exclude: tuple[str, ...] = ()) -> dict:
    return {
        field.name: _value(getattr(instance, field.name))
        for field in instance._meta.fields
        if field.name not in exclude
    }


def _rows(queryset: QuerySet, *, exclude: tuple[str, ...] = ()) -> list[dict]:
    return [_row(item, exclude=exclude) for item in queryset]


def _dataset(dataset: Dataset) -> dict:
    return {
        **_row(dataset, exclude=("project", "created_by")),
        "records": _rows(
            DatasetRecord.objects.filter(dataset=dataset).order_by("position"),
            exclude=("dataset",),
        ),
    }


def _evaluation(evaluation: Evaluation) -> dict:
    models = list(
        EvaluationModel.objects.filter(evaluation=evaluation)
        .select_related("provider")
        .order_by("position")
    )
    results = (
        EvaluationResult.objects.filter(evaluation=evaluation)
        .select_related("model")
        .prefetch_related("reviews__reviewer")
        .order_by("model__position", "record_position")
    )
    rows = []
    for result in results:
        row = _row(result, exclude=("evaluation", "model"))
        row["model_id"] = str(result.model_id)
        row["model_position"] = result.model.position
        row["reviews"] = [
            {
                **_row(review, exclude=("result", "reviewer")),
                "reviewer_email": review.reviewer.email if review.reviewer else "",
            }
            for review in result.reviews.all()
        ]
        rows.append(row)
    return {
        **_row(
            evaluation,
            exclude=(
                "project",
                "dataset",
                "judge_provider",
                "created_by",
            ),
        ),
        "models": [
            {
                **_row(model, exclude=("evaluation", "provider")),
                "provider_id": str(model.provider_id) if model.provider_id else None,
            }
            for model in models
        ],
        "results": rows,
    }


def _playground_execution(execution: Execution) -> dict:
    return {
        **_row(
            execution,
            exclude=("project", "prompt", "prompt_version", "created_by"),
        ),
        "prompt_id": str(execution.prompt_id) if execution.prompt_id else None,
        "results": _rows(
            ExecutionResult.objects.filter(execution=execution).order_by("position"),
            exclude=("execution", "provider"),
        ),
    }


def _security_scan(scan: SecurityScan) -> dict:
    return {
        **_row(
            scan,
            exclude=("project", "dataset", "prompt", "execution", "created_by"),
        ),
        "findings": _rows(
            SecurityFinding.objects.filter(scan=scan)
            .select_related("reviewed_by")
            .order_by("detected_at"),
            exclude=(
                "scan",
                "project",
                "execution",
                "execution_result",
                "reviewed_by",
            ),
        ),
    }


def _security_test_run(run: SecurityTestRun) -> dict:
    return {
        **_row(run, exclude=("project", "created_by")),
        "models": _rows(
            SecurityTestModel.objects.filter(run=run).order_by("position"),
            exclude=("run", "provider"),
        ),
        "results": _rows(
            SecurityTestResult.objects.filter(run=run).order_by("created_at"),
            exclude=("run", "model"),
        ),
    }


def _project(project: Project) -> dict:
    return {
        **_row(project, exclude=("workspace", "created_by")),
        "providers": [
            {
                **_row(provider, exclude=("project",)),
                "has_secret": hasattr(provider, "secret"),
                "models": _rows(
                    ModelConfig.objects.filter(provider=provider),
                    exclude=("provider",),
                ),
            }
            for provider in ProviderConfig.objects.filter(project=project).order_by(
                "created_at"
            )
        ],
        "datasets": [
            _dataset(dataset)
            for dataset in Dataset.objects.filter(project=project).order_by("created_at")
        ],
        "prompts": [
            {
                **_row(prompt, exclude=("project", "created_by")),
                "versions": _rows(
                    PromptVersion.objects.filter(prompt=prompt).order_by("version_number"),
                    exclude=("prompt", "created_by"),
                ),
            }
            for prompt in Prompt.objects.filter(project=project).order_by("created_at")
        ],
        "playground_executions": [
            _playground_execution(execution)
            for execution in Execution.objects.filter(project=project).order_by("created_at")
        ],
        "evaluations": [
            _evaluation(evaluation)
            for evaluation in Evaluation.objects.filter(project=project).order_by("created_at")
        ],
        "security_scans": [
            _security_scan(scan)
            for scan in SecurityScan.objects.filter(project=project).order_by("created_at")
        ],
        "security_test_runs": [
            _security_test_run(run)
            for run in SecurityTestRun.objects.filter(project=project).order_by("created_at")
        ],
    }


def export_workspace(*, user, workspace_id) -> dict:
    """Return a portable JSON-serialisable snapshot for workspace admins."""
    workspace, _ = require_membership(user, workspace_id, Membership.Role.ADMIN)
    workspace = Workspace.objects.select_related("owner").get(pk=workspace.pk)
    record_event(
        actor=user,
        action="workspace.exported",
        workspace=workspace,
        target_type="workspace",
        target_id=workspace.pk,
        metadata={"format_version": 1},
    )
    members = (
        Membership.objects.filter(workspace=workspace)
        .select_related("user")
        .order_by("created_at")
    )
    return {
        "format": "modelscope-ai-workspace-export",
        "format_version": 1,
        "exported_at": timezone.now().isoformat(),
        "workspace": {
            **_row(workspace, exclude=("owner",)),
            "owner_email": workspace.owner.email,
        },
        "members": [
            {
                "id": str(member.id),
                "email": member.user.email,
                "display_name": member.user.display_name,
                "role": member.role,
                "joined_at": member.created_at.isoformat(),
            }
            for member in members
        ],
        "projects": [
            _project(project)
            for project in Project.objects.filter(workspace=workspace).order_by("created_at")
        ],
    }
