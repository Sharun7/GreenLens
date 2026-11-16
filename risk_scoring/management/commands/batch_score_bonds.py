# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Management command: batch_score_bonds
Usage:
    python manage.py batch_score_bonds
    python manage.py batch_score_bonds --limit 100
    python manage.py batch_score_bonds --only-missing   (skip bonds that already have a score)
"""
import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger("greenlens.batch_score_bonds")


class Command(BaseCommand):
    help = "Run PCRS inference for all bonds and save PCRScore records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of bonds to process (default: all).",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            default=False,
            help="Skip bonds that already have a score for the active model version.",
        )

    def handle(self, *args, **options):
        from data_ingestion.models import GreenBond
        from risk_scoring.models import PCRScore
        from risk_scoring.ml_engine import PCRSPredictor

        try:
            predictor = PCRSPredictor()
        except (FileNotFoundError, ValueError) as exc:
            raise CommandError(str(exc)) from None

        qs = GreenBond.objects.all().order_by("pk")

        if options["only_missing"]:
            scored_pks = set(PCRScore.objects.filter(
                model_version=predictor.model_version,
            ).values_list("bond_id", flat=True))
            qs = qs.exclude(pk__in=scored_pks)
            self.stdout.write(f"Skipping {len(scored_pks)} already-scored bonds.")

        if options["limit"] is not None:
            if options["limit"] < 0:
                raise CommandError("--limit must be non-negative")
            qs = qs[: options["limit"]]

        total = qs.count()
        self.stdout.write(f"Scoring {total} bonds …")

        ok = errors = 0
        for i, bond in enumerate(qs.iterator(chunk_size=100), start=1):
            try:
                predictor.predict(bond.pk)
                ok += 1
            except Exception as exc:
                errors += 1
                logger.error("bond pk=%s failed: %s", bond.pk, exc)

            if i % 100 == 0 or i == total:
                self.stdout.write(f"  {i}/{total}  ok={ok}  errors={errors}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {ok} bonds scored, {errors} errors."
        ))
