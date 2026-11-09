"""Benchmark the dashboard against a synthetic production-sized dataset."""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.observability.benchmark import (
    cleanup_benchmark,
    measure_dashboard,
    seed_benchmark,
)


class Command(BaseCommand):
    help = (
        "Seed a temporary project with synthetic rollups and raw traces, then "
        "measure the dashboard service's latency and query count. The temporary "
        "workspace is deleted unless --keep is supplied."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Owner of the temporary benchmark workspace.")
        parser.add_argument("--days", type=int, default=365, help="Rolled-up days (default 365).")
        parser.add_argument("--models", type=int, default=20, help="Models per rollup bucket (default 20).")
        parser.add_argument("--providers", type=int, default=4, help="Providers per rollup bucket (default 4).")
        parser.add_argument("--raw-traces", type=int, default=10_000, help="Current-day raw traces (default 10000).")
        parser.add_argument("--calls-per-bucket", type=int, default=100, help="Calls represented by each rollup bucket (default 100).")
        parser.add_argument("--runs", type=int, default=5, help="Measured dashboard runs (default 5).")
        parser.add_argument("--keep", action="store_true", help="Keep the temporary project for inspection.")

    def handle(self, *args, **options):
        User = get_user_model()
        user = (
            User.objects.filter(email=options["email"], is_active=True).first()
            if options["email"]
            else User.objects.filter(is_active=True).first()
        )
        if user is None:
            raise CommandError("An active user is required to own the benchmark workspace.")

        try:
            dataset = seed_benchmark(
                user=user,
                days=options["days"],
                models=options["models"],
                providers=options["providers"],
                raw_traces=options["raw_traces"],
                calls_per_bucket=options["calls_per_bucket"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        try:
            result = measure_dashboard(dataset=dataset, runs=options["runs"])
            result["project"] = str(dataset.project.pk)
            result["workspace"] = str(dataset.workspace.pk)
            self.stdout.write(self.style.SUCCESS(json.dumps(result, indent=2)))
        finally:
            if options["keep"]:
                self.stdout.write(
                    self.style.WARNING(
                        "Benchmark workspace kept: "
                        f"{dataset.workspace.pk} / project {dataset.project.pk}"
                    )
                )
            else:
                cleanup_benchmark(dataset)
                self.stdout.write(self.style.SUCCESS("Benchmark workspace removed."))
