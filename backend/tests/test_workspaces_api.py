import pytest

from apps.workspaces.models import Membership
from apps.workspaces.services import add_member, create_workspace
from common.audit.models import AuditEvent


@pytest.fixture()
def workspace(user):
    return create_workspace(user=user, name="Acme")


@pytest.fixture()
def owner_client(authenticated_client, user):
    return authenticated_client(user)


def test_create_workspace_creates_owner_membership_and_audit(owner_client, user):
    response = owner_client.post(
        "/api/v1/workspaces/", {"name": "Acme"}, format="json"
    )
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "owner"

    membership = Membership.objects.get(workspace_id=body["id"], user=user)
    assert membership.role == Membership.Role.OWNER
    assert AuditEvent.objects.filter(
        action="workspace.created", target_id=body["id"]
    ).exists()


def test_workspace_list_excludes_other_tenants(
    owner_client, other_user, workspace
):
    foreign = create_workspace(user=other_user, name="Foreign")
    response = owner_client.get("/api/v1/workspaces/")
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert str(workspace.id) in ids
    assert str(foreign.id) not in ids


def test_non_member_cannot_read_workspace(
    authenticated_client, other_user, workspace
):
    response = authenticated_client(other_user).get(
        f"/api/v1/workspaces/{workspace.id}/"
    )
    assert response.status_code == 404


def test_member_can_read_but_not_manage(
    authenticated_client, user, other_user, third_user, workspace
):
    add_member(
        actor=user,
        workspace_id=workspace.id,
        email=other_user.email,
        role=Membership.Role.MEMBER,
    )
    client = authenticated_client(other_user)
    detail = f"/api/v1/workspaces/{workspace.id}/"
    members = f"{detail}members/"

    assert client.get(detail).status_code == 200
    assert client.get(members).status_code == 200
    assert (
        client.patch(detail, {"name": "Hijacked"}, format="json").status_code
        == 403
    )
    assert client.delete(detail).status_code == 403
    assert (
        client.post(
            members,
            {"email": third_user.email, "role": "member"},
            format="json",
        ).status_code
        == 403
    )


def test_admin_can_manage_members_but_not_administrators(
    authenticated_client, user, other_user, third_user, workspace
):
    add_member(
        actor=user,
        workspace_id=workspace.id,
        email=other_user.email,
        role=Membership.Role.ADMIN,
    )
    client = authenticated_client(other_user)
    detail = f"/api/v1/workspaces/{workspace.id}/"
    members = f"{detail}members/"

    assert (
        client.patch(detail, {"name": "Renamed"}, format="json").status_code
        == 200
    )
    added = client.post(
        members,
        {"email": third_user.email, "role": "member"},
        format="json",
    )
    assert added.status_code == 201
    assert (
        client.post(
            members,
            {"email": "new-admin@example.com", "role": "admin"},
            format="json",
        ).status_code
        == 403
    )
    assert client.delete(detail).status_code == 403


def test_owner_manages_administrators_and_owner_is_protected(
    owner_client, user, other_user, workspace
):
    add_member(
        actor=user,
        workspace_id=workspace.id,
        email=other_user.email,
        role=Membership.Role.ADMIN,
    )
    admin_membership = Membership.objects.get(
        workspace=workspace, user=other_user
    )
    owner_membership = Membership.objects.get(workspace=workspace, user=user)
    members = f"/api/v1/workspaces/{workspace.id}/members/"

    demoted = owner_client.patch(
        f"{members}{admin_membership.id}/", {"role": "member"}, format="json"
    )
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "member"

    promoted = owner_client.patch(
        f"{members}{admin_membership.id}/", {"role": "admin"}, format="json"
    )
    assert promoted.status_code == 200

    assert (
        owner_client.patch(
            f"{members}{owner_membership.id}/",
            {"role": "member"},
            format="json",
        ).status_code
        == 403
    )
    assert (
        owner_client.delete(f"{members}{owner_membership.id}/").status_code
        == 403
    )


def test_add_member_rejects_duplicates_and_unknown_email(
    owner_client, other_user, workspace
):
    members = f"/api/v1/workspaces/{workspace.id}/members/"
    first = owner_client.post(
        members,
        {"email": other_user.email, "role": "member"},
        format="json",
    )
    assert first.status_code == 201

    duplicate = owner_client.post(
        members,
        {"email": other_user.email, "role": "viewer"},
        format="json",
    )
    assert duplicate.status_code == 409

    unknown = owner_client.post(
        members,
        {"email": "ghost@example.com", "role": "member"},
        format="json",
    )
    assert unknown.status_code == 400


def test_owner_can_delete_workspace_and_memberships_cascade(
    owner_client, user, other_user, workspace
):
    add_member(
        actor=user,
        workspace_id=workspace.id,
        email=other_user.email,
        role="member",
    )
    response = owner_client.delete(f"/api/v1/workspaces/{workspace.id}/")
    assert response.status_code == 204
    assert not Membership.objects.filter(workspace_id=workspace.id).exists()
    assert AuditEvent.objects.filter(action="workspace.deleted").exists()


def test_role_changes_are_audited(owner_client, user, other_user, workspace):
    membership = add_member(
        actor=user,
        workspace_id=workspace.id,
        email=other_user.email,
        role="member",
    )
    response = owner_client.patch(
        f"/api/v1/workspaces/{workspace.id}/members/{membership.id}/",
        {"role": "viewer"},
        format="json",
    )
    assert response.status_code == 200

    event = AuditEvent.objects.get(
        action="membership.role_changed", target_id=membership.id
    )
    assert event.metadata == {
        "from": "member",
        "to": "viewer",
        "user_id": str(other_user.id),
    }


def test_non_member_cannot_list_or_add_members(
    authenticated_client, other_user, third_user, workspace
):
    client = authenticated_client(other_user)
    members = f"/api/v1/workspaces/{workspace.id}/members/"
    assert client.get(members).status_code == 404
    assert (
        client.post(
            members,
            {"email": third_user.email, "role": "member"},
            format="json",
        ).status_code
        == 404
    )
