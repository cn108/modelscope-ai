"""Registration / account services and serializers.

Business logic lives here, not in views (§1 agent rules).
"""

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.accounts.models import User


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    display_name = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_password(self, value: str) -> str:
        # Django validators (length/complexity) — raises on weak passwords.
        password_validation.validate_password(value)
        return value


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "display_name", "created_at"]
        read_only_fields = fields


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
