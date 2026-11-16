# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Management command: train_pcrs_model
Usage:
    python manage.py train_pcrs_model
    python manage.py train_pcrs_model --bond-ids 1 2 3   (subset)
"""
from django.core.management.base import BaseCommand, CommandError
from risk_scoring.ml_engine import train_pcrs_model


class Command(BaseCommand):
    help = "Train the PCRS XGBoost model and save artefacts to models/"

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", help="Artifact directory (default: models/pcrs_v2)")
        parser.add_argument("--no-plot", action="store_true", help="Skip the optional SHAP summary PNG")
        parser.add_argument("--allow-demo", action="store_true", help="Explicitly allow known demo hazards; output remains a proxy research model")
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
            metrics = train_pcrs_model(
                bond_ids=options.get("bond_ids"), output_dir=options.get("output_dir"),
                make_plot=not options["no_plot"], allow_demo=options["allow_demo"],
            )
        except ValueError as exc:
            raise CommandError(f"Training failed: {exc}") from None

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
        self.stdout.write(f"  Artifacts: {metrics['artifact_dir']}")
        self.stdout.write("  Target: hazard-derived proxy; metrics are not observed-loss validation.")
