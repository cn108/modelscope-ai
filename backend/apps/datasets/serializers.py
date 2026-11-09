from rest_framework import serializers

from apps.datasets.models import Dataset, DatasetRecord

MAX_TEXT_LENGTH = 20_000


class DatasetSerializer(serializers.ModelSerializer):
    record_count = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        fields = [
            "id",
            "project",
            "name",
            "description",
            "version",
            "record_count",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_record_count(self, obj) -> int:
        annotated = getattr(obj, "record_count", None)
        if annotated is not None:
            return int(annotated)
        return obj.records.count()


class DatasetCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )


class DatasetUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False)
    description = serializers.CharField(
        max_length=2000, required=False, allow_blank=True
    )


class _RecordValidationMixin:
    def validate_input(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("A record input is required.")
        if len(value) > MAX_TEXT_LENGTH:
            raise serializers.ValidationError(
                f"Input may be at most {MAX_TEXT_LENGTH} characters."
            )
        return value

    def validate_expected_output(self, value):
        value = value or ""
        if len(value) > MAX_TEXT_LENGTH:
            raise serializers.ValidationError(
                f"Expected output may be at most {MAX_TEXT_LENGTH} characters."
            )
        return value

    def validate_context(self, value):
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError(
                "Context must be a string or a list of strings."
            )
        cleaned = [item.strip() for item in value if item.strip()]
        if sum(len(item) for item in cleaned) > 60_000:
            raise serializers.ValidationError("Context is too large.")
        return cleaned

    def validate_metadata(self, value):
        if value in (None, {}):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("Metadata must be a JSON object.")
        if len(str(value)) > 4_096:
            raise serializers.ValidationError("Metadata is too large.")
        return value


class DatasetRecordInputSerializer(_RecordValidationMixin, serializers.Serializer):
    input = serializers.CharField(max_length=MAX_TEXT_LENGTH)
    expected_output = serializers.CharField(
        max_length=MAX_TEXT_LENGTH, required=False, allow_blank=True, default=""
    )
    context = serializers.JSONField(required=False, default=list)
    metadata = serializers.JSONField(required=False, default=dict)


class DatasetRecordUpdateSerializer(_RecordValidationMixin, serializers.Serializer):
    input = serializers.CharField(max_length=MAX_TEXT_LENGTH, required=False)
    expected_output = serializers.CharField(
        max_length=MAX_TEXT_LENGTH, required=False, allow_blank=True
    )
    context = serializers.JSONField(required=False)
    metadata = serializers.JSONField(required=False)


class DatasetRecordSerializer(serializers.ModelSerializer):
    dataset = serializers.UUIDField(read_only=True)

    class Meta:
        model = DatasetRecord
        fields = [
            "id",
            "dataset",
            "position",
            "input",
            "expected_output",
            "context",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DatasetImportSerializer(serializers.Serializer):
    file = serializers.FileField()
    mode = serializers.ChoiceField(choices=["append", "replace"], default="append")

    def validate_file(self, value):
        if value.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("Dataset files may be at most 2 MB.")
        return value
