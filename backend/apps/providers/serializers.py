from rest_framework import serializers

from apps.providers.models import ModelConfig, ProviderConfig
from integrations.providers.adapters import (
    ZAI_BASE_URL,
    validate_lmstudio_endpoint,
    validate_ollama_endpoint,
)

ALLOWED_DEFAULTS = {
    "temperature",
    "top_p",
    "max_tokens",
    "stop",
    "seed",
    "presence_penalty",
    "frequency_penalty",
}


class ProviderConfigSerializer(serializers.ModelSerializer):
    has_secret = serializers.SerializerMethodField()
    models = serializers.SerializerMethodField()

    class Meta:
        model = ProviderConfig
        fields = [
            "id",
            "project",
            "name",
            "kind",
            "endpoint",
            "settings",
            "connection_status",
            "connection_detail",
            "last_tested_at",
            "has_secret",
            "models",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "project",
            "connection_status",
            "connection_detail",
            "last_tested_at",
            "created_at",
            "updated_at",
        ]

    def get_has_secret(self, obj) -> bool:
        return hasattr(obj, "secret")

    def get_models(self, obj) -> list[dict]:
        """Known model ids, readable by any workspace member for the playground."""
        return [
            {
                "id": str(model.id),
                "model_id": model.model_id,
                "display_name": model.display_name,
            }
            for model in obj.models.all()
        ]

    def validate_settings(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Settings must be a JSON object.")
        if set(value) - ALLOWED_DEFAULTS:
            raise serializers.ValidationError("Settings contain unsupported inference options.")
        if len(value) > 16 or any(not isinstance(key, str) or len(key) > 64 for key in value):
            raise serializers.ValidationError("Provider settings are too large or invalid.")
        if len(str(value)) > 4096:
            raise serializers.ValidationError("Provider settings are too large.")
        return value

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        endpoint = attrs.get("endpoint", getattr(self.instance, "endpoint", ""))
        if kind == ProviderConfig.Kind.ZAI:
            if endpoint and endpoint.rstrip("/") != ZAI_BASE_URL:
                raise serializers.ValidationError({"endpoint": "Z.ai uses its verified API endpoint and cannot be overridden."})
            attrs["endpoint"] = ZAI_BASE_URL
        elif kind == ProviderConfig.Kind.OLLAMA:
            try:
                attrs["endpoint"] = validate_ollama_endpoint(endpoint or "http://localhost:11434/api")
            except ValueError as exc:
                raise serializers.ValidationError({"endpoint": str(exc)}) from exc
        elif kind == ProviderConfig.Kind.LMSTUDIO:
            try:
                attrs["endpoint"] = validate_lmstudio_endpoint(
                    endpoint or "http://localhost:1234/v1"
                )
            except ValueError as exc:
                raise serializers.ValidationError({"endpoint": str(exc)}) from exc
        return attrs


class ProviderCreateSerializer(ProviderConfigSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=False, trim_whitespace=False)

    class Meta(ProviderConfigSerializer.Meta):
        fields = [*ProviderConfigSerializer.Meta.fields, "api_key"]
        read_only_fields = ProviderConfigSerializer.Meta.read_only_fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        kind = attrs.get("kind")
        if kind == ProviderConfig.Kind.ZAI and not attrs.get("api_key"):
            raise serializers.ValidationError({"api_key": "An API key is required for Z.ai."})
        if kind == ProviderConfig.Kind.OLLAMA and attrs.get("api_key"):
            raise serializers.ValidationError({"api_key": "Local Ollama does not use a key."})
        return attrs


class ProviderUpdateSerializer(ProviderConfigSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=False, trim_whitespace=False)

    class Meta(ProviderConfigSerializer.Meta):
        fields = [*ProviderConfigSerializer.Meta.fields, "api_key"]
        read_only_fields = ProviderConfigSerializer.Meta.read_only_fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if "kind" in attrs and self.instance and attrs["kind"] != self.instance.kind:
            raise serializers.ValidationError({"kind": "Provider type cannot be changed; create a new provider."})
        if self.instance and self.instance.kind == ProviderConfig.Kind.OLLAMA and attrs.get("api_key"):
            raise serializers.ValidationError({"api_key": "Local Ollama does not use a key."})
        return attrs


class ModelConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelConfig
        fields = ["id", "provider", "model_id", "display_name", "defaults", "created_at"]
        read_only_fields = fields
