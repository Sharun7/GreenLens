# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
pricing_analysis/tasks.py — Celery tasks for bond pricing data refresh.
"""
import logging

from celery import shared_task

logger = logging.getLogger("greenlens.pricing_tasks")


@shared_task(
    name="pricing_analysis.refresh_pricing_data",
    bind=True,
    max_retries=3,
    default_retry_delay=300,   # 5 min retry
    soft_time_limit=3600,      # 1-hour hard limit
)
def refresh_pricing_data(self):
    """
    Scheduled task: refresh yield spread data for every active GreenBond.

    Run schedule: every 24 hours (configured via django-celery-beat).
    For each bond:
    1. Estimate a spread from rating tables and an available benchmark rate
    2. Predict a reference spread using the fitted pricing regression
    3. Save the gap with explicit estimated-data provenance
    """
    from data_ingestion.models import GreenBond
    from risk_scoring.models import PCRScore
    from pricing_analysis.pricing_fetcher import BondPricingFetcher

    fetcher = BondPricingFetcher()
    bonds = GreenBond.objects.all().select_related()

    total = bonds.count()
    logger.info("refresh_pricing_data: processing %d bonds", total)

    success, skipped, errors = 0, 0, 0

    for bond in bonds:
        try:
            refresh_bond_pricing(bond, fetcher)
            success += 1

        except Exception as exc:
            errors += 1
            logger.error("Error processing bond %s: %s", bond.id, exc, exc_info=True)

    summary = f"refresh_pricing_data complete: {success} ok, {skipped} skipped, {errors} errors"
    logger.info(summary)
    return summary


@shared_task(
    name="pricing_analysis.refresh_single_bond",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def refresh_single_bond(self, bond_id: int):
    """
    On-demand pricing refresh for a single bond (triggered by API or admin action).
    """
    from data_ingestion.models import GreenBond
    from pricing_analysis.pricing_fetcher import BondPricingFetcher

    try:
        bond = GreenBond.objects.get(pk=bond_id)
    except GreenBond.DoesNotExist:
        logger.error("refresh_single_bond: bond %d not found", bond_id)
        return

    fetcher = BondPricingFetcher()
    gap = refresh_bond_pricing(bond, fetcher)
    return f"Bond {bond_id}: estimated gap = {gap.gap_bps:+.1f} bps"


def refresh_bond_pricing(bond, fetcher):
    """Persist a spread estimate versus trained regression, not a market trade."""
    maturity_years = float(bond.bond_maturity_years or 7)
    predicted_spread = _predicted_spread_from_pcr(bond, maturity_years)
    actual_spread, benchmark_available = fetcher.get_market_adjusted_spread(
        credit_rating="BBB", maturity_years=maturity_years,
        country=bond.country or "",
        currency=(bond.currency or _detect_currency(bond.country)).upper(),
    )
    return fetcher.save_pricing_gap(
        bond=bond,
        actual_spread_bps=actual_spread,
        predicted_spread_bps=predicted_spread,
        is_live=False,
        source_note="market_adjusted_estimate" if benchmark_available else "synthetic_table",
    )


# ── Helper functions ──────────────────────────────────────────────────────────

def _detect_currency(country: str) -> str:
    """Rough currency detection from issuer country."""
    eur_countries = {
        "germany", "france", "italy", "spain", "netherlands", "belgium",
        "austria", "portugal", "finland", "ireland", "luxembourg", "greece",
        "eurozone", "eu", "european union", "sweden", "denmark", "norway",
    }
    if (country or "").lower() in eur_countries:
        return "EUR"
    return "USD"


def _predicted_spread_from_pcr(bond, maturity_years: float) -> float:
    """Use the fitted pricing model; missing prerequisites must not become fake predictions."""
    from risk_scoring.models import PCRScore
    from pricing_analysis.analyser import PricingGapAnalyser

    latest_score = PCRScore.objects.filter(bond=bond).order_by("-scored_at").first()

    if latest_score and latest_score.score is not None:
        analyser = PricingGapAnalyser()
        predicted = analyser.predict_spread(float(latest_score.score), maturity_years)
        return round(max(0.0, predicted), 1)
    raise ValueError(f"Bond {bond.bond_id} has no PCRScore. Score it before running pricing analysis.")
