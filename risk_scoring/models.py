"""
risk_scoring/models.py — PCRScore model (Physical Climate Risk Score).
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

from data_ingestion.models import GreenBond


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
