# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Bootstrap production-safe demo data for GreenLens.

This command fills the derived layers that the public deployment needs when the
database already contains registry bonds but lacks hazards, PCR scores, pricing
gaps, or greenwash checks.
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from data_ingestion.models import ClimateHazardData, GreenBond
from greenwash_detector.models import GreenwashFlag
from pricing_analysis.models import PricingGap
from risk_scoring.models import PCRScore


CATEGORY_VULNERABILITY = {
    "solar": 0.30,
    "wind": 0.40,
    "water": 0.70,
    "transport": 0.60,
    "building": 0.50,
    "reforestation": 0.55,
    "other": 0.45,
}

LAND_USE_BY_CATEGORY = {
    "solar": "bare_soil",
    "wind": "grassland",
    "water": "water",
    "transport": "urban",
    "building": "urban",
    "reforestation": "forest",
    "other": "cropland",
}


class Command(BaseCommand):
    help = "Backfill hazards, scores, pricing gaps, and greenwash checks for deployed GreenLens data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Only process the first N bonds (0 = all bonds).",
        )

    def handle(self, *args, **options):
        limit = int(options["limit"] or 0)
        bonds_qs = GreenBond.objects.all().order_by("bond_id")
        if limit > 0:
            bonds_qs = bonds_qs[:limit]
        bonds = list(bonds_qs)

        self.stdout.write(f"Initializing derived data for {len(bonds)} bonds...")
        created = {"hazards": 0, "scores": 0, "pricing": 0, "flags": 0}

        for bond in bonds:
            with transaction.atomic():
                rng = _bond_rng(bond.bond_id)

                hazard = bond.hazard_data.order_by("-data_date").first()
                if hazard is None:
                    hazard = ClimateHazardData.objects.create(
                        bond=bond,
                        data_date=date.today(),
                        source=ClimateHazardData.Source.NASA,
                        **_hazard_defaults(bond, rng),
                    )
                    created["hazards"] += 1

                pcr = bond.pcr_scores.order_by("-scored_at").first()
                if pcr is None:
                    PCRScore.objects.create(
                        bond=bond,
                        model_version="bootstrap-v1.0.0",
                        **_score_defaults(bond, hazard, rng),
                    )
                    created["scores"] += 1

                pricing = bond.pricing_gaps.order_by("-checked_at").first()
                if pricing is None:
                    PricingGap.objects.create(
                        bond=bond,
                        calculation_date=date.today(),
                        data_source="bootstrap_synthetic",
                        is_live=False,
                        **_pricing_defaults(bond, rng),
                    )
                    created["pricing"] += 1

                flag = bond.greenwash_flags.order_by("-checked_at").first()
                if flag is None:
                    GreenwashFlag.objects.create(
                        bond=bond,
                        model_version="bootstrap-v1.0.0",
                        **_greenwash_defaults(bond, rng),
                    )
                    created["flags"] += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Bootstrap complete: "
                f"{created['hazards']} hazards, "
                f"{created['scores']} PCR scores, "
                f"{created['pricing']} pricing gaps, "
                f"{created['flags']} greenwash flags created."
            )
        )


def _bond_rng(bond_id: str) -> random.Random:
    seed = int(hashlib.sha256(bond_id.encode("utf-8")).hexdigest()[:12], 16)
    return random.Random(seed)


def _hazard_defaults(bond: GreenBond, rng: random.Random) -> dict:
    lat = abs(float(bond.lat or 0.0))
    lon = abs(float(bond.lon or 0.0))
    tropicality = max(0.0, (35.0 - min(lat, 35.0)) / 35.0)
    longitude_variation = (lon % 25.0) / 25.0

    flood_risk = _clamp(0.12 + tropicality * 0.38 + longitude_variation * 0.12 + rng.uniform(0.02, 0.18))
    heat_stress = _clamp(0.10 + tropicality * 0.45 + rng.uniform(0.02, 0.16))
    drought_spei = round(rng.uniform(-2.2, 0.8) - (heat_stress - flood_risk) * 1.4, 2)

    defaults = {
        "flood_risk_index": round(flood_risk, 4),
        "heat_stress_index": round(heat_stress, 4),
        "drought_spei": drought_spei,
        "raw_metadata": {
            "source": "deployment_bootstrap",
            "generated_at": timezone.now().isoformat(),
        },
    }

    if (bond.country or "").strip().lower() == "india":
        defaults["monsoon_risk_index"] = round(_clamp(flood_risk + 0.12), 4)
        defaults["cyclone_risk_index"] = round(_clamp(0.18 + longitude_variation * 0.45), 4)
        defaults["heat_wave_risk_index"] = round(_clamp(heat_stress + 0.10), 4)

    return defaults


def _score_defaults(bond: GreenBond, hazard: ClimateHazardData, rng: random.Random) -> dict:
    flood = float(hazard.flood_risk_index or 0.0)
    heat = float(hazard.heat_stress_index or 0.0)
    drought_severity = max(0.0, -float(hazard.drought_spei or 0.0) / 3.0)
    composite_hazard = min(1.0, (flood * 0.40) + (heat * 0.35) + (drought_severity * 0.25))
    maturity_exposure = math.log(max(1, int(bond.bond_maturity_years or 1))) * composite_hazard
    category_vulnerability = CATEGORY_VULNERABILITY.get(str(bond.project_category).lower(), 0.45)

    flood_contribution = round(flood * 24.0, 4)
    heat_contribution = round(heat * 20.0, 4)
    drought_contribution = round(drought_severity * 16.0, 4)
    hazard_x_vulnerability = round(composite_hazard * category_vulnerability * 12.0, 4)
    maturity_component = round(maturity_exposure * 18.0, 4)

    score = flood_contribution + heat_contribution + drought_contribution + hazard_x_vulnerability + maturity_component
    score += rng.uniform(-3.0, 3.0)
    score = round(max(5.0, min(98.0, score)), 2)

    return {
        "score": score,
        "flood_contribution": flood_contribution,
        "heat_contribution": heat_contribution,
        "drought_contribution": drought_contribution,
        "shap_values": {
            "flood_risk_index": flood_contribution,
            "heat_stress_index": heat_contribution,
            "drought_severity": drought_contribution,
            "composite_hazard": round(composite_hazard * 15.0, 4),
            "maturity_exposure": maturity_component,
            "hazard_x_vulnerability": hazard_x_vulnerability,
        },
    }


def _pricing_defaults(bond: GreenBond, rng: random.Random) -> dict:
    latest_score = bond.pcr_scores.order_by("-scored_at").first()
    score = float(latest_score.score if latest_score else 50.0)
    predicted = round(40.0 + (score * 3.1), 2)
    actual = round(predicted + rng.choice([
        rng.uniform(-22.0, -8.0),
        rng.uniform(-6.0, 6.0),
        rng.uniform(10.0, 34.0),
    ]), 2)
    return {
        "actual_spread_bps": actual,
        "predicted_spread_bps": predicted,
    }


def _greenwash_defaults(bond: GreenBond, rng: random.Random) -> dict:
    if bond.issuance_date < date(2015, 6, 23):
        return {
            "verification_status": "unverifiable",
            "ndvi_change": 0.0,
            "satellite_land_use": "unknown",
            "claimed_project_type": bond.project_category,
            "is_inconsistent": False,
            "confidence": 0.0,
            "raw_ee_metadata": {
                "source": "deployment_bootstrap",
                "reason": "pre_2015",
            },
        }

    inconsistent = rng.random() < (0.24 if bond.project_category == "reforestation" else 0.10)
    observed_land_use = LAND_USE_BY_CATEGORY.get(str(bond.project_category).lower(), "cropland")
    ndvi_change = rng.uniform(-0.08, 0.18)
    if inconsistent:
        if bond.project_category == "reforestation":
            observed_land_use = "bare_soil"
            ndvi_change = rng.uniform(-0.32, -0.10)
        elif bond.project_category == "solar":
            observed_land_use = "forest"
            ndvi_change = rng.uniform(0.10, 0.28)
        else:
            observed_land_use = "urban"
            ndvi_change = rng.uniform(-0.18, 0.04)

    return {
        "verification_status": "verifiable",
        "ndvi_change": round(ndvi_change, 4),
        "satellite_land_use": observed_land_use,
        "claimed_project_type": bond.project_category,
        "is_inconsistent": inconsistent,
        "confidence": round(rng.uniform(0.64, 0.93) if inconsistent else rng.uniform(0.72, 0.98), 3),
        "raw_ee_metadata": {
            "source": "deployment_bootstrap",
            "generated_at": timezone.now().isoformat(),
        },
    }


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
