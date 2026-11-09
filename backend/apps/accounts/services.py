"""Registration / account services and serializers.

Business logic lives here, not in views (§1 agent rules).
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.accounts.models import User
from common.audit.services import record_event

DEFAULT_PREFERENCES = {
    "timezone": "UTC",
    "date_format": "medium",
    "default_workspace": None,
    "landing_page": "dashboard",
}
DATE_FORMATS = {"medium", "short", "iso"}
LANDING_PAGES = {"dashboard", "workspaces", "playground"}
PREFERENCE_KEYS = set(DEFAULT_PREFERENCES)


def _validate_preferences(value, *, user) -> dict:
    if not isinstance(value, dict):
        raise serializers.ValidationError("Preferences must be a JSON object.")
    if set(value) - PREFERENCE_KEYS:
        raise serializers.ValidationError("Preferences contain unsupported keys.")

    timezone_name = str(value.get("timezone", "UTC")).strip() or "UTC"
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise serializers.ValidationError(
            {"timezone": "Choose a valid IANA time zone, for example Europe/London."}
        ) from exc

    date_format = str(value.get("date_format", "medium")).strip()
    if date_format not in DATE_FORMATS:
        raise serializers.ValidationError({"date_format": "Unsupported date format."})

    landing_page = str(value.get("landing_page", "dashboard")).strip()
    if landing_page not in LANDING_PAGES:
        raise serializers.ValidationError({"landing_page": "Unsupported landing page."})

    default_workspace = value.get("default_workspace")
    if default_workspace in ("", None):
        default_workspace = None
    else:
        membership = user.workspace_memberships.filter(
            workspace_id=default_workspace
        ).first()
        if membership is None:
            raise serializers.ValidationError(
                {"default_workspace": "Choose a workspace you belong to."}
            )
        default_workspace = str(membership.workspace_id)

    return {
        "timezone": timezone_name,
        "date_format": date_format,
        "default_workspace": default_workspace,
        "landing_page": landing_page,
    }


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    display_name = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_password(self, value: str) -> str:
        # Django validators (length/complexity) — raises on weak passwords.
        password_validation.validate_password(value)
        return value


class UserProfileSerializer(serializers.ModelSerializer):
    preferences = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "preferences", "created_at"]
        read_only_fields = fields

    def get_preferences(self, obj) -> dict:
        return {**DEFAULT_PREFERENCES, **(obj.preferences or {})}


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    preferences = serializers.JSONField(required=False)

    class Meta:
        model = User
        fields = ["display_name", "preferences"]

    def validate_display_name(self, value: str) -> str:
        return value.strip()[:200]

    def validate_preferences(self, value):
        return _validate_preferences(value, user=self.instance)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(
        write_only=True, min_length=8, trim_whitespace=False
    )

    def validate_new_password(self, value: str) -> str:
        password_validation.validate_password(value)
        return value


def update_profile(*, user, validated_data) -> User:
    fields = []
    for field in ("display_name", "preferences"):
        if field in validated_data:
            value = validated_data[field]
            if field == "display_name":
                value = value.strip()
            else:
                value = {**DEFAULT_PREFERENCES, **(value or {})}
            setattr(user, field, value)
            fields.append(field)
    if fields:
        user.save(update_fields=[*fields, "updated_at"])
        record_event(
            actor=user,
            action="account.profile_updated",
            target_type="user",
            target_id=user.pk,
            metadata={"fields": fields},
        )
    return user


def change_password(*, user, current_password: str, new_password: str) -> int:
    """Change the password and revoke every outstanding refresh token.

    Access tokens are short-lived; revoking refresh tokens means no other browser
    can silently mint a new access token after a password change.
    """
    if not user.check_password(current_password):
        raise serializers.ValidationError(
            {"current_password": "The current password is incorrect."}
        )
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])

    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    revoked = 0
    for token in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        revoked += 1 if created else 0
    record_event(
        actor=user,
        action="account.password_changed",
        target_type="user",
        target_id=user.pk,
        metadata={"refresh_tokens_revoked": revoked},
    )
    return revoked


def register_user(*, email: str, password: str, display_name: str = "") -> User:
    """Create a user atomically; normalise email case (§7 integrity)."""
    email = email.strip().lower()
    if User.objects.filter(email=email).exists():
        raise ValueError("An account with this email already exists.")
    try:
        with transaction.atomic():
            return User.objects.create_user(
                email=email, password=password, display_name=display_name.strip()
            )
    except (IntegrityError, DjangoValidationError) as exc:
        raise ValueError("An account with this email already exists.") from exc
