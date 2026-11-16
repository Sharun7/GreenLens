from django.core.management.base import BaseCommand, CommandError

from data_ingestion.models import PilotProject
from greenwash_detector.pilot_evidence import collect_project_evidence


class Command(BaseCommand):
    help = "Collect real S1/S2 evidence over pilot project polygons; never create outcome labels."

    def add_arguments(self, parser):
        parser.add_argument("--project-id")
        parser.add_argument("--limit", type=int, default=30)
        parser.add_argument("--before-start", default="2024-06-01")
        parser.add_argument("--before-end", default="2024-09-01")
        parser.add_argument("--after-start", default="2025-06-01")
        parser.add_argument("--after-end", default="2025-09-01")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 50:
            raise CommandError("Use a batch limit from 1 to 50.")
        query = PilotProject.objects.exclude(review_status="rejected")
        if options["project_id"]:
            query = query.filter(source_id=options["project_id"])
        windows = {key: options[key] for key in ("before_start", "before_end", "after_start", "after_end")}
        if not query.exists():
            raise CommandError("No eligible source-mapped pilot projects are available.")
        for project in query[:options["limit"]]:
            try:
                evidence = collect_project_evidence(project, windows)
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(f"{project.source_id}: {evidence.status}; optical={evidence.optical.get('status')}; SAR={evidence.sar.get('status')}")