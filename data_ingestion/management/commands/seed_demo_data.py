"""
data_ingestion/management/commands/seed_demo_data.py

Populates the database with 50 realistic synthetic green bonds and
scoring data so the GreenLens dashboard renders immediately without
needing external CSV files, NASA API keys, or Google Earth Engine access.

Usage:
    python manage.py seed_demo_data
    python manage.py seed_demo_data --clear   # wipe and re-seed
"""
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from data_ingestion.models import GreenBond, ClimateHazardData
from risk_scoring.models import PCRScore
from pricing_analysis.models import PricingGap
from greenwash_detector.models import GreenwashFlag

# ── Synthetic bond catalogue ──────────────────────────────────────────────────

BONDS_CATALOGUE = [
    # (bond_id, issuer_name, country, category, lat, lon, amount_m, currency, year, maturity)
    ("DE_SOLAR_2021", "KfW Bankengruppe", "Germany", "solar", 51.16, 10.45, 1500, "EUR", 2021, 10),
    ("FR_WIND_2020", "Caisse des Dépôts", "France", "wind", 46.23, 2.21, 2000, "EUR", 2020, 15),
    ("US_SOLAR_2022", "Apple Green Bond LLC", "United States", "solar", 37.09, -95.71, 1750, "USD", 2022, 7),
    ("CN_SOLAR_2021", "Industrial Bank Co.", "China", "solar", 35.86, 104.19, 3000, "CNY", 2021, 5),
    ("IN_WIND_2022", "Adani Green Energy", "India", "wind", 20.59, 78.96, 500, "USD", 2022, 10),
    ("BR_REFO_2020", "BNDES", "Brazil", "reforestation", -14.24, -51.93, 800, "USD", 2020, 12),
    ("AU_SOLAR_2021", "Clean Energy Finance Corp", "Australia", "solar", -25.27, 133.77, 600, "USD", 2021, 8),
    ("JP_TRAN_2022", "East Japan Railway", "Japan", "transport", 36.20, 138.25, 2500, "JPY", 2022, 10),
    ("GB_WIND_2021", "UK Infrastructure Bank", "United Kingdom", "wind", 55.38, -3.44, 1200, "GBP", 2021, 20),
    ("CA_BLDG_2020", "Province of Ontario", "Canada", "building", 56.13, -106.35, 900, "USD", 2020, 15),
    ("ES_SOLAR_2022", "Iberdrola SA", "Spain", "solar", 40.46, -3.75, 1100, "EUR", 2022, 7),
    ("NL_WATER_2021", "Rijkswaterstaat", "Netherlands", "water", 52.13, 5.29, 700, "EUR", 2021, 12),
    ("SE_WIND_2020", "Vattenfall AB", "Sweden", "wind", 60.13, 18.64, 500, "EUR", 2020, 10),
    ("KR_TRAN_2022", "Korea Railroad Corp", "South Korea", "transport", 35.91, 127.77, 1000, "USD", 2022, 8),
    ("MX_SOLAR_2021", "Nacional Financiera", "Mexico", "solar", 23.63, -102.55, 400, "USD", 2021, 10),
    ("ZA_WIND_2020", "DBSA", "South Africa", "wind", -30.56, 22.94, 300, "USD", 2020, 12),
    ("EG_SOLAR_2022", "Egypt New Administrative Capital", "Egypt", "solar", 26.82, 30.80, 250, "USD", 2022, 7),
    ("ID_REFO_2021", "Indonesia Green Bond", "Indonesia", "reforestation", -0.79, 113.92, 350, "USD", 2021, 10),
    ("PL_WIND_2020", "PKN Orlen SA", "Poland", "wind", 51.92, 19.14, 600, "EUR", 2020, 8),
    ("IT_SOLAR_2022", "Enel Green Power", "Italy", "solar", 41.87, 12.57, 1800, "EUR", 2022, 12),
    ("NG_SOLAR_2021", "Access Bank PLC", "Nigeria", "solar", 9.08, 8.68, 150, "USD", 2021, 7),
    ("TR_WIND_2020", "Zorlu Enerji", "Turkey", "wind", 38.96, 35.24, 200, "USD", 2020, 10),
    ("AR_WIND_2021", "YPF SA", "Argentina", "wind", -38.42, -63.62, 120, "USD", 2021, 5),
    ("TH_SOLAR_2022", "Gulf Energy Development", "Thailand", "solar", 15.87, 100.99, 280, "USD", 2022, 8),
    ("MY_BLDG_2021", "Khazanah Nasional", "Malaysia", "building", 4.21, 101.98, 320, "USD", 2021, 10),
    ("VN_WIND_2020", "EVN Finance", "Vietnam", "wind", 14.06, 108.28, 180, "USD", 2020, 7),
    ("CL_SOLAR_2022", "Enel Américas", "Chile", "solar", -35.68, -71.54, 400, "USD", 2022, 10),
    ("CO_REFO_2021", "Banco de Bogotá", "Colombia", "reforestation", 4.57, -74.30, 200, "USD", 2021, 12),
    ("PE_WATER_2020", "Ministerio de Economía", "Peru", "water", -9.19, -75.02, 250, "USD", 2020, 15),
    ("PH_SOLAR_2022", "ACEN Corp", "Philippines", "solar", 12.88, 121.77, 220, "USD", 2022, 8),
    ("BD_BLDG_2021", "IDCOL", "Bangladesh", "building", 23.69, 90.36, 100, "USD", 2021, 7),
    ("PK_SOLAR_2020", "NTDC Pakistan", "Pakistan", "solar", 30.38, 69.35, 130, "USD", 2020, 10),
    ("UA_WIND_2021", "DTEK Renewables", "Ukraine", "wind", 48.38, 31.17, 150, "USD", 2021, 8),
    ("CZ_TRAN_2022", "Czech Railways", "Czech Republic", "transport", 49.82, 15.47, 500, "EUR", 2022, 12),
    ("NO_WIND_2021", "Statkraft AS", "Norway", "wind", 64.57, 17.89, 800, "EUR", 2021, 15),
    ("FI_WATER_2020", "City of Helsinki", "Finland", "water", 61.92, 25.75, 300, "EUR", 2020, 10),
    ("DK_WIND_2022", "Ørsted A/S", "Denmark", "wind", 56.26, 9.50, 1500, "EUR", 2022, 20),
    ("PT_SOLAR_2021", "EDP Renováveis", "Portugal", "solar", 39.40, -8.22, 700, "EUR", 2021, 10),
    ("GR_SOLAR_2020", "Public Power Corporation", "Greece", "solar", 39.07, 21.82, 400, "EUR", 2020, 8),
    ("RO_WIND_2022", "Enel Romania", "Romania", "wind", 45.94, 24.97, 350, "EUR", 2022, 10),
    ("HU_BLDG_2021", "Magyar Fejlesztési Bank", "Hungary", "building", 47.16, 19.50, 280, "EUR", 2021, 7),
    ("SK_TRAN_2020", "Slovak Railways", "Slovakia", "transport", 48.67, 19.70, 200, "EUR", 2020, 12),
    ("HR_SOLAR_2022", "HEP d.d.", "Croatia", "solar", 45.10, 15.20, 180, "EUR", 2022, 8),
    ("RS_WIND_2021", "EPS Serbia", "Serbia", "wind", 44.02, 21.00, 150, "EUR", 2021, 10),
    ("SI_WATER_2020", "DARS Slovenia", "Slovenia", "water", 46.15, 14.99, 120, "EUR", 2020, 12),
    ("BG_SOLAR_2022", "CEZ Bulgaria", "Bulgaria", "solar", 42.73, 25.49, 160, "EUR", 2022, 8),
    ("EE_WIND_2021", "Eesti Energia", "Estonia", "wind", 58.60, 25.01, 200, "EUR", 2021, 10),
    ("LT_WIND_2020", "Ignitis Group", "Lithuania", "wind", 55.17, 23.88, 220, "EUR", 2020, 12),
    ("LV_WATER_2022", "Latvijas Valsts Meži", "Latvia", "water", 56.88, 24.60, 130, "EUR", 2022, 8),
    ("IS_WIND_2021", "Landsvirkjun", "Iceland", "wind", 64.96, -19.02, 90, "EUR", 2021, 15),
]

LAND_USE_TYPES = ["forest", "grassland", "cropland", "shrubland", "urban", "bare_soil", "wetland"]


class Command(BaseCommand):
    help = "Seed the database with 50 synthetic green bonds and scoring data for demo purposes"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear", action="store_true",
            help="Clear existing data before seeding (full re-seed)",
        )

    def handle(self, *args, **options):
        rng = random.Random(42)  # deterministic seed for reproducibility

        # Collect the exact bond IDs from this catalogue
        SYNTHETIC_IDS = [b[0] for b in BONDS_CATALOGUE]

        if options["clear"]:
            self.stdout.write("Clearing SYNTHETIC demo bonds only (real CBI data is preserved)...")
            # Only delete bonds that are part of this synthetic catalogue
            synthetic_bonds = GreenBond.objects.filter(bond_id__in=SYNTHETIC_IDS)
            synthetic_count = synthetic_bonds.count()
            # Cascade-delete associated scoring data for only these bonds
            bond_pks = list(synthetic_bonds.values_list('pk', flat=True))
            GreenwashFlag.objects.filter(bond_id__in=bond_pks).delete()
            PricingGap.objects.filter(bond_id__in=bond_pks).delete()
            PCRScore.objects.filter(bond_id__in=bond_pks).delete()
            ClimateHazardData.objects.filter(bond_id__in=bond_pks).delete()
            synthetic_bonds.delete()
            self.stdout.write(self.style.WARNING(
                f"Cleared {synthetic_count} synthetic bonds (real bonds untouched)."
            ))

        existing_count = GreenBond.objects.count()
        if existing_count > 0 and not options["clear"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Database already has {existing_count} bonds. "
                    "Use --clear to re-seed from scratch."
                )
            )
            return

        with transaction.atomic():
            self._seed_bonds(rng)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! Seeded {GreenBond.objects.count()} bonds, "
            f"{PCRScore.objects.count()} PCR scores, "
            f"{PricingGap.objects.count()} pricing gaps, "
            f"{GreenwashFlag.objects.count()} greenwash flags, "
            f"{ClimateHazardData.objects.count()} climate hazard records."
        ))

    def _seed_bonds(self, rng):
        self.stdout.write("Creating green bonds...")
        bonds_created = []

        for (
            bond_id, issuer_name, country, category,
            lat, lon, amount_m, currency, year, maturity
        ) in BONDS_CATALOGUE:
            issuance_date = date(year, rng.randint(1, 12), rng.randint(1, 28))

            bond, _ = GreenBond.objects.update_or_create(
                bond_id=bond_id,
                defaults=dict(
                    issuer_name=issuer_name,
                    country=country,
                    project_category=category,
                    project_description=(
                        f"{issuer_name} green bond financing {category.replace('_', ' ')} "
                        f"projects in {country}."
                    ),
                    bond_maturity_years=maturity,
                    issuance_date=issuance_date,
                    currency=currency if currency in ("USD", "EUR", "GBP", "JPY", "CNY") else "USD",
                    amount_millions=Decimal(str(amount_m)),
                    lat=lat + rng.uniform(-2, 2),
                    lon=lon + rng.uniform(-2, 2),
                ),
            )
            bonds_created.append(bond)

        self.stdout.write(f"  -> {len(bonds_created)} bonds created")

        # ── Module 1: Climate Hazard Data ─────────────────────────────────────
        self.stdout.write("Creating climate hazard records...")
        hazards = []
        for bond in bonds_created:
            for months_back in range(0, 36, 6):  # 6 monthly snapshots over 3 years
                obs_date = date.today() - timedelta(days=months_back * 30)
                # Higher-risk regions get higher hazard indices
                base_flood = abs(bond.lat) / 90 * 0.4 + rng.uniform(0, 0.4)
                base_heat  = max(0, (50 - abs(bond.lat)) / 50) * 0.5 + rng.uniform(0, 0.3)
                spei       = rng.uniform(-3.0, 1.5)
                hazards.append(ClimateHazardData(
                    bond=bond,
                    flood_risk_index=min(1.0, base_flood),
                    heat_stress_index=min(1.0, base_heat),
                    drought_spei=spei,
                    data_date=obs_date,
                    source="nasa",
                    raw_metadata={"source": "synthetic", "period": str(obs_date)},
                ))
        ClimateHazardData.objects.bulk_create(hazards, ignore_conflicts=True)
        self.stdout.write(f"  -> {len(hazards)} hazard records created")

        # ── Module 2: PCR Scores ──────────────────────────────────────────────
        self.stdout.write("Creating PCR scores...")
        pcr_scores = []
        risk_scored_bonds = {}
        for bond in bonds_created:
            latest_hazard = bond.hazard_data.order_by("-data_date").first()
            if latest_hazard:
                flood_c = latest_hazard.flood_risk_index * 30
                heat_c  = latest_hazard.heat_stress_index * 20
                drought_c = max(0, -latest_hazard.drought_spei) * 10
            else:
                flood_c = rng.uniform(0, 30)
                heat_c  = rng.uniform(0, 20)
                drought_c = rng.uniform(0, 10)

            noise = rng.uniform(-5, 5)
            raw_score = flood_c + heat_c + drought_c + noise
            score = max(1.0, min(99.0, raw_score))

            shap_vals = {
                "flood_risk_index":    round(flood_c / 100, 4),
                "heat_stress_index":   round(heat_c / 100, 4),
                "drought_spei":        round(-drought_c / 100, 4),
                "lat":                 round(bond.lat * 0.001, 4),
                "lon":                 round(bond.lon * 0.001, 4),
                "bond_maturity_years": round(bond.bond_maturity_years * 0.01, 4),
            }

            pcr = PCRScore(
                bond=bond,
                score=round(score, 2),
                flood_contribution=round(flood_c / 100, 4),
                heat_contribution=round(heat_c / 100, 4),
                drought_contribution=round(drought_c / 100, 4),
                model_version="v1.0.0",
                shap_values=shap_vals,
            )
            pcr_scores.append(pcr)
            risk_scored_bonds[bond.id] = score

        PCRScore.objects.bulk_create(pcr_scores, ignore_conflicts=True)
        self.stdout.write(f"  -> {len(pcr_scores)} PCR scores created")

        # ── Module 3: Pricing Gaps ────────────────────────────────────────────
        self.stdout.write("Creating pricing gap records...")
        pricing_gaps = []
        for bond in bonds_created:
            pcr_score = risk_scored_bonds.get(bond.id, 50)
            # Predicted spread based on risk score (higher risk -> higher spread)
            predicted_bps = 80 + (pcr_score * 2.5) + rng.uniform(-20, 20)
            # Actual market spread with some noise (some bonds are mispriced)
            mispricing_noise = rng.choice([
                rng.uniform(-60, -20),   # overpriced
                rng.uniform(-15, 15),    # fairly priced
                rng.uniform(20, 80),     # underpriced (climate risk not reflected)
            ])
            actual_bps = predicted_bps + mispricing_noise

            gap = PricingGap(
                bond=bond,
                actual_spread_bps=round(actual_bps, 2),
                predicted_spread_bps=round(predicted_bps, 2),
                gap_bps=round(actual_bps - predicted_bps, 2),
                is_mispriced=abs(actual_bps - predicted_bps) >= 20,
                is_live=False,
                calculation_date=date.today() - timedelta(days=rng.randint(0, 30)),
                data_source="synthetic",
            )
            pricing_gaps.append(gap)

        PricingGap.objects.bulk_create(pricing_gaps, ignore_conflicts=True)
        self.stdout.write(f"  -> {len(pricing_gaps)} pricing gaps created")

        # ── Module 4: Greenwash Flags ─────────────────────────────────────────
        self.stdout.write("Creating greenwash detection records...")
        flags = []
        for bond in bonds_created:
            # Reforestation and solar bonds are most likely to be checked
            is_likely_flag = (
                bond.project_category == "reforestation" and rng.random() < 0.35
            ) or rng.random() < 0.15

            # NDVI change: reforestation should show positive, actual depends on detection
            if bond.project_category == "reforestation":
                ndvi_change = rng.uniform(-0.15, 0.25) if not is_likely_flag else rng.uniform(-0.30, -0.05)
                claimed = "reforestation"
                observed = rng.choice(["forest", "cropland", "bare_soil"]) if is_likely_flag else "forest"
            elif bond.project_category == "solar":
                ndvi_change = rng.uniform(-0.20, 0.05)
                claimed = "solar_installation"
                observed = rng.choice(["grassland", "bare_soil", "urban"])
            else:
                ndvi_change = rng.uniform(-0.10, 0.10)
                claimed = bond.project_category
                observed = rng.choice(LAND_USE_TYPES)

            base_date = datetime.now(timezone.utc) - timedelta(days=rng.randint(30, 365))
            pre_date  = (base_date - timedelta(days=730)).date()
            post_date = base_date.date()

            flag = GreenwashFlag(
                bond=bond,
                ndvi_change=round(ndvi_change, 4),
                satellite_land_use=observed,
                pre_project_image_date=pre_date,
                post_project_image_date=post_date,
                claimed_project_type=claimed,
                is_inconsistent=is_likely_flag,
                confidence=round(rng.uniform(0.60, 0.97) if is_likely_flag else rng.uniform(0.70, 0.99), 3),
                model_version="v1.0.0",
                raw_ee_metadata={"source": "synthetic", "ndvi_method": "Sentinel-2"},
            )
            flags.append(flag)

        GreenwashFlag.objects.bulk_create(flags, ignore_conflicts=True)
        self.stdout.write(f"  -> {len(flags)} greenwash flags created")
