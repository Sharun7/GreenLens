"""
Management command: batch_compute_pricing
Usage:
    python manage.py batch_compute_pricing
    python manage.py batch_compute_pricing --limit 200
    python manage.py batch_compute_pricing --only-missing
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger("greenlens.batch_compute_pricing")


class Command(BaseCommand):
    help = "Compute pricing gaps (actual vs predicted spread) for all bonds using Yahoo Finance live rates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of bonds to process (default: all).",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            default=False,
            help="Skip bonds that already have a PricingGap record.",
        )

    def handle(self, *args, **options):
        from data_ingestion.models import GreenBond
        from pricing_analysis.models import PricingGap
        from pricing_analysis.pricing_fetcher import BondPricingFetcher
        from pricing_analysis.tasks import _detect_currency, _predicted_spread_from_pcr

        fetcher = BondPricingFetcher()

        # Pre-fetch all risk-free rates once (cached per currency for the run)
        self.stdout.write("Fetching live risk-free rates from Yahoo Finance...")
        for currency in ["USD", "EUR", "GBP", "JPY"]:
            rf = fetcher.get_live_rf_rate(currency)
            if rf is not None:
                self.stdout.write(self.style.SUCCESS(f"  {currency}: {rf:.3f}% (Yahoo Finance live)"))
            else:
                from pricing_analysis.pricing_fetcher import RF_BASELINES
                baseline = RF_BASELINES.get(currency, 4.5)
                self.stdout.write(f"  {currency}: {baseline:.2f}% (baseline fallback)")

        qs = GreenBond.objects.all().order_by("pk")

        if options["only_missing"]:
            gapped_pks = set(PricingGap.objects.values_list("bond_id", flat=True))
            qs = qs.exclude(pk__in=gapped_pks)
            self.stdout.write(f"Skipping {len(gapped_pks)} bonds that already have a gap record.")

        if options["limit"]:
            qs = qs[: options["limit"]]

        total = qs.count()
        self.stdout.write(f"Computing pricing gaps for {total} bonds ...")

        ok = errors = live = synthetic = 0

        for i, bond in enumerate(qs.iterator(chunk_size=100), start=1):
            try:
                maturity_years = float(bond.bond_maturity_years or 7)
                currency = _detect_currency(bond.country)

                # Use market-adjusted spread: Yahoo Finance live rates + credit table
                actual_spread, is_live_data = fetcher.get_market_adjusted_spread(
                    credit_rating="BBB",
                    maturity_years=maturity_years,
                    country=bond.country or "",
                    currency=currency,
                )
                if is_live_data:
                    live += 1
                else:
                    synthetic += 1

                predicted_spread = _predicted_spread_from_pcr(bond, maturity_years)

                fetcher.save_pricing_gap(
                    bond=bond,
                    actual_spread_bps=actual_spread,
                    predicted_spread_bps=predicted_spread,
                    is_live=is_live_data,
                    source_note="yahoo_finance_rf" if is_live_data else "synthetic_table",
                )
                ok += 1

            except Exception as exc:
                errors += 1
                logger.error("bond pk=%s failed: %s", bond.pk, exc)

            if i % 100 == 0 or i == total:
                self.stdout.write(f"  {i}/{total}  ok={ok}  live={live}  synthetic={synthetic}  errors={errors}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {ok} gaps saved ({live} with Yahoo Finance rates, {synthetic} synthetic), {errors} errors."
        ))
