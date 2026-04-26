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
      1. Try live spread via yfinance
      2. Fall back to synthetic spread if live data unavailable
      3. Use PCRScore as predicted spread proxy (or simple rating-based estimate)
      4. Save PricingGap record
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
            isin = bond.bond_id or ""
            # Determine maturity in years
            maturity_years = float(bond.bond_maturity_years or 7)
            currency = _detect_currency(bond.country)

            # --- Actual spread (Yahoo Finance risk-free rate + credit spread) ---
            actual_spread = None
            is_live = False

            actual_spread, is_live = fetcher.get_market_adjusted_spread(
                credit_rating="BBB",
                maturity_years=maturity_years,
                country=bond.country or "",
                currency=currency,
            )

            # --- Predicted spread (from latest PCRScore) ---
            predicted_spread = _predicted_spread_from_pcr(bond, maturity_years)

            # --- Persist ---
            fetcher.save_pricing_gap(
                bond=bond,
                actual_spread_bps=actual_spread,
                predicted_spread_bps=predicted_spread,
                is_live=is_live,
                source_note="yfinance" if is_live else "synthetic_table",
            )
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
    maturity_years = float(bond.bond_maturity_years or 7)
    currency = _detect_currency(bond.country)

    actual_spread = None
    is_live = False

    if bond.bond_id:
        actual_spread = fetcher.get_yield_spread(bond.bond_id, maturity_years, currency)
        if actual_spread is not None:
            is_live = True

    if actual_spread is None:
        actual_spread = fetcher.get_synthetic_spread("BBB", maturity_years, bond.country or "")

    predicted_spread = _predicted_spread_from_pcr(bond, maturity_years)
    fetcher.save_pricing_gap(
        bond=bond,
        actual_spread_bps=actual_spread,
        predicted_spread_bps=predicted_spread,
        is_live=is_live,
    )
    return f"Bond {bond_id}: gap = {actual_spread - predicted_spread:+.1f} bps"


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
    """
    Derive a model-implied spread from the bond's latest PCRScore.
    Linear approximation: higher climate risk → higher required spread.

    Mapping: PCRScore 0-100 → spread 40-350 bps (rough empirical range).
    Falls back to rating-based synthetic if no PCRScore exists.
    """
    from risk_scoring.models import PCRScore
    from pricing_analysis.pricing_fetcher import BondPricingFetcher, _maturity_bucket, SYNTHETIC_SPREADS

    latest_score = PCRScore.objects.filter(bond=bond).order_by("-scored_at").first()

    if latest_score and latest_score.score is not None:
        score = float(latest_score.score)     # 0-100
        # Linear interpolation: score 0 → 40 bps, score 100 → 350 bps
        predicted = 40.0 + (score / 100.0) * 310.0
        return round(predicted, 1)

    # No PCRScore — use synthetic table at BBB (median IG)
    bucket = _maturity_bucket(maturity_years)
    return float(SYNTHETIC_SPREADS["BBB"][bucket])
