"""
pricing_analysis/models.py — PricingGap model.
"""
from django.db import models

from data_ingestion.models import GreenBond


class PricingGap(models.Model):
    """
    Measures the mispricing signal between a bond's actual yield spread
    and the spread predicted by the PCRS model.

    gap_bps = actual_spread_bps - predicted_spread_bps
    Positive gap  → bond is under-priced for its climate risk (investor undercompensated).
    Negative gap  → bond is over-priced relative to its climate risk.
    """

    bond = models.ForeignKey(
        GreenBond,
        on_delete=models.CASCADE,
        related_name="pricing_gaps",
        db_index=True,
    )

    # Spread data (basis points)
    actual_spread_bps = models.FloatField(
        help_text="Observed yield spread over benchmark (basis points)",
    )
    predicted_spread_bps = models.FloatField(
        help_text="PCRS-model-implied fair-value spread (basis points)",
    )
    gap_bps = models.FloatField(
        help_text="Mispricing gap: actual minus predicted (basis points)",
    )

    # Signal
    is_mispriced = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when |gap_bps| exceeds the materiality threshold (±20 bps)",
    )
    is_live = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when spread was fetched from a live market data source; False = synthetic estimate",
    )

    # Provenance
    calculation_date = models.DateField(
        null=True, blank=True,
        db_index=True,
        help_text="Date on which spread data was calculated or fetched",
    )
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    data_source = models.CharField(
        max_length=50,
        default="yahoo_finance",
        help_text="Source of the actual spread data",
    )

    class Meta:
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["bond", "checked_at"]),
            models.Index(fields=["is_mispriced"]),
            models.Index(fields=["gap_bps"]),
        ]
        verbose_name = "Pricing Gap"
        verbose_name_plural = "Pricing Gaps"

    def __str__(self):
        direction = "under" if self.gap_bps > 0 else "over"
        return (
            f"PricingGap({self.bond.bond_id}) "
            f"gap={self.gap_bps:+.1f}bps [{direction}-priced]"
        )

    def save(self, *args, **kwargs):
        # Auto-compute gap and mispricing flag before saving
        self.gap_bps = self.actual_spread_bps - self.predicted_spread_bps
        self.is_mispriced = abs(self.gap_bps) >= 48.0
        super().save(*args, **kwargs)
