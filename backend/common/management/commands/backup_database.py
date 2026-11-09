"""Create a PostgreSQL custom-format dump and apply retention."""

from django.core.management.base import BaseCommand

from common.backups import apply_retention, create_backup


class Command(BaseCommand):
    help = "Create a PostgreSQL backup and remove expired local backups."

    def add_arguments(self, parser):
        parser.add_argument("--label", default="", help="Optional filename label.")
        parser.add_argument(
            "--keep-days",
            type=int,
            default=None,
            help="Override BACKUP_RETENTION_DAYS for this run.",
        )

    def handle(self, *args, **options):
        path = create_backup(label=options["label"])
        removed = apply_retention(days=options["keep_days"])
        self.stdout.write(f"Backup written: {path} ({path.stat().st_size} bytes)")
        self.stdout.write(f"Expired backups removed: {len(removed)}")
