import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.datasets.models import Dataset
from apps.projects.models import Project
from apps.workspaces.models import Membership
from apps.workspaces.services import add_member, create_workspace


@pytest.fixture()
def project(user):
    workspace = create_workspace(user=user, name="Datasets")
    return Project.objects.create(
        workspace=workspace, name="Datasets project", created_by=user
    )


@pytest.fixture()
def owner_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def create_dataset(client, project, name="Support QA"):
    response = client.post(
        f"/api/v1/projects/{project.id}/datasets/",
        {"name": name, "description": "Regression cases"},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def upload(client, dataset_id, filename, content, mode="append"):
    file = SimpleUploadedFile(
        filename, content.encode("utf-8"), content_type="text/plain"
    )
    return client.post(
        f"/api/v1/datasets/{dataset_id}/import/",
        {"file": file, "mode": mode},
        format="multipart",
    )


def test_dataset_crud_and_listing(owner_client, project):
    created = create_dataset(owner_client, project)
    assert created["version"] == 1
    assert created["record_count"] == 0

    listing = owner_client.get(f"/api/v1/projects/{project.id}/datasets/")
    assert listing.status_code == 200
    assert [row["name"] for row in listing.json()] == ["Support QA"]

    updated = owner_client.patch(
        f"/api/v1/datasets/{created['id']}/",
        {"name": "Support QA v2", "description": "Updated"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Support QA v2"
    # Metadata edits do not change record content, so the version is unchanged.
    assert updated.json()["version"] == 1

    deleted = owner_client.delete(f"/api/v1/datasets/{created['id']}/")
    assert deleted.status_code == 204
    assert Dataset.objects.count() == 0


def test_duplicate_dataset_name_is_rejected(owner_client, project):
    create_dataset(owner_client, project)
    response = owner_client.post(
        f"/api/v1/projects/{project.id}/datasets/",
        {"name": "Support QA"},
        format="json",
    )
    assert response.status_code == 400
    assert "already exists" in str(response.json())


def test_record_crud_bumps_dataset_version(owner_client, project):
    dataset = create_dataset(owner_client, project)
    created = owner_client.post(
        f"/api/v1/datasets/{dataset['id']}/records/",
        {
            "input": "What is 2+2?",
            "expected_output": "4",
            "context": ["Two plus two equals four."],
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    record = created.json()
    assert record["position"] == 1
    assert record["context"] == ["Two plus two equals four."]

    detail = owner_client.get(f"/api/v1/datasets/{dataset['id']}/")
    assert detail.json()["version"] == 2
    assert detail.json()["record_count"] == 1

    patched = owner_client.patch(
        f"/api/v1/dataset-records/{record['id']}/",
        {"expected_output": "four"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["expected_output"] == "four"
    assert owner_client.get(f"/api/v1/datasets/{dataset['id']}/").json()["version"] == 3

    assert (
        owner_client.delete(f"/api/v1/dataset-records/{record['id']}/").status_code
        == 204
    )
    assert owner_client.get(f"/api/v1/datasets/{dataset['id']}/").json()["version"] == 4


def test_json_import_appends_and_validates(owner_client, project):
    dataset = create_dataset(owner_client, project)
    response = upload(
        owner_client,
        dataset["id"],
        "cases.json",
        """
        [
          {"input": "What is 2+2?", "expected_output": "4"},
          {"input": "Capital of France?", "expected_output": "Paris",
           "context": ["France's capital is Paris."]}
        ]
        """,
    )
    assert response.status_code == 201, response.content
    assert response.json() == {"imported": 2, "version": 2, "mode": "append"}

    rows = owner_client.get(f"/api/v1/datasets/{dataset['id']}/records/").json()
    assert rows["count"] == 2
    assert [row["position"] for row in rows["results"]] == [1, 2]
    assert rows["results"][1]["context"] == ["France's capital is Paris."]


def test_jsonl_and_csv_imports(owner_client, project):
    dataset = create_dataset(owner_client, project)
    jsonl = upload(
        owner_client,
        dataset["id"],
        "cases.jsonl",
        '{"input": "a", "expected_output": "A"}\n\n{"input": "b"}\n',
    )
    assert jsonl.status_code == 201, jsonl.content
    assert jsonl.json()["imported"] == 2

    csv_response = upload(
        owner_client,
        dataset["id"],
        "cases.csv",
        "input,expected_output,context\nc,C,\nd,,\n",
    )
    assert csv_response.status_code == 201, csv_response.content
    assert csv_response.json()["imported"] == 2
    assert csv_response.json()["version"] == 3


def test_replace_import_removes_existing_records(owner_client, project):
    dataset = create_dataset(owner_client, project)
    upload(
        owner_client,
        dataset["id"],
        "cases.json",
        '[{"input": "old"}]',
    )
    replaced = upload(
        owner_client,
        dataset["id"],
        "cases.json",
        '[{"input": "new"}]',
        mode="replace",
    )
    assert replaced.status_code == 201
    assert replaced.json()["mode"] == "replace"
    rows = owner_client.get(f"/api/v1/datasets/{dataset['id']}/records/").json()
    assert rows["count"] == 1
    assert rows["results"][0]["input"] == "new"


def test_invalid_import_reports_rows_and_imports_nothing(owner_client, project):
    dataset = create_dataset(owner_client, project)
    response = upload(
        owner_client,
        dataset["id"],
        "cases.json",
        '[{"input": ""}, {"input": "ok", "unexpected": true}, {"expected_output": "x"}]',
    )
    assert response.status_code == 400
    details = response.json()["error"]["details"]
    assert details["error_count"] == 3
    messages = {(item["row"], item["field"]) for item in details["errors"]}
    assert (1, "input") in messages
    assert (2, "record") in messages
    assert (3, "input") in messages

    rows = owner_client.get(f"/api/v1/datasets/{dataset['id']}/records/").json()
    assert rows["count"] == 0
    assert owner_client.get(f"/api/v1/datasets/{dataset['id']}/").json()["version"] == 1


def test_unsupported_or_malformed_files_are_rejected(owner_client, project):
    dataset = create_dataset(owner_client, project)
    unsupported = upload(owner_client, dataset["id"], "cases.txt", "input\nx\n")
    assert unsupported.status_code == 400
    assert "json" in str(unsupported.json()).lower()

    malformed = upload(owner_client, dataset["id"], "cases.json", "[{]")
    assert malformed.status_code == 400
    assert "Invalid JSON" in str(malformed.json())

    bad_metadata = upload(
        owner_client,
        dataset["id"],
        "cases.csv",
        "input,metadata\nx,not-json\n",
    )
    assert bad_metadata.status_code == 400


def test_viewer_is_read_only(owner_client, user, other_user, project):
    dataset = create_dataset(owner_client, project)
    upload(owner_client, dataset["id"], "cases.json", '[{"input": "hi"}]')
    add_member(
        actor=user,
        workspace_id=project.workspace_id,
        email=other_user.email,
        role=Membership.Role.VIEWER,
    )
    viewer = APIClient()
    viewer.force_authenticate(user=other_user)

    assert viewer.get(f"/api/v1/datasets/{dataset['id']}/").status_code == 200
    assert (
        viewer.get(f"/api/v1/datasets/{dataset['id']}/records/").status_code == 200
    )
    assert (
        viewer.post(
            f"/api/v1/datasets/{dataset['id']}/records/",
            {"input": "nope"},
            format="json",
        ).status_code
        == 403
    )
    assert (
        viewer.post(
            f"/api/v1/projects/{project.id}/datasets/",
            {"name": "Viewer dataset"},
            format="json",
        ).status_code
        == 403
    )
    assert (
        viewer.delete(f"/api/v1/datasets/{dataset['id']}/").status_code == 403
    )
    assert (
        viewer.patch(
            f"/api/v1/datasets/{dataset['id']}/", {"name": "x"}, format="json"
        ).status_code
        == 403
    )


def test_members_edit_only_their_own_datasets_but_admins_edit_any(
    owner_client, user, other_user, third_user, project
):
    dataset = create_dataset(owner_client, project)
    add_member(
        actor=user,
        workspace_id=project.workspace_id,
        email=other_user.email,
        role=Membership.Role.MEMBER,
    )
    member = APIClient()
    member.force_authenticate(user=other_user)
    denied = member.patch(
        f"/api/v1/datasets/{dataset['id']}/", {"name": "Member rename"}, format="json"
    )
    assert denied.status_code == 403

    add_member(
        actor=user,
        workspace_id=project.workspace_id,
        email=third_user.email,
        role=Membership.Role.ADMIN,
    )
    admin = APIClient()
    admin.force_authenticate(user=third_user)
    allowed = admin.patch(
        f"/api/v1/datasets/{dataset['id']}/", {"name": "Admin rename"}, format="json"
    )
    assert allowed.status_code == 200
    assert allowed.json()["name"] == "Admin rename"


def test_cross_tenant_dataset_access_is_404(owner_client, other_user, project):
    dataset = create_dataset(owner_client, project)
    owner_client.post(
        f"/api/v1/datasets/{dataset['id']}/records/",
        {"input": "hello"},
        format="json",
    )
    record = owner_client.get(
        f"/api/v1/datasets/{dataset['id']}/records/"
    ).json()["results"][0]

    outsider = APIClient()
    outsider.force_authenticate(user=other_user)
    assert outsider.get(f"/api/v1/datasets/{dataset['id']}/").status_code == 404
    assert (
        outsider.get(f"/api/v1/datasets/{dataset['id']}/records/").status_code == 404
    )
    assert (
        outsider.get(f"/api/v1/dataset-records/{record['id']}/").status_code == 404
    )
    assert (
        outsider.patch(
            f"/api/v1/dataset-records/{record['id']}/",
            {"input": "hijack"},
            format="json",
        ).status_code
        == 404
    )
    assert (
        outsider.get(f"/api/v1/projects/{project.id}/datasets/").status_code == 404
    )
