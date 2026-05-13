# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Management command: python manage.py detect_model_bias

Runs comprehensive bias detection analysis on the PCRS model.
"""
from django.core.management.base import BaseCommand

from risk_scoring.bias_detection import BiasDetector, print_bias_report


class Command(BaseCommand):
    help = "Detect and analyze model bias (geographic, synthetic label, CNN classifier)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--region",
            type=str,
            help="Analyze specific region only (e.g., Europe, Asia, Africa)",
        )
        parser.add_argument(
            "--export-report",
            action="store_true",
            help="Export bias detection report as JSON",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="bias_detection_report.json",
            help="Output filepath for JSON report (default: bias_detection_report.json)",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting bias detection analysis..."))

        detector = BiasDetector()
        results = detector.run_full_analysis()

        # Print to console
        print_bias_report(results)

        # Export if requested
        if options["export_report"]:
            output_path = options["output"]
            detector.export_report(filepath=output_path)
            self.stdout.write(
                self.style.SUCCESS(f"✓ Bias report exported to {output_path}")
            )

        self.stdout.write(self.style.SUCCESS("✓ Bias detection complete"))
