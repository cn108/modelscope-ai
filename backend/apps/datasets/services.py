"""Dataset services: tenancy, edit rules and record versioning.

Dataset ``version`` increases on every record mutation so evaluations can record
which snapshot of the test cases they ran. Dataset metadata edits (name,
description) do not change the test content and therefore do not bump it.
"""

from django.db import transaction
from django.db.models import Count, F, Max
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.datasets.importers import parse_dataset_file
from apps.datasets.models import Dataset, DatasetRecord
from apps.projects.services import project_for_user
from apps.workspaces.models import Membership


def dataset_for_user(user, dataset_id, minimum_role=Membership.Role.VIEWER) -> Dataset:
    dataset = (
        Dataset.objects.select_related("project", "project__workspace")
        .filter(pk=dataset_id)
        .first()
    )
    if dataset is None:
        raise NotFound("Dataset not found.")
    from apps.workspaces.permissions import require_membership

    require_membership(user, dataset.project.workspace_id, minimum_role)
    return dataset


def dataset_record_for_user(
    user, record_id, minimum_role=Membership.Role.VIEWER
) -> DatasetRecord:
    record = (
        DatasetRecord.objects.select_related("dataset", "dataset__project")
        .filter(pk=record_id)
        .first()
    )
    if record is None:
        raise NotFound("Dataset record not found.")
    from apps.workspaces.permissions import require_membership

    require_membership(user, record.dataset.project.workspace_id, minimum_role)
    return record


def require_dataset_editor(user, dataset: Dataset) -> None:
    """Admins and owners may edit any dataset; members only their own."""
    membership = Membership.objects.filter(
        workspace=dataset.project.workspace_id, user=user
    ).first()
    if membership is None:
        raise NotFound("Dataset not found.")
    if membership.role == Membership.Role.VIEWER:
        raise PermissionDenied("Viewers cannot modify datasets.")
    if membership.role not in (Membership.Role.ADMIN, Membership.Role.OWNER):
        if dataset.created_by_id != user.id:
            raise PermissionDenied("You can only modify datasets you created.")


def list_datasets(*, user, project_id):
    project = project_for_user(user, project_id)
    return (
        Dataset.objects.filter(project=project)
        .select_related("created_by")
        .annotate(record_count=Count("records"))
        .order_by("name")
    )


def get_dataset(*, user, dataset_id) -> Dataset:
    dataset = dataset_for_user(user, dataset_id)
    return (
        Dataset.objects.select_related("project", "created_by")
        .annotate(record_count=Count("records"))
        .get(pk=dataset.pk)
    )


def _clean_name(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise ValidationError({"name": "A dataset name is required."})
    return name


@transaction.atomic
def create_dataset(*, actor, project_id, validated_data) -> Dataset:
    project = project_for_user(actor, project_id, Membership.Role.MEMBER)
    name = _clean_name(validated_data.get("name", ""))
    if Dataset.objects.filter(project=project, name=name).exists():
        raise ValidationError({"name": "A dataset with this name already exists."})
    return Dataset.objects.create(
        project=project,
        name=name,
        description=(validated_data.get("description") or "").strip(),
        created_by=actor,
    )


@transaction.atomic
def update_dataset(*, actor, dataset_id, validated_data) -> Dataset:
    dataset = dataset_for_user(actor, dataset_id, Membership.Role.MEMBER)
    require_dataset_editor(actor, dataset)
    data = dict(validated_data)
    changed = []
    if "name" in data:
        name = _clean_name(data["name"])
        if name != dataset.name:
            if Dataset.objects.filter(project=dataset.project, name=name).exclude(
                pk=dataset.pk
            ).exists():
                raise ValidationError({"name": "A dataset with this name already exists."})
            dataset.name = name
            changed.append("name")
    if "description" in data:
        description = (data["description"] or "").strip()
        if description != dataset.description:
            dataset.description = description
            changed.append("description")
    if changed:
        dataset.save(update_fields=[*changed, "updated_at"])
    return get_dataset(user=actor, dataset_id=dataset.pk)


@transaction.atomic
def delete_dataset(*, actor, dataset_id) -> None:
    dataset = dataset_for_user(actor, dataset_id, Membership.Role.MEMBER)
    require_dataset_editor(actor, dataset)
    dataset.delete()


def _bump_version(dataset: Dataset) -> None:
    Dataset.objects.filter(pk=dataset.pk).update(
        version=F("version") + 1, updated_at=timezone.now()
    )


def _locked_dataset(actor, dataset_id, minimum_role=Membership.Role.MEMBER) -> Dataset:
    dataset = (
        Dataset.objects.select_for_update()
        .select_related("project", "project__workspace")
        .filter(pk=dataset_id)
        .first()
    )
    if dataset is None:
        raise NotFound("Dataset not found.")
    from apps.workspaces.permissions import require_membership

    require_membership(actor, dataset.project.workspace_id, minimum_role)
    require_dataset_editor(actor, dataset)
    return dataset


def list_records(*, user, dataset_id):
    dataset = dataset_for_user(user, dataset_id)
    return DatasetRecord.objects.filter(dataset=dataset).order_by("position")


@transaction.atomic
def create_record(*, actor, dataset_id, validated_data) -> DatasetRecord:
    dataset = _locked_dataset(actor, dataset_id)
    highest = dataset.records.aggregate(value=Max("position"))["value"] or 0
    record = DatasetRecord.objects.create(
        dataset=dataset,
        position=highest + 1,
        input=validated_data["input"],
        expected_output=validated_data.get("expected_output") or "",
        context=validated_data.get("context") or [],
        metadata=validated_data.get("metadata") or {},
    )
    _bump_version(dataset)
    return record


@transaction.atomic
def update_record(*, actor, record_id, validated_data) -> DatasetRecord:
    record = dataset_record_for_user(actor, record_id, Membership.Role.MEMBER)
    dataset = _locked_dataset(actor, record.dataset_id)
    changed = []
    for field in ("input", "expected_output", "context", "metadata"):
        if field in validated_data:
            value = validated_data[field]
            if field in ("context", "metadata"):
                value = value or ([] if field == "context" else {})
            elif field == "expected_output":
                value = value or ""
            setattr(record, field, value)
            changed.append(field)
    if changed:
        record.save(update_fields=[*changed, "updated_at"])
        _bump_version(dataset)
    return DatasetRecord.objects.get(pk=record.pk)


@transaction.atomic
def delete_record(*, actor, record_id) -> None:
    record = dataset_record_for_user(actor, record_id, Membership.Role.MEMBER)
    dataset = _locked_dataset(actor, record.dataset_id)
    record.delete()
    _bump_version(dataset)


@transaction.atomic
def import_records(*, actor, dataset_id, filename, raw, mode="append") -> dict:
    """Validate the whole file first, then apply it in one transaction."""
    dataset = _locked_dataset(actor, dataset_id)
    records = parse_dataset_file(filename, raw)
    if mode == "replace":
        dataset.records.all().delete()
        start = 1
    else:
        highest = dataset.records.aggregate(value=Max("position"))["value"] or 0
        start = highest + 1

    DatasetRecord.objects.bulk_create(
        [
            DatasetRecord(
                dataset=dataset,
                position=start + offset,
                input=item["input"],
                expected_output=item["expected_output"],
                context=item["context"],
                metadata=item["metadata"],
            )
            for offset, item in enumerate(records)
        ]
    )
    _bump_version(dataset)
    dataset.refresh_from_db(fields=["version"])
    return {"imported": len(records), "version": dataset.version, "mode": mode}
