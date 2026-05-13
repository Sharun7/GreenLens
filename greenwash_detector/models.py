# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
greenwash_detector/models.py — GreenwashFlag model.
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

from data_ingestion.models import GreenBond


class GreenwashFlag(models.Model):
    """
    Satellite-based greenwashing detection result for a bond's project site.

    Compares the issuer's claimed project type against independently
    observed satellite land-use and NDVI change data.
    """

    bond = models.ForeignKey(
        GreenBond,
        on_delete=models.CASCADE,
        related_name="greenwash_flags",
        db_index=True,
    )

    VERIFICATION_CHOICES = [
        ('verifiable', 'Verifiable'),
        ('unverifiable', 'Unverifiable'),
    ]
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_CHOICES,
        default='verifiable',
        help_text="Whether satellite data is available for this bond's timeline",
    )

    # Satellite-derived signals
    ndvi_change = models.FloatField(
        help_text=(
            "Change in Normalised Difference Vegetation Index between "
            "pre- and post-project satellite imagery. "
            "Positive = greening; negative = vegetation loss."
        ),
    )
    satellite_land_use = models.CharField(
        max_length=100,
        help_text="Land-use class inferred from satellite imagery (e.g. 'bare_soil', 'forest')",
    )
    pre_project_image_date = models.DateField(
        null=True, blank=True,
        help_text="Acquisition date of the baseline satellite image",
    )
    post_project_image_date = models.DateField(
        null=True, blank=True,
        help_text="Acquisition date of the comparison satellite image",
    )

    # Claimed vs observed
    claimed_project_type = models.CharField(
        max_length=100,
        help_text="Project type as self-reported by the bond issuer",
    )
    is_inconsistent = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when satellite evidence is inconsistent with the claimed project type",
    )
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Model confidence in the inconsistency classification (0–1)",
    )

    # Provenance
    model_version = models.CharField(
        max_length=30,
        default="v1.0.0",
        help_text="Version of the CNN classifier used",
    )
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    raw_ee_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw Google Earth Engine API response for audit trail",
    )

    class Meta:
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["bond", "checked_at"]),
            models.Index(fields=["is_inconsistent"]),
            models.Index(fields=["confidence"]),
        ]
        verbose_name = "Greenwash Flag"
        verbose_name_plural = "Greenwash Flags"

    def __str__(self):
        status = "⚠ FLAGGED" if self.is_inconsistent else "✓ OK"
        return (
            f"GreenwashFlag({self.bond.bond_id}) "
            f"{status} claimed={self.claimed_project_type} "
            f"observed={self.satellite_land_use} "
            f"conf={self.confidence:.0%}"
        )
