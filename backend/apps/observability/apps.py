from django.apps import AppConfig


class ObservabilityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.observability"
    verbose_name = "Observability"

    def ready(self) -> None:
        # Configure OpenTelemetry once per process; database traces do not
        # depend on an exporter being present.
        from integrations.telemetry.tracing import configure_tracing

        configure_tracing()
