# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
data_ingestion/models.py — GreenBond and ClimateHazardData models.
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class PilotProject(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Source mapped; analyst review pending"
        APPROVED = "approved", "Boundary reviewed"
        REJECTED = "rejected", "Rejected"

    source_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    country = models.CharField(max_length=100)
    region = models.CharField(max_length=100)
    category = models.CharField(max_length=30, default="solar")
    boundary = models.JSONField()
    boundary_sha256 = models.CharField(max_length=64)
    source_url = models.URLField(max_length=1000)
    source_version = models.CharField(max_length=100)
    source_metadata = models.JSONField(default=dict)
    review_status = models.CharField(max_length=12, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    reviewed_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["source_id"]

    def clean(self):
        from django.core.exceptions import ValidationError
        from .pilot import boundary_hash

        if self.boundary_sha256 != boundary_hash(self.boundary):
            raise ValidationError("The recorded boundary checksum does not match the polygon.")
        if self.review_status == self.ReviewStatus.APPROVED and not (self.reviewed_by_id and self.reviewed_at and self.review_notes.strip()):
            raise ValidationError("Boundary approval requires a reviewer, timestamp, and review notes.")

    def __str__(self):
        return f"{self.source_id}: {self.name}"


class PilotOutcome(models.Model):
    project = models.ForeignKey(PilotProject, on_delete=models.PROTECT, related_name="outcomes")
    feature_date = models.DateField()
    outcome_date = models.DateField()
    label_available_on = models.DateField()
    damage_fraction = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    label_source_url = models.URLField(max_length=1000)
    label_method = models.CharField(max_length=255)
    independently_observed = models.BooleanField(default=False)
    features = models.JSONField(default=dict)
    feature_provenance = models.JSONField(default=dict)
    reviewed_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["outcome_date", "pk"]
        constraints = [models.UniqueConstraint(fields=["project", "outcome_date"], name="unique_pilot_project_outcome")]

    def clean(self):
        from django.core.exceptions import ValidationError
        import math

        if self.damage_fraction is not None and (not math.isfinite(self.damage_fraction) or not 0 <= self.damage_fraction <= 1):
            raise ValidationError("Observed damage must be a finite fraction between zero and one.")
        if all((self.feature_date, self.outcome_date, self.label_available_on)) and not self.feature_date < self.outcome_date <= self.label_available_on:
            raise ValidationError("Features must precede the outcome, and labels cannot be available before the outcome.")
        if self.independently_observed and not (self.reviewed_by_id and self.reviewed_at and self.notes.strip()):
            raise ValidationError("Independent labels require a reviewer, review timestamp, and evidence notes.")
        if self.independently_observed:
            from risk_scoring.pilot_evaluation import outcome_row, validate_rows

            try:
                validate_rows([outcome_row(self)])
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise ValidationError(f"Independent-label gate: {exc}") from exc


class PilotIngestionRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=20, default="running")
    source_url = models.URLField(max_length=1000)
    source_sha256 = models.CharField(max_length=64, blank=True)
    result = models.JSONField(default=dict)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]


class PilotEvidence(models.Model):
    project = models.ForeignKey(PilotProject, on_delete=models.PROTECT, related_name="evidence_runs")
    boundary_sha256 = models.CharField(max_length=64)
    windows = models.JSONField()
    status = models.CharField(max_length=20)
    optical = models.JSONField(default=dict)
    sar = models.JSONField(default=dict)
    recipe_version = models.CharField(max_length=50, default="s1-s2-polygon-v1")
    collected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-collected_at", "-pk"]


class GreenBond(models.Model):
    """Represents a single green bond and its financed project."""

    class ProjectCategory(models.TextChoices):
        SOLAR = "solar", "Solar Energy"
        WIND = "wind", "Wind Energy"
        WATER = "water", "Water & Sanitation"
        TRANSPORT = "transport", "Clean Transport"
        BUILDING = "building", "Green Building"
        REFORESTATION = "reforestation", "Reforestation"
        OTHER = "other", "Other"

    class Currency(models.TextChoices):
        USD = "USD", "US Dollar"
        EUR = "EUR", "Euro"
        GBP = "GBP", "British Pound"
        JPY = "JPY", "Japanese Yen"
        CNY = "CNY", "Chinese Yuan"
        OTHER = "OTHER", "Other"

    # Identification
    bond_id = models.CharField(max_length=100, unique=True, db_index=True)
    issuer_name = models.CharField(max_length=255, db_index=True)
    country = models.CharField(max_length=100, db_index=True)

    # Project details
    project_category = models.CharField(
        max_length=20,
        choices=ProjectCategory.choices,
        default=ProjectCategory.OTHER,
        db_index=True,
    )
    project_description = models.TextField(blank=True)

    # Financial
    bond_maturity_years = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    issuance_date = models.DateField(db_index=True)
    currency = models.CharField(
        max_length=10, choices=Currency.choices, default=Currency.USD
    )
    amount_millions = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Bond amount in millions of the specified currency",
    )

    # Geolocation of financed project
    lat = models.FloatField(
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)],
        help_text="Latitude of the project site",
    )
    lon = models.FloatField(
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)],
        help_text="Longitude of the project site",
    )

    class LocationConfidence(models.TextChoices):
        PRECISE   = "precise",  "Precise (GPS / address-level)"
        CITY      = "city",     "City-level geocoding"
        COUNTRY   = "country",  "Country centroid (fallback)"

    location_confidence = models.CharField(
        max_length=10,
        choices=LocationConfidence.choices,
        default=LocationConfidence.COUNTRY,
        help_text="Geocoding precision level for this bond's project coordinates",
    )

    # Regulatory Framework (Category 19 — Global vs India Context)
    class RegulatoryFramework(models.TextChoices):
        EU_GBS = "EU_GBS", "EU Green Bond Standard"
        SEBI = "SEBI", "SEBI Green Bond Framework"
        CBI = "CBI", "Climate Bonds Standard"
        ICMA = "ICMA", "ICMA Green Bond Principles"
        OTHER = "OTHER", "Other/Self-labeled"

    regulatory_framework = models.CharField(
        max_length=10,
        choices=RegulatoryFramework.choices,
        default=RegulatoryFramework.OTHER,
        help_text="Regulatory framework under which the bond is issued",
    )

    class DisclosureQuality(models.TextChoices):
        HIGH = "HIGH", "GPS + verified"
        MEDIUM = "MEDIUM", "City level + audited"
        LOW = "LOW", "State/country + self-reported"

    disclosure_quality = models.CharField(
        max_length=10,
        choices=DisclosureQuality.choices,
        default=DisclosureQuality.LOW,
        help_text="Quality level of location and verification disclosure",
    )

    # Data provenance
    data_source = models.CharField(
        max_length=50,
        default="CBI",
        help_text="Registry source: CBI, IMF, Refinitiv, etc.",
    )
    last_synced_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp of last data sync from the registry source",
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issuance_date"]
        indexes = [
            models.Index(fields=["country", "project_category"]),
            models.Index(fields=["issuance_date"]),
            models.Index(fields=["issuer_name"]),
        ]
        verbose_name = "Green Bond"
        verbose_name_plural = "Green Bonds"

    def __str__(self):
        return f"{self.bond_id} — {self.issuer_name} ({self.project_category})"


class ClimateHazardData(models.Model):
    """Satellite-derived climate hazard indices for a bond's project location."""

    class Source(models.TextChoices):
        NASA = "nasa", "NASA Earthdata"
        ESA = "esa", "ESA Copernicus"
        NOAA = "noaa", "NOAA"
        IPCC = "ipcc", "IPCC AR6"
        OTHER = "other", "Other"

    bond = models.ForeignKey(
        GreenBond,
        on_delete=models.CASCADE,
        related_name="hazard_data",
        db_index=True,
    )

    # Hazard indices (all normalised 0–1 unless noted)
    flood_risk_index = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Normalised flood risk index (0 = no risk, 1 = extreme risk)",
    )
    heat_stress_index = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Normalised heat stress index (0 = no stress, 1 = extreme stress)",
    )
    drought_spei = models.FloatField(
        help_text=(
            "Standardised Precipitation-Evapotranspiration Index. "
            "Negative = drought; positive = wet conditions."
        ),
    )

    # Extended risk dimensions (Category 3 — Carbon, Policy, Transition)
    carbon_intensity_score = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Country-level carbon intensity score (0=low, 1=high) — sourced from EDGAR CO2 data",
    )
    policy_risk_score = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Policy risk score (0=stable, 1=high risk) — World Bank Governance Indicators",
    )
    transition_risk_score = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Transition risk score (0=low, 1=high) — based on country NDC ambition and fossil fuel dependency",
    )

    # India-Specific Climate Risks (Category 19 — Global vs India Context)
    monsoon_risk_index = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="India monsoon risk score (0=no risk, 1=extreme risk) — IMD seasonal forecast + ENSO",
    )
    cyclone_risk_index = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="India cyclone risk score (0=no risk, 1=extreme risk) — IMD historical cyclone tracks",
    )
    heat_wave_risk_index = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="India heat wave risk using WBGT (0=low, 1=extreme) — IMD heat wave frequency",
    )

    # Provenance
    data_date = models.DateField(db_index=True, help_text="Date of the underlying satellite observation")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.NASA)
    raw_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw API response metadata for audit purposes",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_date"]
        indexes = [
            models.Index(fields=["bond", "data_date"]),
            models.Index(fields=["data_date"]),
        ]
        verbose_name = "Climate Hazard Data"
        verbose_name_plural = "Climate Hazard Data"

    def __str__(self):
        return (
            f"Hazard({self.bond.bond_id}) "
            f"flood={self.flood_risk_index:.2f} "
            f"heat={self.heat_stress_index:.2f} "
            f"SPEI={self.drought_spei:.2f} "
            f"@ {self.data_date}"
        )
