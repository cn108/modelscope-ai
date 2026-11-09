from rest_framework import serializers

from .models import (
    SecurityClassification,
    SecurityFinding,
    SecurityFindingEvent,
    SecurityScan,
    SecuritySeverity,
)


class SecurityFindingEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()

    class Meta:
        model = SecurityFindingEvent
        fields = [
            "id",
            "from_status",
            "to_status",
            "note",
            "actor",
            "actor_email",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_email(self, obj) -> str:
        return getattr(obj.actor, "email", "") if obj.actor_id else ""


class SecurityFindingSerializer(serializers.ModelSerializer):
    check = serializers.CharField(source="check_key", read_only=True)
    resource = serializers.SerializerMethodField()
    scan_target = serializers.SerializerMethodField()
    reviewed_by_email = serializers.SerializerMethodField()
    status_history = SecurityFindingEventSerializer(
        source="events", many=True, read_only=True
    )

    class Meta:
        model = SecurityFinding
        fields = [
            "id",
            "scan",
            "project",
            "check",
            "category",
            "title",
            "description",
            "severity",
            "disposition",
            "classification",
            "resource",
            "resource_type",
            "resource_id",
            "resource_label",
            "location",
            "evidence",
            "remediation",
            "rule_id",
            "detected_at",
            "execution",
            "execution_result",
            "metadata",
            "status",
            "reviewed_by",
            "reviewed_by_email",
            "reviewed_at",
            "resolved_at",
            "resolution_note",
            "status_history",
            "scan_target",
            "updated_at",
        ]
        read_only_fields = fields

    def get_resource(self, obj) -> dict:
        return {
            "type": obj.resource_type,
            "id": obj.resource_id,
            "label": obj.resource_label,
            "location": obj.location,
        }

    def get_scan_target(self, obj) -> dict:
        scan = obj.scan
        return {
            "id": str(scan.pk),
            "type": scan.target_type,
            "label": scan.target_label,
            "version": scan.target_version,
        }

    def get_reviewed_by_email(self, obj) -> str:
        return getattr(obj.reviewed_by, "email", "") if obj.reviewed_by_id else ""


class SecurityScanSerializer(serializers.ModelSerializer):
    target = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()
    finding_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SecurityScan
        fields = [
            "id",
            "project",
            "target_type",
            "target",
            "target_label",
            "target_identifier",
            "target_version",
            "checks",
            "config",
            "blocking_enabled",
            "blocking_severity",
            "blocking_reason",
            "status",
            "total_items",
            "scanned_items",
            "finding_count",
            "highest_severity",
            "summary",
            "error",
            "created_by",
            "created_by_email",
            "created_at",
            "started_at",
            "completed_at",
        ]
        read_only_fields = fields

    def get_target(self, obj) -> dict:
        return {
            "type": obj.target_type,
            "label": obj.target_label,
            "identifier": obj.target_identifier,
            "version": obj.target_version,
            "dataset": str(obj.dataset_id) if obj.dataset_id else None,
            "prompt": str(obj.prompt_id) if obj.prompt_id else None,
            "execution": str(obj.execution_id) if obj.execution_id else None,
        }

    def get_created_by_email(self, obj) -> str:
        return getattr(obj.created_by, "email", "") if obj.created_by_id else ""


class SecurityScanCreateSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=SecurityScan.TargetType.choices)
    target_id = serializers.UUIDField()
    checks = serializers.ListField(
        child=serializers.CharField(max_length=64), allow_empty=False
    )
    config = serializers.JSONField(required=False, default=dict)
    blocking_enabled = serializers.BooleanField(default=False)
    blocking_severity = serializers.ChoiceField(
        choices=SecuritySeverity.choices,
        required=False,
        default=SecuritySeverity.HIGH,
    )
    blocking_reason = serializers.CharField(
        required=False, allow_blank=True, max_length=2000, default=""
    )

    def validate_config(self, value):
        if value in (None, {}):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("Scan configuration must be an object.")
        return value

    def validate_checks(self, value):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if not cleaned:
            raise serializers.ValidationError("Select at least one check.")
        return list(dict.fromkeys(cleaned))


class SecurityFindingUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=SecurityFinding.Status.choices, required=False
    )
    classification = serializers.ChoiceField(
        choices=SecurityClassification.choices, required=False
    )
    note = serializers.CharField(
        required=False, allow_blank=True, max_length=2000, default=""
    )
