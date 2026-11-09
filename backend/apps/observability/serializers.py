from rest_framework import serializers

from apps.observability.models import Span, Trace


def _preview(value: str | None, limit: int = 160) -> str:
    text = " ".join((value or "").split())
    return text[:limit]


def _linked_request(trace: Trace) -> str:
    if trace.role == Trace.Role.JUDGE and trace.request_text:
        return trace.request_text
    if trace.execution_result_id and trace.execution_result:
        result = trace.execution_result
        return result.execution.user_prompt if result.execution_id else ""
    if trace.evaluation_result_id and trace.evaluation_result:
        return trace.evaluation_result.input
    return trace.request_text


def _linked_response(trace: Trace) -> str:
    if trace.role == Trace.Role.JUDGE and trace.response_text:
        return trace.response_text
    if trace.execution_result_id and trace.execution_result:
        return trace.execution_result.content
    if trace.evaluation_result_id and trace.evaluation_result:
        return trace.evaluation_result.generated_response
    return trace.response_text


class SpanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Span
        fields = [
            "id",
            "parent",
            "sequence",
            "name",
            "kind",
            "status",
            "started_at",
            "ended_at",
            "duration_ms",
            "attributes",
            "error",
        ]
        read_only_fields = fields


class TraceListSerializer(serializers.ModelSerializer):
    source_label = serializers.SerializerMethodField()
    request_preview = serializers.SerializerMethodField()
    link = serializers.SerializerMethodField()

    class Meta:
        model = Trace
        fields = [
            "id",
            "project",
            "source",
            "source_label",
            "role",
            "status",
            "provider",
            "provider_name",
            "provider_kind",
            "model_id",
            "started_at",
            "ended_at",
            "duration_ms",
            "provider_latency_ms",
            "input_tokens",
            "output_tokens",
            "estimated_cost",
            "cost_currency",
            "cost_status",
            "cost_detail",
            "error",
            "otel_trace_id",
            "request_preview",
            "link",
        ]
        read_only_fields = fields

    def get_source_label(self, obj: Trace) -> str:
        if obj.evaluation_result_id and obj.evaluation_result:
            return obj.evaluation_result.evaluation.dataset_name
        return "Playground"

    def get_request_preview(self, obj: Trace) -> str:
        return _preview(_linked_request(obj))

    def get_link(self, obj: Trace) -> dict:
        if obj.execution_result_id and obj.execution_result:
            result = obj.execution_result
            return {
                "source": "playground",
                "execution_id": str(result.execution_id),
                "result_id": str(result.pk),
            }
        if obj.evaluation_result_id and obj.evaluation_result:
            result = obj.evaluation_result
            return {
                "source": "evaluation",
                "evaluation_id": str(result.evaluation_id),
                "result_id": str(result.pk),
            }
        return {"source": obj.source}


class TraceDetailSerializer(TraceListSerializer):
    request = serializers.SerializerMethodField()
    response = serializers.SerializerMethodField()
    spans = SpanSerializer(many=True, read_only=True)

    class Meta(TraceListSerializer.Meta):
        fields = [*TraceListSerializer.Meta.fields, "request", "response", "spans", "attributes"]
        read_only_fields = fields

    def get_request(self, obj: Trace) -> dict:
        if obj.execution_result_id and obj.execution_result:
            result = obj.execution_result
            execution = result.execution
            return {
                "kind": "playground",
                "system_prompt": execution.system_prompt,
                "user_prompt": execution.user_prompt,
                "parameters": execution.parameters,
                "prompt_version": execution.prompt_version,
                "execution_id": str(execution.pk),
            }
        if obj.evaluation_result_id and obj.evaluation_result:
            result = obj.evaluation_result
            if obj.role == Trace.Role.JUDGE:
                return {
                    "kind": "judge",
                    "prompt": obj.request_text,
                    "note": (
                        "Judge prompts are produced inside the metric library and "
                        "retained here up to 4,000 characters."
                    ),
                    "dataset_name": result.evaluation.dataset_name,
                    "record_position": result.record_position,
                }
            return {
                "kind": "evaluation",
                "input": result.input,
                "expected_output": result.expected_output,
                "context": result.context,
                "evaluation_id": str(result.evaluation_id),
                "dataset_name": result.evaluation.dataset_name,
                "dataset_version": result.evaluation.dataset_version,
                "metrics": result.evaluation.metrics,
                "record_position": result.record_position,
            }
        return {"kind": obj.source}

    def get_response(self, obj: Trace) -> str:
        return _linked_response(obj)
