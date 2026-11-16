import json
from pathlib import Path

import joblib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from risk_scoring.pilot_evaluation import evaluate_pilot, reviewed_outcome_rows


class Command(BaseCommand):
    help = "Evaluate the independent-outcome XGBoost baseline without replacing production artifacts."

    def add_arguments(self, parser):
        parser.add_argument("--train-before", required=True)
        parser.add_argument("--calibrate-before", required=True)
        parser.add_argument("--held-out-counties", nargs="+", required=True)
        parser.add_argument("--alpha", type=float, default=0.1)

    def handle(self, *args, **options):
        rows = reviewed_outcome_rows()
        try:
            model, report = evaluate_pilot(rows, options["train_before"], options["calibrate_before"], options["held_out_counties"], options["alpha"])
        except (ValueError, KeyError, TypeError) as exc:
            raise CommandError(f"Evaluation blocked; no model was published: {exc}") from exc
        directory = Path(settings.BASE_DIR) / "data" / "cache" / "project_pilot" / report["dataset_sha256"][:16]
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, directory / "xgboost_damage_baseline.pkl")
        (directory / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Held-out report saved to {directory}; production PCRS was not replaced."))