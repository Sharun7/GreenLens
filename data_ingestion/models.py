"""
data_ingestion/models.py — GreenBond and ClimateHazardData models.
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


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
