from rest_framework import serializers

from apps.playground.models import Execution, ExecutionResult
from apps.prompts.serializers import validate_parameters


class ModelSelectionSerializer(serializers.Serializer):
    provider = serializers.UUIDField()
    model_id = serializers.CharField(max_length=200)
    parameters = serializers.JSONField(required=False, default=dict)

    def validate_model_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A model is required.")
        return value

    def validate_parameters(self, value):
        return validate_parameters(value)


class ExecutionCreateSerializer(serializers.Serializer):
    system_prompt = serializers.CharField(required=False, allow_blank=True, default="")
    user_prompt = serializers.CharField()
    parameters = serializers.JSONField(required=False, default=dict)
    prompt = serializers.UUIDField(required=False, allow_null=True)
    models = ModelSelectionSerializer(many=True)

    def validate_parameters(self, value):
        return validate_parameters(value)

    def validate_user_prompt(self, value):
        if not value.strip():
            raise serializers.ValidationError("A user prompt is required.")
        return value

    def validate_models(self, value):
        if not 1 <= len(value) <= 2:
            raise serializers.ValidationError("Select one or two models.")
        seen = set()
        for item in value:
            key = (str(item["provider"]), item["model_id"])
            if key in seen:
                raise serializers.ValidationError("Select two different models to compare.")
            seen.add(key)
        return value


class ExecutionResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExecutionResult
        fields = [
            "id",
            "position",
            "provider",
            "provider_name",
            "provider_kind",
            "model_id",
            "content",
            "input_tokens",
            "output_tokens",
            "tokens_are_provider_reported",
            "latency_ms",
            "finish_reason",
            "request_id",
            "estimated_cost",
            "cost_currency",
            "status",
            "error",
            "created_at",
        ]
        read_only_fields = fields


class ExecutionSerializer(serializers.ModelSerializer):
    results = ExecutionResultSerializer(many=True, read_only=True)

    class Meta:
        model = Execution
        fields = [
            "id",
            "project",
            "prompt",
            "prompt_version",
            "mode",
            "system_prompt",
            "user_prompt",
            "parameters",
            "status",
            "created_by",
            "created_at",
            "results",
        ]
        read_only_fields = fields
