# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Management command to initialize demo data for all features.
This runs automatically during deployment to populate pricing, risk scores, etc.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from data_ingestion.models import GreenBond
from risk_scoring.models import PCRScore, BiasDetectionResult
from pricing_analysis.models import PricingGap
import random


class Command(BaseCommand):
    help = 'Initialize demo data for pricing, risk scores, and bias detection'

    def handle(self, *args, **options):
        self.stdout.write("Initializing demo data...")

        # Get all bonds
        bonds = list(GreenBond.objects.all()[:300])
        self.stdout.write(f"Found {len(bonds)} bonds to process")

        # 1. Create Risk Scores
        self.stdout.write("Creating risk scores...")
        created_scores = 0
        for bond in bonds:
            _, created = PCRScore.objects.get_or_create(
                bond=bond,
                defaults={
                    'pcrs': round(random.uniform(30, 85), 2),
                    'flood_risk': round(random.uniform(0, 100), 2),
                    'heat_stress': round(random.uniform(0, 100), 2),
                    'drought_spei': round(random.uniform(-3, 3), 2),
                    'model_version': 'v1.0',
                    'scored_at': timezone.now()
                }
            )
            if created:
                created_scores += 1
        
        self.stdout.write(f"✓ Created {created_scores} risk scores")

        # 2. Create Pricing Data
        self.stdout.write("Creating pricing data...")
        created_pricing = 0
        for bond in bonds:
            actual = round(random.uniform(50, 300), 2)
            predicted = round(random.uniform(50, 300), 2)
            gap = round(actual - predicted, 2)
            
            _, created = PricingGap.objects.get_or_create(
                bond=bond,
                defaults={
                    'actual_spread_bps': actual,
                    'predicted_spread_bps': predicted,
                    'gap_bps': gap,
                    'is_mispriced': abs(gap) > 10,
                    'confidence_score': round(random.uniform(0.6, 0.95), 2),
                    'calculation_date': timezone.now(),
                    'is_live': True
                }
            )
            if created:
                created_pricing += 1
        
        self.stdout.write(f"✓ Created {created_pricing} pricing records")

        # 3. Create Bias Detection Data
        self.stdout.write("Creating bias detection data...")
        regions = ['Europe', 'Asia', 'North America', 'South America', 'Africa']
        created_bias = 0
        
        for region in regions:
            _, created = BiasDetectionResult.objects.get_or_create(
                region=region,
                defaults={
                    'mean_shap_variance': round(random.uniform(0.1, 0.5), 3),
                    'mean_pcrs': round(random.uniform(40, 70), 2),
                    'bias_severity': random.choice(['low', 'medium', 'high']),
                    'status': 'active',
                    'detected_at': timezone.now()
                }
            )
            if created:
                created_bias += 1
        
        self.stdout.write(f"✓ Created {created_bias} bias detection results")

        # Summary
        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Initialization complete!\n"
            f"  - Risk scores: {created_scores}\n"
            f"  - Pricing records: {created_pricing}\n"
            f"  - Bias results: {created_bias}"
        ))
