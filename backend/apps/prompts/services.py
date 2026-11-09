"""Saved prompt services: append-only versions and workspace-scoped access."""

from django.db import transaction
from django.db.models import Max
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.projects.services import project_for_user  # noqa: F401 - re-exported for callers
from apps.prompts.models import Prompt, PromptVersion
from apps.workspaces.models import Membership
from apps.workspaces.permissions import require_membership


def prompt_for_user(user, prompt_id, minimum_role=Membership.Role.VIEWER) -> Prompt:
    prompt = (
        Prompt.objects.select_related("project", "project__workspace")
        .filter(pk=prompt_id)
        .first()
    )
    if prompt is None:
        raise NotFound("Prompt not found.")
    require_membership(user, prompt.project.workspace_id, minimum_role)
    return prompt


def require_prompt_editor(user, prompt: Prompt) -> None:
    """Admins and owners may edit any prompt; members only their own."""
    membership = Membership.objects.filter(
        workspace=prompt.project.workspace_id, user=user
    ).first()
    if membership is None:
        raise NotFound("Prompt not found.")
    if membership.role == Membership.Role.VIEWER:
        raise PermissionDenied("Viewers cannot modify prompts.")
    if membership.role not in (Membership.Role.ADMIN, Membership.Role.OWNER):
        if prompt.created_by_id != user.id:
            raise PermissionDenied("You can only modify prompts you created.")


def list_prompts(*, user, project_id):
    project = project_for_user(user, project_id)
    return (
        Prompt.objects.filter(project=project)
        .select_related("created_by")
        .prefetch_related("versions")
        .order_by("name")
    )


def current_version(prompt: Prompt) -> PromptVersion | None:
    return prompt.versions.order_by("-version_number").first()


def get_prompt(*, user, prompt_id) -> Prompt:
    prompt = prompt_for_user(user, prompt_id)
    return (
        Prompt.objects.select_related("project", "created_by")
        .prefetch_related("versions")
        .get(pk=prompt.pk)
    )


def _append_version(*, prompt, actor, system_prompt, user_prompt, parameters) -> PromptVersion:
    latest = prompt.versions.aggregate(number=Max("version_number"))["number"] or 0
    return PromptVersion.objects.create(
        prompt=prompt,
        version_number=latest + 1,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        parameters=parameters or {},
        created_by=actor,
    )


@transaction.atomic
def create_prompt(*, actor, project_id, validated_data) -> Prompt:
    project = project_for_user(actor, project_id, Membership.Role.MEMBER)
    data = dict(validated_data)
    prompt = Prompt.objects.create(
        project=project,
        name=data["name"].strip(),
        description=(data.get("description") or "").strip(),
        created_by=actor,
    )
    _append_version(
        prompt=prompt,
        actor=actor,
        system_prompt=data.get("system_prompt", ""),
        user_prompt=data["user_prompt"],
        parameters=data.get("parameters"),
    )
    return prompt


@transaction.atomic
def update_prompt(*, actor, prompt_id, validated_data) -> Prompt:
    prompt = prompt_for_user(actor, prompt_id, Membership.Role.MEMBER)
    require_prompt_editor(actor, prompt)
    prompt = Prompt.objects.select_for_update().get(pk=prompt.pk)
    data = dict(validated_data)
    changed = []

    if "name" in data and data["name"].strip() != prompt.name:
        prompt.name = data["name"].strip()
        changed.append("name")
    if "description" in data and (data["description"] or "").strip() != prompt.description:
        prompt.description = (data["description"] or "").strip()
        changed.append("description")

    version = current_version(prompt)
    content_fields = ("system_prompt", "user_prompt", "parameters")
    if any(field in data for field in content_fields):
        candidate = {
            "system_prompt": data.get(
                "system_prompt", version.system_prompt if version else ""
            ),
            "user_prompt": data.get(
                "user_prompt", version.user_prompt if version else ""
            ),
            "parameters": data.get(
                "parameters", version.parameters if version else {}
            )
            or {},
        }
        if version is None or any(
            getattr(version, field) != value for field, value in candidate.items()
        ):
            _append_version(prompt=prompt, actor=actor, **candidate)
            changed.append("version")

    if changed:
        # "version" is not a column on Prompt; only bump concrete fields.
        metadata = [field for field in changed if field in ("name", "description")]
        prompt.save(update_fields=[*metadata, "updated_at"])
    return get_prompt(user=actor, prompt_id=prompt.pk)


@transaction.atomic
def duplicate_prompt(*, actor, prompt_id) -> Prompt:
    source = prompt_for_user(actor, prompt_id, Membership.Role.MEMBER)
    version = current_version(source)
    if version is None:
        raise NotFound("Prompt has no saved version.")
    base_name = f"{source.name} (copy)"
    name = base_name
    suffix = 2
    while Prompt.objects.filter(project=source.project, name=name).exists():
        name = f"{base_name} {suffix}"
        suffix += 1
    copy = Prompt.objects.create(
        project=source.project,
        name=name[:160],
        description=source.description,
        created_by=actor,
    )
    _append_version(
        prompt=copy,
        actor=actor,
        system_prompt=version.system_prompt,
        user_prompt=version.user_prompt,
        parameters=version.parameters,
    )
    return copy


@transaction.atomic
def restore_version(*, actor, prompt_id, version_number: int) -> Prompt:
    prompt = prompt_for_user(actor, prompt_id, Membership.Role.MEMBER)
    require_prompt_editor(actor, prompt)
    source = prompt.versions.filter(version_number=version_number).first()
    if source is None:
        raise NotFound("Prompt version not found.")
    _append_version(
        prompt=prompt,
        actor=actor,
        system_prompt=source.system_prompt,
        user_prompt=source.user_prompt,
        parameters=source.parameters,
    )
    prompt.save(update_fields=["updated_at"])
    return get_prompt(user=actor, prompt_id=prompt.pk)


@transaction.atomic
def delete_prompt(*, actor, prompt_id) -> None:
    prompt = prompt_for_user(actor, prompt_id, Membership.Role.MEMBER)
    require_prompt_editor(actor, prompt)
    prompt.delete()
