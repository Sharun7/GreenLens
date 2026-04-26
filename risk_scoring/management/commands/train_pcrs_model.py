"""
Management command: train_pcrs_model
Usage:
    python manage.py train_pcrs_model
    python manage.py train_pcrs_model --bond-ids 1 2 3   (subset)
"""
from django.core.management.base import BaseCommand
from risk_scoring.ml_engine import train_pcrs_model


class Command(BaseCommand):
    help = "Train the PCRS XGBoost model and save artefacts to models/"

    def add_arguments(self, parser):
        parser.add_argument(
            "--bond-ids",
            nargs="+",
            type=int,
            metavar="PK",
            help="Restrict training to specific bond PKs (default: all).",
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting PCRS model training …")
        try:
            metrics = train_pcrs_model(bond_ids=options.get("bond_ids"))
        except ValueError as exc:
            self.stderr.write(self.style.ERROR(f"Training failed: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS("\n── Training complete ──────────────────"))
        self.stdout.write(f"  R²   : {metrics['r2']}")
        self.stdout.write(f"  RMSE : {metrics['rmse']}")
        self.stdout.write(f"  MAE  : {metrics['mae']}")
        self.stdout.write(f"  Train samples : {metrics['n_train']}")
        self.stdout.write(f"  Val samples   : {metrics['n_val']}")
        self.stdout.write(f"  Test samples  : {metrics['n_test']}")
        self.stdout.write(f"  Best iteration: {metrics['best_iteration']}")
        self.stdout.write(f"  Model version : {metrics['model_version']}")
        self.stdout.write("────────────────────────────────────────\n")
        self.stdout.write("  Model → models/pcrs_model_v1.pkl")
        self.stdout.write("  Scaler → models/pcrs_scaler_v1.pkl")
        self.stdout.write("  SHAP plot → models/shap_summary.png")
