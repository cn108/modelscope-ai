"""Build daily dashboard rollups from raw traces."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.observability import rollups
from apps.projects.models import Project


class Command(BaseCommand):
    help = "Aggregate completed trace days into dashboard rollups."

    def add_arguments(self, parser):
        parser.add_argument(
            "--through",
            help=(
                "Last day to roll up (ISO date). Defaults to yesterday; today is "
                "never rolled up because it is still accumulating traces."
            ),
        )
        parser.add_argument(
            "--project",
            help="Only roll up this project UUID (default: all projects with traces).",
        )

    def handle(self, *args, **options):
        through = None
        if options["through"]:
            try:
                through = date.fromisoformat(options["through"])
            except ValueError as exc:
                raise CommandError("--through must be an ISO date (YYYY-MM-DD).") from exc

        if options["project"]:
            project = Project.objects.filter(pk=options["project"]).first()
            if project is None:
                raise CommandError("Project not found.")
            try:
                result = rollups.rollup_project(project=project, through_day=through)
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS(str(result)))
            return

        try:
            result = rollups.rollup_all(through_day=through)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(str(result)))
