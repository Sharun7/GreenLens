# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
ai_features/models.py — AI prediction, alerts, and portfolio optimization models.

Implements:
- Climate predictions (LSTM-based PCRS trajectory)
- Automated alerts (climate events, greenwash, pricing, regulatory)
- Portfolio optimization recommendations
- Alert delivery tracking
"""
from django.db import models
from django.utils import timezone
from data_ingestion.models import GreenBond


class ClimateScenario(models.Model):
    """IPCC SSP climate scenarios for future predictions."""
    
    class ScenarioType(models.TextChoices):
        SSP1_1_9 = "ssp1_1_9", "SSP1-1.9 (Very Low Emissions)"
        SSP1_2_6 = "ssp1_2_6", "SSP1-2.6 (Low Emissions)"
        SSP2_4_5 = "ssp2_4_5", "SSP2-4.5 (Intermediate Emissions)"
        SSP3_7_0 = "ssp3_7_0", "SSP3-7.0 (High Emissions)"
        SSP5_8_5 = "ssp5_8_5", "SSP5-8.5 (Very High Emissions)"
    
    scenario_type = models.CharField(
        max_length=20,
        choices=ScenarioType.choices,
        unique=True,
        db_index=True,
    )
    description = models.TextField()
    warming_by_2050 = models.FloatField(help_text="Expected warming in °C by 2050")
    warming_by_2100 = models.FloatField(help_text="Expected warming in °C by 2100")
    
    class Meta:
        verbose_name = "Climate Scenario"
        verbose_name_plural = "Climate Scenarios"
    
    def __str__(self):
        return f"{self.get_scenario_type_display()}"


class PCRSPrediction(models.Model):
    """
    AI-predicted PCRS trajectory for a bond over time.
    
    Level 1: Bond-level prediction
    "This bond's PCRS will reach 78 by 2030 under SSP2-4.5 scenario"
    """
    
    bond = models.ForeignKey(
        GreenBond,
        on_delete=models.CASCADE,
        related_name="pcrs_predictions",
        db_index=True,
    )
    scenario = models.ForeignKey(
        ClimateScenario,
        on_delete=models.CASCADE,
        related_name="pcrs_predictions",
    )
    
    # Current state
    current_pcrs = models.FloatField()
    current_date = models.DateField()
    
    # Prediction
    predicted_pcrs = models.FloatField()
    prediction_date = models.DateField()
    confidence = models.FloatField(help_text="Confidence 0-100%")
    
    # Primary driver
    primary_driver = models.CharField(
        max_length=100,
        choices=[
            ("sea_level_rise", "Sea Level Rise"),
            ("temperature_increase", "Temperature Increase"),
            ("precipitation_change", "Precipitation Change"),
            ("extreme_weather", "Extreme Weather Frequency"),
        ],
    )
    driver_magnitude = models.FloatField(help_text="Expected change in driver (e.g., 0.3m sea level rise)")
    
    # Model metadata
    model_version = models.CharField(max_length=30, default="v1.0.0")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-prediction_date"]
        indexes = [
            models.Index(fields=["bond", "scenario"]),
            models.Index(fields=["prediction_date"]),
        ]
        verbose_name = "PCRS Prediction"
        verbose_name_plural = "PCRS Predictions"
    
    def __str__(self):
        return f"{self.bond.bond_id} — {self.predicted_pcrs:.1f} by {self.prediction_date}"


class AutomatedAlert(models.Model):
    """
    Automated alerts triggered by climate events, greenwash detection, pricing anomalies, etc.
    """
    
    class AlertType(models.TextChoices):
        CLIMATE_EVENT = "climate_event", "Climate Event Alert"
        GREENWASH_DETECTION = "greenwash", "Greenwash Detection Alert"
        PRICING_ANOMALY = "pricing", "Pricing Anomaly Alert"
        REGULATORY_CHANGE = "regulatory", "Regulatory Change Alert"
    
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
    
    # Alert details
    alert_type = models.CharField(
        max_length=20,
        choices=AlertType.choices,
        db_index=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    # Affected bonds
    affected_bonds = models.ManyToManyField(
        GreenBond,
        related_name="alerts",
        help_text="Bonds affected by this alert",
    )
    
    # Alert data
    alert_data = models.JSONField(
        default=dict,
        help_text="Structured alert data (event details, PCRS changes, etc.)",
    )
    
    # Delivery
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    delivery_method = models.CharField(
        max_length=50,
        choices=[
            ("email", "Email"),
            ("dashboard", "Dashboard"),
            ("sms", "SMS"),
            ("webhook", "Webhook"),
        ],
        default="email",
    )
    
    # Metadata
    triggered_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    response_time_minutes = models.IntegerField(null=True, blank=True)
    
    class Meta:
        ordering = ["-triggered_at"]
        indexes = [
            models.Index(fields=["alert_type", "status"]),
            models.Index(fields=["triggered_at"]),
        ]
        verbose_name = "Automated Alert"
        verbose_name_plural = "Automated Alerts"
    
    def __str__(self):
        return f"{self.get_alert_type_display()} — {self.title}"


class PortfolioOptimization(models.Model):
    """
    Portfolio optimization recommendations based on climate risk.
    """
    
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        GENERATED = "generated", "Generated"
        REVIEWED = "reviewed", "Reviewed"
        IMPLEMENTED = "implemented", "Implemented"
    
    # Portfolio
    portfolio_name = models.CharField(max_length=255)
    portfolio_description = models.TextField(blank=True)
    
    # Current state
    current_bonds = models.JSONField(
        default=list,
        help_text="List of current bond holdings with amounts",
    )
    current_pcrs = models.FloatField()
    current_return = models.FloatField(help_text="Expected return %")
    
    # Optimized state
    optimized_bonds = models.JSONField(
        default=list,
        help_text="List of optimized bond holdings with amounts",
    )
    optimized_pcrs = models.FloatField()
    optimized_return = models.FloatField(help_text="Expected return %")
    
    # Recommendations
    sell_recommendations = models.JSONField(
        default=list,
        help_text="Bonds to sell with reasons",
    )
    buy_recommendations = models.JSONField(
        default=list,
        help_text="Bonds to buy with reasons",
    )
    
    # Constraints
    min_return_target = models.FloatField()
    max_single_bond_allocation = models.FloatField(default=5.0)
    geographic_diversification_required = models.BooleanField(default=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    implemented_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]
        verbose_name = "Portfolio Optimization"
        verbose_name_plural = "Portfolio Optimizations"
    
    def __str__(self):
        return f"{self.portfolio_name} — PCRS {self.current_pcrs:.1f} → {self.optimized_pcrs:.1f}"
    
    @property
    def pcrs_improvement(self) -> float:
        """Calculate PCRS improvement percentage."""
        if self.current_pcrs == 0:
            return 0
        return ((self.current_pcrs - self.optimized_pcrs) / self.current_pcrs) * 100


class RegulatoryMonitor(models.Model):
    """
    Monitor regulatory changes and their impact on portfolio.
    """
    
    class RegulationType(models.TextChoices):
        EU_SFDR = "eu_sfdr", "EU SFDR"
        EU_TAXONOMY = "eu_taxonomy", "EU Taxonomy"
        SEBI_BRSR = "sebi_brsr", "SEBI BRSR"
        RBI_CLIMATE = "rbi_climate", "RBI Climate Risk"
        SEC_CLIMATE = "sec_climate", "SEC Climate Disclosure"
    
    # Regulation
    regulation_type = models.CharField(
        max_length=30,
        choices=RegulationType.choices,
        db_index=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    # Dates
    announcement_date = models.DateField()
    effective_date = models.DateField()
    
    # Impact
    impact_description = models.TextField()
    affected_bonds_count = models.IntegerField(null=True, blank=True)
    
    # Compliance
    compliance_required = models.BooleanField(default=True)
    action_required = models.TextField(blank=True)
    
    # Metadata
    source_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-effective_date"]
        indexes = [
            models.Index(fields=["regulation_type", "effective_date"]),
        ]
        verbose_name = "Regulatory Monitor"
        verbose_name_plural = "Regulatory Monitors"
    
    def __str__(self):
        return f"{self.get_regulation_type_display()} — {self.title}"
