"""Read-only audit event representation for the Settings audit views."""

from rest_framework import serializers

from common.audit.models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default="")

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "action",
            "target_type",
            "target_id",
            "actor",
            "actor_email",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields
