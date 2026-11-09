"""Optional OpenTelemetry tracing for model execution.

Observability records live in the database (see ``apps.observability``) so the
dashboard and trace explorer work without an external collector.  At the same
time, each provider call and metric evaluation is wrapped in a real
OpenTelemetry span.  When ``OTEL_EXPORTER_OTLP_ENDPOINT`` is configured the
spans are exported over OTLP/HTTP; otherwise they are still created and
discarded, which keeps local development quiet but preserves the same
instrumentation path in production.

Nothing here may break an execution.  Missing packages, an unreachable
collector, or a malformed endpoint are reported through the returned status and
never raised into a model call.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from django.conf import settings

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_PROVIDER = None
_TRACER = None
_CONFIGURED = False
_STATUS: dict[str, Any] = {
    "enabled": False,
    "exported": False,
    "detail": "OpenTelemetry tracing has not been configured.",
}


@dataclass
class SpanHandle:
    """Small, dependency-free handle around an OTel span."""

    span: Any = None

    @property
    def trace_id(self) -> str:
        if self.span is None:
            return ""
        try:
            context = self.span.get_span_context()
            return format(context.trace_id, "032x") if context.is_valid else ""
        except Exception:  # noqa: BLE001 - telemetry must never break callers
            return ""

    def set_attribute(self, key: str, value: Any) -> None:
        if self.span is None or value is None:
            return
        try:
            self.span.set_attribute(key, value)
        except Exception:  # noqa: BLE001
            pass

    def record_error(self, error: dict[str, Any] | None) -> None:
        if self.span is None or not error:
            return
        try:
            from opentelemetry.trace import Status, StatusCode

            self.span.set_attribute("error.category", str(error.get("category", "")))
            self.span.set_attribute("error.message", str(error.get("message", ""))[:400])
            self.span.set_status(Status(StatusCode.ERROR))
        except Exception:  # noqa: BLE001
            pass


def configure_tracing() -> dict[str, Any]:
    """Initialise the OTel tracer provider once, honouring settings.

    Safe to call from ``AppConfig.ready()`` and from tests.  The function never
    raises; callers can inspect the returned status for diagnostics.
    """
    global _PROVIDER, _TRACER, _CONFIGURED, _STATUS

    with _LOCK:
        if _CONFIGURED:
            return dict(_STATUS)

        _CONFIGURED = True
        if not getattr(settings, "OTEL_TRACING_ENABLED", True):
            _STATUS = {
                "enabled": False,
                "exported": False,
                "detail": "OpenTelemetry tracing is disabled by configuration.",
            }
            return dict(_STATUS)

        try:
            from opentelemetry import trace as trace_api
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError:
            _STATUS = {
                "enabled": False,
                "exported": False,
                "detail": "The OpenTelemetry SDK is not installed.",
            }
            logger.warning("OpenTelemetry SDK unavailable; database traces still record.")
            return dict(_STATUS)

        service_name = getattr(settings, "OTEL_SERVICE_NAME", "modelscope-ai")
        provider = TracerProvider(
            resource=Resource.create({"service.name": service_name})
        )
        endpoint = (getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "") or "").strip()
        exported = False
        detail = "Spans are recorded in-process; no OTLP endpoint is configured."
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )

                provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
                )
                exported = True
                detail = f"Spans are exported over OTLP/HTTP to {endpoint}."
            except ImportError:
                detail = (
                    "OTLP endpoint configured but the OTLP exporter package is not "
                    "installed; spans stay in-process."
                )
                logger.warning(detail)
            except Exception as exc:  # noqa: BLE001 - bad endpoint must not crash boot
                detail = f"OTLP exporter could not be configured: {exc.__class__.__name__}."
                logger.warning(detail)

        trace_api.set_tracer_provider(provider)
        _PROVIDER = provider
        _TRACER = provider.get_tracer("modelscope.observability")
        _STATUS = {
            "enabled": True,
            "exported": exported,
            "detail": detail,
            "service_name": service_name,
        }
        return dict(_STATUS)


def tracing_status() -> dict[str, Any]:
    """Report whether OTel is active and exporting (never claims more)."""
    status = dict(_STATUS)
    status["provider_configured"] = _PROVIDER is not None
    return status


def _tracer():
    if not _CONFIGURED:
        configure_tracing()
    return _TRACER


@contextmanager
def model_call_span(
    name: str, *, attributes: dict[str, Any] | None = None
) -> Iterator[SpanHandle]:
    """Create a CLIENT span for a provider call and always end it.

    The caller measures its own duration; this helper only produces the OTel
    span/trace id and records errors.  Any OTel failure degrades to a no-op.
    """
    tracer = _tracer()
    span = None
    if tracer is not None:
        try:
            from opentelemetry.trace import SpanKind

            span = tracer.start_span(name, kind=SpanKind.CLIENT)
            for key, value in (attributes or {}).items():
                if value is not None:
                    span.set_attribute(key, value)
        except Exception:  # noqa: BLE001
            span = None

    handle = SpanHandle(span)
    try:
        yield handle
    except Exception as exc:
        if span is not None:
            try:
                span.record_exception(exc)
                from opentelemetry.trace import Status, StatusCode

                span.set_status(Status(StatusCode.ERROR))
            except Exception:  # noqa: BLE001
                pass
        raise
    finally:
        if span is not None:
            try:
                span.end()
            except Exception:  # noqa: BLE001
                pass
