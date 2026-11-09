from rest_framework import serializers

from apps.prompts.serializers import validate_parameters
from integrations.security_testing import registry

from .models import SecurityTestModel, SecurityTestResult, SecurityTestRun


class SecurityTestModelSelectionSerializer(serializers.Serializer):
    provider = serializers.UUIDField()
    model_id = serializers.CharField(max_length=200)
    parameters = serializers.JSONField(required=False, default=dict)

    def validate_model_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A model id is required.")
        return value

    def validate_parameters(self, value):
        return validate_parameters(value)


class SecurityTestRunCreateSerializer(serializers.Serializer):
    models = SecurityTestModelSelectionSerializer(many=True, allow_empty=False)
    cases = serializers.ListField(
        child=serializers.CharField(max_length=120),
        required=False,
        allow_empty=True,
        default=list,
    )
    categories = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        allow_empty=True,
        default=list,
    )
    parameters = serializers.JSONField(required=False, default=dict)

    def validate_models(self, value):
        if not 1 <= len(value) <= 5:
            raise serializers.ValidationError("Select between 1 and 5 models.")
        seen = set()
        for item in value:
            key = (str(item["provider"]), item["model_id"].strip())
            if key in seen:
                raise serializers.ValidationError("Each selected model must be different.")
            seen.add(key)
        return value

    def validate_cases(self, value):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if not cleaned:
            return []
        try:
            return list(registry.validate_cases(cleaned))
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_categories(self, value):
        if not value:
            return []
        try:
            return list(registry.validate_categories(value))
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_parameters(self, value):
        return validate_parameters(value)

    def validate(self, attrs):
        if not attrs.get("cases") and not attrs.get("categories"):
            raise serializers.ValidationError(
                {"cases": "Select at least one security test case or category."}
            )
        return attrs


class SecurityTestModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecurityTestModel
        fields = [
            "id",
            "position",
            "provider",
            "provider_name",
            "provider_kind",
            "model_id",
            "parameters",
            "status",
            "summary",
            "error",
            "created_at",
        ]
        read_only_fields = fields


class SecurityTestResultListSerializer(serializers.ModelSerializer):
    model_id = serializers.CharField(source="model.model_id", read_only=True)
    provider_name = serializers.CharField(source="model.provider_name", read_only=True)
    provider_kind = serializers.CharField(source="model.provider_kind", read_only=True)
    position = serializers.IntegerField(source="model.position", read_only=True)

    class Meta:
        model = SecurityTestResult
        fields = [
            "id",
            "run",
            "model",
            "model_id",
            "provider_name",
            "provider_kind",
            "position",
            "case_key",
            "case_name",
            "category",
            "category_label",
            "technique",
            "status",
            "verdict",
            "severity",
            "rationale",
            "evidence",
            "matched_rules",
            "duration_ms",
            "input_tokens",
            "output_tokens",
            "error",
            "executed_at",
            "created_at",
        ]
        read_only_fields = fields


class SecurityTestResultDetailSerializer(SecurityTestResultListSerializer):
    class Meta(SecurityTestResultListSerializer.Meta):
        fields = [
            *SecurityTestResultListSerializer.Meta.fields,
            "system_prompt",
            "attack_input",
            "response_text",
            "criteria",
            "mitigation",
            "references",
            "provider_request_id",
            "updated_at",
        ]
        read_only_fields = fields


class SecurityTestRunSerializer(serializers.ModelSerializer):
    models = SecurityTestModelSerializer(many=True, read_only=True)
    created_by_email = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = SecurityTestRun
        fields = [
            "id",
            "project",
            "case_keys",
            "categories",
            "parameters",
            "status",
            "total_models",
            "total_cases",
            "total_results",
            "completed_results",
            "progress",
            "summary",
            "error",
            "created_by",
            "created_by_email",
            "created_at",
            "started_at",
            "completed_at",
            "models",
        ]
        read_only_fields = fields

    def get_created_by_email(self, obj) -> str:
        return getattr(obj.created_by, "email", "") if obj.created_by_id else ""

    def get_progress(self, obj) -> int:
        if not obj.total_results:
            return 0
        return min(100, round((obj.completed_results / obj.total_results) * 100))
