"""Serializers for workspace and membership payloads (§8)."""

from rest_framework import serializers

from apps.accounts.services import UserProfileSerializer
from apps.workspaces.models import Membership, Workspace

MANAGEABLE_ROLES = [
    Membership.Role.ADMIN,
    Membership.Role.MEMBER,
    Membership.Role.VIEWER,
]


def _validate_settings(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError("Settings must be a JSON object.")
    return value


class WorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ["id", "name", "owner", "settings", "role", "created_at", "updated_at"]
        read_only_fields = fields

    def get_role(self, obj) -> str | None:
        request = self.context.get("request")
        if request is None:
            return None
        prefetched = getattr(obj, "current_memberships", None)
        if prefetched is not None:
            return prefetched[0].role if prefetched else None
        membership = obj.memberships.filter(user=request.user).first()
        return membership.role if membership else None


class WorkspaceCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    settings = serializers.JSONField(required=False, default=dict)

    def validate_settings(self, value):
        return _validate_settings(value)


class WorkspaceUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    settings = serializers.JSONField(required=False)

    def validate_settings(self, value):
        return _validate_settings(value)


class MembershipSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "role", "created_at"]
        read_only_fields = fields


class AddMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=MANAGEABLE_ROLES, default=Membership.Role.MEMBER
    )


class UpdateMemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=MANAGEABLE_ROLES)
