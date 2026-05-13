# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Migration: Add PostGIS spatial indexes for scaling to 1 lakh bonds.

This migration adds:
1. Composite index for country + project_category filtering
2. Composite index for score-based queries
3. Spatial index preparation (when PostGIS enabled)
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data_ingestion', '0004_add_extended_risk_scores'),
    ]

    operations = [
        # Composite index for common filter combinations
        migrations.AddIndex(
            model_name='greenbond',
            index=models.Index(
                fields=['country', 'project_category', 'issuance_date'],
                name='idx_bond_filter_combo',
            ),
        ),
        
        # Index for amount-based queries (portfolio analysis)
        migrations.AddIndex(
            model_name='greenbond',
            index=models.Index(
                fields=['amount_millions'],
                name='idx_bond_amount',
            ),
        ),
        
        # Index for location confidence filtering
        migrations.AddIndex(
            model_name='greenbond',
            index=models.Index(
                fields=['location_confidence'],
                name='idx_location_conf',
            ),
        ),
        
        # Composite index for lat/lon bounding box queries
        migrations.AddIndex(
            model_name='greenbond',
            index=models.Index(
                fields=['lat', 'lon'],
                name='idx_bond_latlon',
            ),
        ),
    ]
