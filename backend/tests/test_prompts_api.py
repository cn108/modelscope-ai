import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.prompts.models import Prompt
from apps.workspaces.models import Membership
from apps.workspaces.services import add_member, create_workspace

PAYLOAD = {
    "name": "Support triage",
    "description": "Classify inbound tickets",
    "system_prompt": "You are a support triage assistant.",
    "user_prompt": "Classify this ticket: {{ticket}}",
    "parameters": {"temperature": 0.2, "max_tokens": 200},
}


@pytest.fixture()
def project(user):
    workspace = create_workspace(user=user, name="Prompts")
    return Project.objects.create(workspace=workspace, name="Prompt project", created_by=user)


@pytest.fixture()
def owner_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def create_prompt(client, project, **overrides):
    payload = {**PAYLOAD, **overrides}
    response = client.post(f"/api/v1/projects/{project.id}/prompts/", payload, format="json")
    assert response.status_code == 201, response.content
    return response.json()


def test_create_prompt_starts_at_version_one(owner_client, project):
    body = create_prompt(owner_client, project)
    assert body["version_count"] == 1
    assert body["current_version"]["version_number"] == 1
    assert body["current_version"]["user_prompt"] == PAYLOAD["user_prompt"]
    assert body["current_version"]["parameters"] == PAYLOAD["parameters"]
    assert Prompt.objects.filter(project=project).count() == 1


def test_editing_content_appends_version_and_keeps_history(owner_client, project):
    prompt = create_prompt(owner_client, project)
    prompt_id = prompt["id"]

    response = owner_client.patch(
        f"/api/v1/prompts/{prompt_id}/",
        {"user_prompt": "Classify this ticket differently: {{ticket}}"},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version_count"] == 2
    assert body["current_version"]["version_number"] == 2

    versions = owner_client.get(f"/api/v1/prompts/{prompt_id}/versions/").json()
    assert [row["version_number"] for row in versions] == [2, 1]
    assert versions[1]["user_prompt"] == PAYLOAD["user_prompt"]


def test_renaming_does_not_create_a_version(owner_client, project):
    prompt = create_prompt(owner_client, project)
    response = owner_client.patch(
        f"/api/v1/prompts/{prompt['id']}/", {"name": "Renamed prompt"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["version_count"] == 1
    assert response.json()["name"] == "Renamed prompt"


def test_restore_appends_old_content_as_a_new_version(owner_client, project):
    prompt = create_prompt(owner_client, project)
    prompt_id = prompt["id"]
    owner_client.patch(
        f"/api/v1/prompts/{prompt_id}/", {"system_prompt": "Changed system"}, format="json"
    )

    restore = owner_client.post(
        f"/api/v1/prompts/{prompt_id}/versions/restore/",
        {"version_number": 1},
        format="json",
    )
    assert restore.status_code == 201
    body = restore.json()
    assert body["version_count"] == 3
    assert body["current_version"]["version_number"] == 3
    assert body["current_version"]["system_prompt"] == PAYLOAD["system_prompt"]
    assert body["current_version"]["user_prompt"] == PAYLOAD["user_prompt"]


def test_restore_rejects_unknown_version(owner_client, project):
    prompt = create_prompt(owner_client, project)
    response = owner_client.post(
        f"/api/v1/prompts/{prompt['id']}/versions/restore/",
        {"version_number": 99},
        format="json",
    )
    assert response.status_code == 404


def test_duplicate_creates_independent_copy(owner_client, project):
    prompt = create_prompt(owner_client, project)
    response = owner_client.post(f"/api/v1/prompts/{prompt['id']}/duplicate/")
    assert response.status_code == 201
    copy = response.json()
    assert copy["id"] != prompt["id"]
    assert copy["name"] == f"{PAYLOAD['name']} (copy)"
    assert copy["current_version"]["user_prompt"] == PAYLOAD["user_prompt"]

    owner_client.patch(
        f"/api/v1/prompts/{copy['id']}/", {"user_prompt": "Copy only"}, format="json"
    )
    original = owner_client.get(f"/api/v1/prompts/{prompt['id']}/").json()
    assert original["current_version"]["user_prompt"] == PAYLOAD["user_prompt"]


def test_viewer_cannot_create_or_edit_prompts(owner_client, user, other_user, project):
    prompt = create_prompt(owner_client, project)
    add_member(
        actor=user,
        workspace_id=project.workspace_id,
        email=other_user.email,
        role=Membership.Role.VIEWER,
    )
    viewer = APIClient()
    viewer.force_authenticate(user=other_user)

    assert viewer.get(f"/api/v1/projects/{project.id}/prompts/").status_code == 200
    assert viewer.patch(
        f"/api/v1/prompts/{prompt['id']}/", {"user_prompt": "nope"}, format="json"
    ).status_code == 403
    assert viewer.post(
        f"/api/v1/projects/{project.id}/prompts/", PAYLOAD, format="json"
    ).status_code == 403


def test_member_can_only_edit_own_prompt(owner_client, user, other_user, project):
    prompt = create_prompt(owner_client, project)
    add_member(
        actor=user,
        workspace_id=project.workspace_id,
        email=other_user.email,
        role=Membership.Role.MEMBER,
    )
    member = APIClient()
    member.force_authenticate(user=other_user)
    assert member.patch(
        f"/api/v1/prompts/{prompt['id']}/", {"system_prompt": "hijack"}, format="json"
    ).status_code == 403

    own = member.post(
        f"/api/v1/projects/{project.id}/prompts/",
        {**PAYLOAD, "name": "Member prompt"},
        format="json",
    )
    assert own.status_code == 201
    assert member.patch(
        f"/api/v1/prompts/{own.json()['id']}/", {"system_prompt": "mine"}, format="json"
    ).status_code == 200


def test_cross_tenant_prompt_access_is_404(owner_client, other_user, project):
    prompt = create_prompt(owner_client, project)
    outsider = APIClient()
    outsider.force_authenticate(user=other_user)
    assert outsider.get(f"/api/v1/prompts/{prompt['id']}/").status_code == 404
    assert outsider.get(
        f"/api/v1/projects/{project.id}/prompts/"
    ).status_code == 404


def test_prompt_parameters_are_validated(owner_client, project):
    response = owner_client.post(
        f"/api/v1/projects/{project.id}/prompts/",
        {**PAYLOAD, "parameters": {"arbitrary": "value"}},
        format="json",
    )
    assert response.status_code == 400
