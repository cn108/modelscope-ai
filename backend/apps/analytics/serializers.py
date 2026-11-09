from rest_framework import serializers

from .models import AnalyticsReport
from .reporting import REPORT_SECTIONS, build_report_document
from .services import SOURCES


class AnalyticsReportCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    provider = serializers.UUIDField(required=False, allow_null=True)
    model = serializers.CharField(max_length=200, required=False, allow_blank=True)
    source = serializers.ChoiceField(choices=sorted(SOURCES), required=False, allow_blank=True)
    sections = serializers.ListField(
        child=serializers.ChoiceField(choices=list(REPORT_SECTIONS)),
        required=False,
        allow_empty=False,
    )

    def to_internal_value(self, data):
        # The API accepts the same ``from``/``to`` names as the analytics
        # filters.  ``from`` is a Python keyword, so the serializer keeps
        # internal aliases while preserving the public request shape.
        mutable = data.copy() if hasattr(data, "copy") else dict(data)
        if "from" in mutable and "from_date" not in mutable:
            mutable["from_date"] = mutable.get("from")
        if "to" in mutable and "to_date" not in mutable:
            mutable["to_date"] = mutable.get("to")
        return super().to_internal_value(mutable)

    def validate_sections(self, value):
        seen = []
        for key in value:
            if key not in seen:
                seen.append(key)
        return seen


class AnalyticsReportListSerializer(serializers.ModelSerializer):
    section_labels = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = AnalyticsReport
        fields = [
            "id",
            "project",
            "title",
            "sections",
            "section_labels",
            "period_from",
            "period_to",
            "filters",
            "scope",
            "schema_version",
            "created_by",
            "created_by_email",
            "created_at",
        ]
        read_only_fields = fields

    def get_section_labels(self, obj) -> list[str]:
        return [REPORT_SECTIONS.get(key, key) for key in obj.sections or []]

    def get_created_by_email(self, obj) -> str:
        return obj.created_by.email if obj.created_by else ""


class AnalyticsReportDetailSerializer(AnalyticsReportListSerializer):
    document = serializers.SerializerMethodField()

    class Meta(AnalyticsReportListSerializer.Meta):
        fields = [*AnalyticsReportListSerializer.Meta.fields, "document"]
        read_only_fields = fields

    def get_document(self, obj) -> dict:
        return build_report_document(obj)
