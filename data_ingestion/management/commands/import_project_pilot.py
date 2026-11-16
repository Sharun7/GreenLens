from django.core.management.base import BaseCommand, CommandError

from data_ingestion.pilot import run_official_ingestion


class Command(BaseCommand):
    help = "Import 25-50 actual USGS solar-array polygons, separate from the bond registry."

    def add_arguments(self, parser):
        parser.add_argument("--state", default="TX")
        parser.add_argument("--limit", type=int, default=30)

    def handle(self, *args, **options):
        if not 25 <= options["limit"] <= 50:
            raise CommandError("The initial pilot must contain between 25 and 50 source-mapped projects.")
        try:
            run = run_official_ingestion(options["state"].upper(), options["limit"])
        except Exception as exc:
            raise CommandError(f"Pilot import failed; no synthetic fallback: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Run {run.pk}: {run.status}; {run.result}"))