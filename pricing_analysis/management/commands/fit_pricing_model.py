# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Management command: fit_pricing_model

Trains the PricingGapAnalyser regression model on existing DB data and
re-scores all bonds with the trained model's σ-based mispricing threshold.

Usage:
    python manage.py fit_pricing_model
    python manage.py fit_pricing_model --rescore
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger("greenlens.fit_pricing_model")


class Command(BaseCommand):
    help = (
        "Fit the PricingGapAnalyser regression model on current DB data "
        "and optionally re-score all bonds with the trained model."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--rescore",
            action="store_true",
            default=False,
            help="After fitting, re-analyse all bonds to update predicted spreads and mispricing flags.",
        )

    def handle(self, *args, **options):
        from pricing_analysis.analyser import PricingGapAnalyser
        from pricing_analysis.models import PricingGap

        analyser = PricingGapAnalyser()

        # ── Step 1: Fit the model ─────────────────────────────────────────
        self.stdout.write("Fitting PricingGapAnalyser from DB data...")
        try:
            metrics = analyser.fit_from_db()
        except ValueError as exc:
            self.stderr.write(self.style.ERROR(f"Cannot fit model: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Model fitted: R²_train={metrics['r2_train']:.4f}  "
            f"R²_test={metrics['r2_test']:.4f}  "
            f"gap_std={metrics['gap_std_bps']:.1f} bps  "
            f"n_samples={metrics['n_total']}"
        ))

        # ── Step 2: Optionally re-score all bonds ─────────────────────────
        if options["rescore"]:
            self.stdout.write("Re-scoring all bonds with fitted model...")
            gap_pks = list(
                PricingGap.objects
                .select_related("bond")
                .values_list("bond__pk", flat=True)
                .distinct()
            )

            ok = errors = 0
            total = len(gap_pks)

            for i, bond_pk in enumerate(gap_pks, start=1):
                try:
                    analyser.analyse(bond_pk)
                    ok += 1
                except Exception as exc:
                    errors += 1
                    logger.warning("bond pk=%s rescore failed: %s", bond_pk, exc)

                if i % 200 == 0 or i == total:
                    self.stdout.write(f"  {i}/{total}  ok={ok}  errors={errors}")

            self.stdout.write(self.style.SUCCESS(
                f"Re-scored {ok} bonds, {errors} errors."
            ))

        # ── Step 3: Print summary ─────────────────────────────────────────
        summary = analyser.get_market_summary()
        self.stdout.write(
            f"\nMarket summary after fit:\n"
            f"  Total bonds:     {summary['n_total']}\n"
            f"  Underpriced:     {summary['n_underpriced']} ({summary['pct_underpricing_risk']:.1f}%)\n"
            f"  Overpriced:      {summary['n_overpriced']} ({summary['pct_overpricing_risk']:.1f}%)\n"
            f"  Fairly priced:   {summary['n_fairly_priced']}\n"
            f"  Mean gap:        {summary['mean_gap_bps']:.2f} bps\n"
            f"  Mispriced (>sigma):  "
            f"{PricingGap.objects.filter(is_mispriced=True).count()}"
        )
