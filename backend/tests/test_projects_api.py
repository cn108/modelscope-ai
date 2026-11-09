import pytest

from apps.projects.models import Project
from apps.workspaces.services import add_member, create_workspace


@pytest.fixture()
def workspace(user):
    return create_workspace(user=user, name="Acme")


@pytest.fixture()
def owner_client(authenticated_client, user):
    return authenticated_client(user)


@pytest.fixture()
def member(workspace, user, other_user):
    add_member(
        actor=user,
        workspace_id=workspace.id,
        email=other_user.email,
        role="member",
    )
    return other_user


@pytest.fixture()
def viewer(workspace, user, third_user):
    add_member(
        actor=user,
        workspace_id=workspace.id,
        email=third_user.email,
        role="viewer",
    )
    return third_user


def test_owner_can_create_project(owner_client, user, workspace):
    response = owner_client.post(
        "/api/v1/projects/",
        {
            "workspace": str(workspace.id),
            "name": "Evaluation suite",
            "description": "Baseline",
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["workspace"] == str(workspace.id)
    assert body["created_by"] == str(user.id)
    assert body["name"] == "Evaluation suite"


def test_member_can_create_project(authenticated_client, member, workspace):
    response = authenticated_client(member).post(
        "/api/v1/projects/",
        {"workspace": str(workspace.id), "name": "Member project"},
        format="json",
    )
    assert response.status_code == 201


def test_viewer_cannot_create_project(authenticated_client, viewer, workspace):
    response = authenticated_client(viewer).post(
        "/api/v1/projects/",
        {"workspace": str(workspace.id), "name": "Nope"},
        format="json",
    )
    assert response.status_code == 403


def test_non_member_cannot_create_project(
    authenticated_client, other_user, workspace
):
    response = authenticated_client(other_user).post(
        "/api/v1/projects/",
        {"workspace": str(workspace.id), "name": "Nope"},
        format="json",
    )
    assert response.status_code == 404


def test_project_list_and_detail_are_tenant_scoped(
    authenticated_client, user, other_user, workspace
):
    own = Project.objects.create(
        workspace=workspace, name="Owned", created_by=user
    )
    foreign_workspace = create_workspace(user=other_user, name="Foreign")
    foreign = Project.objects.create(
        workspace=foreign_workspace, name="Secret", created_by=other_user
    )
    client = authenticated_client(user)

    listing = client.get("/api/v1/projects/")
    ids = {row["id"] for row in listing.json()["results"]}
    assert str(own.id) in ids
    assert str(foreign.id) not in ids
    assert client.get(f"/api/v1/projects/{foreign.id}/").status_code == 404
    assert (
        client.get(
            f"/api/v1/projects/?workspace={foreign_workspace.id}"
        ).status_code
        == 404
    )


def test_member_can_edit_only_own_projects(
    authenticated_client, user, member, workspace
):
    client = authenticated_client(member)
    created = client.post(
        "/api/v1/projects/",
        {"workspace": str(workspace.id), "name": "Mine"},
        format="json",
    )
    assert created.status_code == 201
    own_id = created.json()["id"]
    assert (
        client.patch(
            f"/api/v1/projects/{own_id}/",
            {"name": "Renamed"},
            format="json",
        ).status_code
        == 200
    )

    owner_project = Project.objects.create(
        workspace=workspace, name="Owner project", created_by=user
    )
    assert (
        client.patch(
            f"/api/v1/projects/{owner_project.id}/",
            {"name": "Hijacked"},
            format="json",
        ).status_code
        == 403
    )


def test_member_can_delete_own_project(
    authenticated_client, member, workspace
):
    client = authenticated_client(member)
    created = client.post(
        "/api/v1/projects/",
        {"workspace": str(workspace.id), "name": "Temporary"},
        format="json",
    )
    project_id = created.json()["id"]
    assert client.delete(f"/api/v1/projects/{project_id}/").status_code == 204


def test_admin_can_edit_and_delete_any_project(
    authenticated_client, user, other_user, workspace
):
    add_member(
        actor=user,
        workspace_id=workspace.id,
        email=other_user.email,
        role="admin",
    )
    project = Project.objects.create(
        workspace=workspace, name="Shared", created_by=user
    )
    client = authenticated_client(other_user)

    updated = client.patch(
        f"/api/v1/projects/{project.id}/",
        {"name": "Updated by admin"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated by admin"
    assert client.delete(f"/api/v1/projects/{project.id}/").status_code == 204


def test_viewer_cannot_modify_projects(
    authenticated_client, user, viewer, workspace
):
    project = Project.objects.create(
        workspace=workspace, name="Read only", created_by=user
    )
    client = authenticated_client(viewer)
    assert (
        client.patch(
            f"/api/v1/projects/{project.id}/",
            {"name": "Nope"},
            format="json",
        ).status_code
        == 403
    )
    assert client.delete(f"/api/v1/projects/{project.id}/").status_code == 403


def test_non_member_cannot_touch_project(
    authenticated_client, user, other_user, workspace
):
    project = Project.objects.create(
        workspace=workspace, name="Private", created_by=user
    )
    client = authenticated_client(other_user)
    assert client.get(f"/api/v1/projects/{project.id}/").status_code == 404
    assert (
        client.patch(
            f"/api/v1/projects/{project.id}/",
            {"name": "Nope"},
            format="json",
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/projects/{project.id}/").status_code == 404
