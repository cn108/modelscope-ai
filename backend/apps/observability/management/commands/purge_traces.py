"""Delete raw traces older than the configured retention window."""

from django.core.management.base import BaseCommand, CommandError

from apps.observability import rollups


class Command(BaseCommand):
    help = (
        "Roll up then delete raw trace rows older than "
        "OBSERVABILITY_TRACE_RETENTION_DAYS. Does nothing when retention is 0."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            help="Override OBSERVABILITY_TRACE_RETENTION_DAYS for this run.",
        )

    def handle(self, *args, **options):
        try:
            result = rollups.purge_old_traces(retention_days=options["days"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(str(result)))
