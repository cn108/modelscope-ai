from rest_framework import serializers

from apps.evaluations.models import Evaluation, EvaluationModel, EvaluationResult
from apps.prompts.serializers import validate_parameters


class EvaluationModelSelectionSerializer(serializers.Serializer):
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


class JudgeSelectionSerializer(serializers.Serializer):
    provider = serializers.UUIDField()
    model_id = serializers.CharField(max_length=200)
    parameters = serializers.JSONField(required=False, default=dict)

    def validate_model_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A judge model is required.")
        return value

    def validate_parameters(self, value):
        return validate_parameters(value)


class EvaluationCreateSerializer(serializers.Serializer):
    dataset = serializers.UUIDField()
    metrics = serializers.ListField(
        child=serializers.CharField(max_length=64), allow_empty=False
    )
    models = EvaluationModelSelectionSerializer(many=True)
    parameters = serializers.JSONField(required=False, default=dict)
    judge = JudgeSelectionSerializer(required=False, allow_null=True)

    def validate_parameters(self, value):
        return validate_parameters(value)

    def validate_metrics(self, value):
        cleaned = [str(item).strip() for item in value]
        if any(not item for item in cleaned):
            raise serializers.ValidationError("Metric keys cannot be empty.")
        return cleaned

    def validate_models(self, value):
        if not 1 <= len(value) <= 5:
            raise serializers.ValidationError("Select between 1 and 5 models.")
        seen = set()
        for item in value:
            key = (str(item["provider"]), item["model_id"])
            if key in seen:
                raise serializers.ValidationError("Each selected model must be different.")
            seen.add(key)
        return value


class EvaluationModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvaluationModel
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
        ]
        read_only_fields = fields


class EvaluationSerializer(serializers.ModelSerializer):
    models = EvaluationModelSerializer(many=True, read_only=True)
    judge = serializers.SerializerMethodField()
    total_results = serializers.SerializerMethodField()

    class Meta:
        model = Evaluation
        fields = [
            "id",
            "project",
            "dataset",
            "dataset_name",
            "dataset_version",
            "status",
            "metrics",
            "parameters",
            "judge",
            "total_cases",
            "total_results",
            "completed_cases",
            "failed_cases",
            "summary",
            "error",
            "created_by",
            "created_at",
            "started_at",
            "completed_at",
            "models",
        ]
        read_only_fields = fields

    def get_judge(self, obj):
        if not obj.judge_model_id:
            return None
        return {
            "provider": str(obj.judge_provider_id) if obj.judge_provider_id else None,
            "provider_name": obj.judge_provider_name,
            "model_id": obj.judge_model_id,
        }

    def get_total_results(self, obj) -> int:
        """Progress is per model/case pair: records multiplied by models."""
        return obj.total_cases * len(obj.models.all())


class EvaluationResultSerializer(serializers.ModelSerializer):
    model = serializers.UUIDField(read_only=True)
    model_id = serializers.CharField(source="model.model_id", read_only=True)
    provider_name = serializers.CharField(source="model.provider_name", read_only=True)
    position = serializers.IntegerField(source="model.position", read_only=True)

    class Meta:
        model = EvaluationResult
        fields = [
            "id",
            "model",
            "model_id",
            "provider_name",
            "position",
            "record_position",
            "input",
            "expected_output",
            "context",
            "generated_response",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "status",
            "scores",
            "metric_results",
            "error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class EvaluationMetricCatalogSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    requires_expected_output = serializers.BooleanField()
    requires_context = serializers.BooleanField()
    requires_judge = serializers.BooleanField()
    threshold = serializers.FloatField(allow_null=True)
    source = serializers.CharField()
