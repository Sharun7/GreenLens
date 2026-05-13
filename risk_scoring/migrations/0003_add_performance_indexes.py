# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Migration: Add performance indexes for PCRS queries at scale.

Optimizes for:
- Score range filtering
- Bond + score composite queries
- Model version filtering
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('risk_scoring', '0002_modelfeedback'),
    ]

    operations = [
        # Composite index for score range + bond queries
        migrations.AddIndex(
            model_name='pcrscore',
            index=models.Index(
                fields=['score', 'bond'],
                name='idx_pcr_score_bond',
            ),
        ),
        
        # Index for score-only queries (distribution, filtering)
        migrations.AddIndex(
            model_name='pcrscore',
            index=models.Index(
                fields=['score'],
                name='idx_pcr_score_only',
            ),
        ),
    ]
