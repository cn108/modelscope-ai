from rest_framework import serializers

from apps.prompts.models import Prompt, PromptVersion

ALLOWED_PARAMETERS = {
    "temperature",
    "top_p",
    "max_tokens",
    "stop",
    "seed",
    "presence_penalty",
    "frequency_penalty",
}


def validate_parameters(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise serializers.ValidationError("Parameters must be a JSON object.")
    if set(value) - ALLOWED_PARAMETERS:
        raise serializers.ValidationError("Parameters contain unsupported inference options.")
    if len(str(value)) > 2048:
        raise serializers.ValidationError("Parameters are too large.")
    return value


class PromptVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptVersion
        fields = [
            "id",
            "version_number",
            "system_prompt",
            "user_prompt",
            "parameters",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class PromptSerializer(serializers.ModelSerializer):
    current_version = serializers.SerializerMethodField()
    version_count = serializers.SerializerMethodField()

    class Meta:
        model = Prompt
        fields = [
            "id",
            "project",
            "name",
            "description",
            "current_version",
            "version_count",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _versions(self, obj):
        # Uses the prefetch cache when present; never issues per-row queries.
        return list(obj.versions.all())

    def get_current_version(self, obj):
        versions = self._versions(obj)
        if not versions:
            return None
        latest = max(versions, key=lambda item: item.version_number)
        return PromptVersionSerializer(latest).data

    def get_version_count(self, obj) -> int:
        return len(self._versions(obj))


class PromptCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(
        max_length=400, required=False, allow_blank=True, default=""
    )
    system_prompt = serializers.CharField(required=False, allow_blank=True, default="")
    user_prompt = serializers.CharField()
    parameters = serializers.JSONField(required=False, default=dict)

    def validate_parameters(self, value):
        return validate_parameters(value)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A prompt name is required.")
        return value

    def validate_user_prompt(self, value):
        if not value.strip():
            raise serializers.ValidationError("A user prompt is required.")
        return value


class PromptUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False)
    description = serializers.CharField(max_length=400, required=False, allow_blank=True)
    system_prompt = serializers.CharField(required=False, allow_blank=True)
    user_prompt = serializers.CharField(required=False)
    parameters = serializers.JSONField(required=False)

    def validate_parameters(self, value):
        return validate_parameters(value)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A prompt name is required.")
        return value

    def validate_user_prompt(self, value):
        if not value.strip():
            raise serializers.ValidationError("A user prompt is required.")
        return value


class RestoreVersionSerializer(serializers.Serializer):
    version_number = serializers.IntegerField(min_value=1)
