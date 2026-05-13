# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_scoring/models.py — PCRScore model (Physical Climate Risk Score).
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

from data_ingestion.models import GreenBond


def _humanize_feature_name(feature_name: str) -> str:
    """Return a UI-friendly name for model feature keys."""
    labels = {
        "flood_risk_index": "Flood exposure",
        "heat_stress_index": "Heat stress",
        "drought_spei": "Drought severity",
        "drought_severity": "Drought severity",
        "composite_hazard": "Composite hazard",
        "maturity_exposure": "Maturity exposure",
        "bond_maturity_years": "Years to maturity",
        "project_category": "Project category",
    }
    return labels.get(feature_name, feature_name.replace("_", " ").title())


class PCRScore(models.Model):
    """
    Physical Climate Risk Score for a green bond.

    Score range: 0 (no risk) → 100 (maximum risk).
    Contributions are SHAP values indicating each hazard's share.
    """

    bond = models.ForeignKey(
        GreenBond,
        on_delete=models.CASCADE,
        related_name="pcr_scores",
        db_index=True,
    )

    # Composite score
    score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Overall Physical Climate Risk Score (0–100)",
    )

    # SHAP feature contributions (can be negative — offsetting risk)
    flood_contribution = models.FloatField(
        help_text="SHAP contribution of flood risk index to the total score",
    )
    heat_contribution = models.FloatField(
        help_text="SHAP contribution of heat stress index to the total score",
    )
    drought_contribution = models.FloatField(
        help_text="SHAP contribution of drought SPEI to the total score",
    )

    # Provenance
    model_version = models.CharField(
        max_length=30,
        db_index=True,
        help_text="Semantic version of the XGBoost model used (e.g. v1.2.0)",
    )
    scored_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Optional: full SHAP explanation payload for explainability UI
    shap_values = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full SHAP values dict for all features",
    )

    class Meta:
        ordering = ["-scored_at"]
        indexes = [
            models.Index(fields=["bond", "scored_at"]),
            models.Index(fields=["model_version"]),
            models.Index(fields=["score"]),
        ]
        verbose_name = "PCR Score"
        verbose_name_plural = "PCR Scores"

    def __str__(self):
        return f"PCRScore({self.bond.bond_id}) score={self.score:.1f} [{self.model_version}]"

    @property
    def risk_band(self) -> str:
        """Human-readable risk band based on score."""
        if self.score < 20:
            return "Low"
        if self.score < 45:
            return "Medium-Low"
        if self.score < 65:
            return "Medium-High"
        if self.score < 85:
            return "High"
        return "Extreme"

    @property
    def three_band_slug(self) -> str:
        """Simple UX band used in fund-manager-facing screens."""
        if self.score <= 33:
            return "low"
        if self.score <= 66:
            return "medium"
        return "high"

    @property
    def three_band_label(self) -> str:
        """Plain-English 0-33 / 34-66 / 67-100 risk label."""
        if self.three_band_slug == "low":
            return "Low Risk"
        if self.three_band_slug == "medium":
            return "Medium Risk"
        return "High Risk - Caution"

    @property
    def confidence_margin(self) -> float:
        """
        PCRS uncertainty margin driven by location precision.

        Exact coordinates produce a narrow interval; city/country fallbacks widen
        the range so the UI avoids false precision.
        """
        location_confidence = getattr(self.bond, "location_confidence", "country")
        margins = {
            GreenBond.LocationConfidence.PRECISE: 3.0,
            GreenBond.LocationConfidence.CITY: 8.0,
            GreenBond.LocationConfidence.COUNTRY: 15.0,
        }
        return margins.get(location_confidence, 12.0)

    @property
    def confidence_lower(self) -> float:
        return max(0.0, round(self.score - self.confidence_margin, 2))

    @property
    def confidence_upper(self) -> float:
        return min(100.0, round(self.score + self.confidence_margin, 2))

    @property
    def confidence_interval(self) -> dict:
        return {
            "lower": self.confidence_lower,
            "upper": self.confidence_upper,
            "margin": self.confidence_margin,
            "basis": getattr(self.bond, "location_confidence", "country"),
        }

    @property
    def main_risk_driver(self) -> dict:
        """Top feature contribution for a simple explanation above SHAP charts."""
        shap_values = self.shap_values or {}
        if isinstance(shap_values, dict) and shap_values:
            feature_name, contribution = max(
                shap_values.items(),
                key=lambda item: abs(float(item[1] or 0.0)),
            )
            contribution = float(contribution or 0.0)
            return {
                "feature": feature_name,
                "label": _humanize_feature_name(feature_name),
                "contribution": round(contribution, 4),
                "direction": "adds risk" if contribution >= 0 else "reduces risk",
            }

        drivers = [
            ("flood_risk_index", self.flood_contribution),
            ("heat_stress_index", self.heat_contribution),
            ("drought_severity", self.drought_contribution),
        ]
        feature_name, contribution = max(drivers, key=lambda item: abs(float(item[1] or 0.0)))
        contribution = float(contribution or 0.0)
        return {
            "feature": feature_name,
            "label": _humanize_feature_name(feature_name),
            "contribution": round(contribution, 4),
            "direction": "adds risk" if contribution >= 0 else "reduces risk",
        }

    @property
    def risk_summary_sentence(self) -> str:
        driver = self.main_risk_driver
        return (
            f"{self.three_band_label}. Main driver: {driver['label']} "
            f"{driver['direction']} by {abs(driver['contribution']):.2f} points."
        )


class ModelFeedback(models.Model):
    """
    Outcome feedback from investment decisions.

    This gives GreenLens a closed loop: record the decision, later record the
    realized outcome/loss, and use adverse cases for model review or retraining.
    """

    class Decision(models.TextChoices):
        AVOID = "avoid", "Avoid"
        BUY = "buy", "Buy"
        HOLD = "hold", "Hold"
        WATCHLIST = "watchlist", "Watchlist"
        SELL = "sell", "Sell"

    class Outcome(models.TextChoices):
        PENDING = "pending", "Pending outcome"
        NO_LOSS = "no_loss", "No loss observed"
        LOSS = "loss", "Loss observed"
        DEFAULT = "default", "Default / distress"
        PRICE_RECOVERY = "price_recovery", "Price recovery"
        MODEL_ERROR = "model_error", "Model review needed"

    bond = models.ForeignKey(
        GreenBond,
        on_delete=models.CASCADE,
        related_name="model_feedback",
        db_index=True,
    )
    pcr_score = models.ForeignKey(
        PCRScore,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_events",
    )

    decision = models.CharField(
        max_length=20,
        choices=Decision.choices,
        default=Decision.WATCHLIST,
        db_index=True,
    )
    outcome = models.CharField(
        max_length=30,
        choices=Outcome.choices,
        default=Outcome.PENDING,
        db_index=True,
    )

    pcr_score_at_decision = models.FloatField(null=True, blank=True)
    pricing_gap_bps_at_decision = models.FloatField(null=True, blank=True)
    location_confidence_at_decision = models.CharField(max_length=20, blank=True)
    realized_loss_bps = models.FloatField(
        null=True,
        blank=True,
        help_text="Observed loss or underperformance in basis points, if known.",
    )
    outcome_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    used_for_retraining = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["bond", "created_at"], name="risk_scorin_bond_id_74615a_idx"),
            models.Index(fields=["outcome", "used_for_retraining"], name="risk_scorin_outcome_0f1ad1_idx"),
        ]
        verbose_name = "Model Feedback"
        verbose_name_plural = "Model Feedback"

    def __str__(self):
        return f"Feedback({self.bond.bond_id}) decision={self.decision} outcome={self.outcome}"

    def save(self, *args, **kwargs):
        if self.pcr_score is None:
            self.pcr_score = self.bond.pcr_scores.order_by("-scored_at").first()
        if self.pcr_score_at_decision is None and self.pcr_score is not None:
            self.pcr_score_at_decision = round(float(self.pcr_score.score), 2)
        if not self.location_confidence_at_decision:
            self.location_confidence_at_decision = self.bond.location_confidence
        if self.pricing_gap_bps_at_decision is None:
            latest_gap = self.bond.pricing_gaps.order_by("-checked_at").first()
            if latest_gap is not None:
                self.pricing_gap_bps_at_decision = round(float(latest_gap.gap_bps), 2)
        super().save(*args, **kwargs)

    @property
    def is_adverse_outcome(self) -> bool:
        if self.outcome in {self.Outcome.LOSS, self.Outcome.DEFAULT, self.Outcome.MODEL_ERROR}:
            return True
        return bool(self.realized_loss_bps and self.realized_loss_bps > 0)

    @property
    def review_priority(self) -> str:
        if self.outcome == self.Outcome.DEFAULT:
            return "high"
        if self.is_adverse_outcome:
            return "medium"
        return "normal"
