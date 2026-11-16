import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from risk_scoring.pilot_benchmark import benchmark_encoders
from risk_scoring.pilot_evaluation import reviewed_outcome_rows


class Command(BaseCommand):
    help = "Compare exported ResNet/Prithvi/SatMAE predictions against the same frozen independent-outcome test projects."

    def add_arguments(self, parser):
        parser.add_argument("--evaluation", required=True)
        parser.add_argument("--predictions", required=True)

    def handle(self, *args, **options):
        try:
            evaluation = json.loads(Path(options["evaluation"]).read_text(encoding="utf-8"))
            bundles = json.loads(Path(options["predictions"]).read_text(encoding="utf-8"))
            report = benchmark_encoders(reviewed_outcome_rows(), evaluation, bundles)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise CommandError(f"Encoder comparison blocked: {exc}") from exc
        self.stdout.write(json.dumps(report, indent=2, allow_nan=False))