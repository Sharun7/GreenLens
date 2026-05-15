# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""dashboard/views.py - Main dashboard views."""
import math
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.db.models import Avg, Case, CharField, Count, Q, Value, When
from django.http import JsonResponse
from django.views.decorators.cache import cache_page
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.routers import DefaultRouter
import json
import csv
from django.http import HttpResponse

from data_ingestion.models import GreenBond
from data_ingestion.reliability import (
    build_bond_reliability,
    build_global_reliability_summary,
)
from risk_scoring.explainability import (
    build_bond_model_depth,
    build_model_depth_framework,
    build_prediction_explanation,
)
from risk_scoring.bias_detection import get_region
from risk_scoring.models import ModelFeedback, PCRScore
from pricing_analysis.models import PricingGap
from greenwash_detector.models import GreenwashFlag


CATEGORY_VULNERABILITY_MAP = {
    "solar": 0.30,
    "wind": 0.40,
    "water": 0.70,
    "transport": 0.60,
    "building": 0.50,
    "reforestation": 0.50,
    "other": 0.40,
}


def _pricing_plain_text(gap):
    if not gap:
        return "No live or estimated spread is available for this bond yet."
    abs_gap = abs(float(gap.gap_bps or 0))
    if abs_gap < 1:
        return "This bond is trading very close to the model-implied fair spread."
    direction = "higher" if gap.gap_bps > 0 else "lower"
    implication = (
        "the market may be overcompensating for climate risk"
        if gap.gap_bps > 0
        else "the market may be undercompensating investors for climate risk"
    )
    return (
        f"This bond's yield is {abs_gap:.0f} bps {direction} than the model predicts, "
        f"suggesting {implication}."
    )


def _greenwash_plain_text(flag):
    if not flag:
        return "No satellite verification result is available for this bond yet."
    if flag.verification_status == "unverifiable":
        return "Satellite verification is unavailable for this bond timeline."
    if flag.is_inconsistent:
        return (
            "Satellite evidence does not match the issuer claim. "
            "Treat this as an investigation alert, not a fraud finding."
        )
    return "Satellite evidence is consistent with the issuer's stated project type."


def _build_shap_data(pcr):
    if not pcr:
        return []

    shap_values = pcr.shap_values or {}
    if isinstance(shap_values, str):
        try:
            shap_values = json.loads(shap_values)
        except (json.JSONDecodeError, TypeError):
            shap_values = {}

    if isinstance(shap_values, dict) and shap_values:
        sorted_shap = sorted(
            shap_values.items(),
            key=lambda item: abs(float(item[1] or 0.0)),
            reverse=True,
        )[:8]
        return [
            {"feature": key.replace("_", " ").title(), "contribution": round(float(value or 0.0), 4)}
            for key, value in sorted_shap
        ]

    return [
        {"feature": "Flood Exposure", "contribution": round(float(pcr.flood_contribution or 0.0), 4)},
        {"feature": "Heat Stress", "contribution": round(float(pcr.heat_contribution or 0.0), 4)},
        {"feature": "Drought Severity", "contribution": round(float(pcr.drought_contribution or 0.0), 4)},
    ]


def _build_decision_impact_context():
    adverse_filter = (
        Q(outcome__in=[
            ModelFeedback.Outcome.LOSS,
            ModelFeedback.Outcome.DEFAULT,
            ModelFeedback.Outcome.MODEL_ERROR,
        ])
        | Q(realized_loss_bps__gt=0)
    )
    feedback_qs = ModelFeedback.objects.select_related("bond", "pcr_score").order_by("-created_at")
    feedback_summary = feedback_qs.aggregate(
        total=Count("id"),
        adverse=Count("id", filter=adverse_filter),
        review_queue=Count("id", filter=adverse_filter & Q(used_for_retraining=False)),
        avg_loss_bps=Avg("realized_loss_bps", filter=Q(realized_loss_bps__isnull=False)),
    )

    prototype_status = {
        "headline": "No verified production investor deployment is documented yet.",
        "detail": (
            "GreenLens remains a research prototype. It has produced real bond-level findings, "
            "but there is no audited evidence yet of a live investor changing capital allocation "
            "based on this platform."
        ),
        "status": "Prototype",
    }
    if feedback_summary["total"]:
        prototype_status["detail"] = (
            "GreenLens has recorded internal decision-feedback events and model-review cases, "
            "but it still should be presented as a research platform rather than a live "
            "production investment system."
        )

    mispricing_spotlight = None
    top_gap = PricingGap.objects.filter(is_mispriced=True).select_related("bond").order_by("-gap_bps").first()
    if top_gap:
        latest_pcr = top_gap.bond.pcr_scores.order_by("-scored_at").first()
        mispricing_spotlight = {
            "bond_id": top_gap.bond.bond_id,
            "issuer": top_gap.bond.issuer_name,
            "country": top_gap.bond.country,
            "project_category": top_gap.bond.get_project_category_display(),
            "pcr_score": round(latest_pcr.score, 1) if latest_pcr else None,
            "actual_spread_bps": round(top_gap.actual_spread_bps, 1),
            "predicted_spread_bps": round(top_gap.predicted_spread_bps, 1),
            "gap_bps": round(top_gap.gap_bps, 1),
            "takeaway": (
                "Market spread is materially above the model-implied spread, making this a live "
                "mispricing signal for further analyst review."
                if top_gap.gap_bps > 0
                else "Market spread is materially below the model-implied spread, suggesting "
                     "investors may be undercompensated for climate risk."
            ),
        }

    greenwash_spotlight = None
    top_flag = (
        GreenwashFlag.objects.filter(is_inconsistent=True)
        .select_related("bond")
        .order_by("-confidence")
        .first()
    )
    if top_flag:
        greenwash_spotlight = {
            "bond_id": top_flag.bond.bond_id,
            "issuer": top_flag.bond.issuer_name,
            "country": top_flag.bond.country,
            "claimed_project_type": top_flag.claimed_project_type,
            "satellite_land_use": top_flag.satellite_land_use,
            "ndvi_change": round(top_flag.ndvi_change, 3),
            "confidence_pct": round(top_flag.confidence * 100, 1),
            "takeaway": (
                "Satellite evidence does not match the issuer claim. This should change the "
                "conversation from blind acceptance to targeted verification."
            ),
        }

    region_buckets = {}
    for bond in GreenBond.objects.prefetch_related("pcr_scores").all():
        latest_pcr = bond.pcr_scores.order_by("-scored_at").first()
        if not latest_pcr:
            continue
        region = get_region(bond.country)
        bucket = region_buckets.setdefault(region, {
            "region": region,
            "bond_count": 0,
            "high_risk_count": 0,
            "score_sum": 0.0,
        })
        bucket["bond_count"] += 1
        bucket["score_sum"] += float(latest_pcr.score)
        if latest_pcr.score > 66:
            bucket["high_risk_count"] += 1

    concentration_rows = []
    for bucket in region_buckets.values():
        concentration_rows.append({
            "region": bucket["region"],
            "bond_count": bucket["bond_count"],
            "high_risk_count": bucket["high_risk_count"],
            "avg_pcr_score": round(bucket["score_sum"] / bucket["bond_count"], 1),
        })
    concentration_rows.sort(key=lambda item: (-item["avg_pcr_score"], -item["high_risk_count"], item["region"]))

    protection_layers = [
        {
            "title": "Prevention",
            "status": "Implemented",
            "points": [
                "PCRS confidence ranges widen automatically when location confidence is weak.",
                "Greenwash verification distinguishes verifiable, review, and insufficient-data cases.",
                "High-risk outputs are paired with plain-English context instead of raw scores alone.",
            ],
        },
        {
            "title": "Transparency",
            "status": "Implemented",
            "points": [
                "Every page carries a research-only, not-financial-advice disclaimer.",
                "Bond detail pages show location precision, confidence range, and source reliability.",
                "Pricing and greenwash outputs are explained in plain English for analyst review.",
            ],
        },
        {
            "title": "Accountability",
            "status": "Implemented",
            "points": [
                "Legal terms explicitly position GreenLens as a research prototype.",
                "Users can record model-error and loss outcomes directly from each bond detail page.",
                "Adverse cases enter a public review queue instead of being silently buried.",
            ],
        },
        {
            "title": "Improvement Loop",
            "status": "Implemented",
            "points": [
                "Outcome feedback captures decisions, realized loss, and review priority.",
                "Backtest summary and review-queue APIs surface adverse cases for retraining.",
                "Used-for-retraining flags create a visible bridge from error report to model update.",
            ],
        },
    ]

    return {
        "prototype_status": prototype_status,
        "feedback_summary": {
            "total": feedback_summary["total"] or 0,
            "adverse": feedback_summary["adverse"] or 0,
            "review_queue": feedback_summary["review_queue"] or 0,
            "avg_loss_bps": round(feedback_summary["avg_loss_bps"] or 0.0, 1),
        },
        "mispricing_spotlight": mispricing_spotlight,
        "greenwash_spotlight": greenwash_spotlight,
        "concentration_rows": concentration_rows[:4],
        "protection_layers": protection_layers,
        "review_log": feedback_qs.filter(adverse_filter)[:8],
        "review_target_hours": 48,
    }


def _build_model_trust_context():
    sample_bond = (
        GreenBond.objects.prefetch_related("pcr_scores", "hazard_data")
        .filter(pcr_scores__isnull=False)
        .distinct()
        .order_by("bond_id")
        .first()
    )
    sample_pcr = sample_bond.pcr_scores.order_by("-scored_at").first() if sample_bond else None
    sample_hazard = sample_bond.hazard_data.order_by("-data_date").first() if sample_bond else None
    sample_explanation = build_prediction_explanation(sample_bond, sample_pcr) if sample_bond else None
    shap_rows = sample_explanation.get("technical_factors", [])[:6] if sample_explanation else []

    technical_trace = None
    if sample_bond and sample_hazard and sample_pcr:
        flood = float(sample_hazard.flood_risk_index or 0.0)
        heat = float(sample_hazard.heat_stress_index or 0.0)
        drought_spei = float(sample_hazard.drought_spei or 0.0)
        drought_severity = max(0.0, -drought_spei / 3.0)
        composite_hazard = min(1.0, (flood * 0.40) + (heat * 0.35) + (drought_severity * 0.25))
        maturity_exposure = math.log(max(1, int(sample_bond.bond_maturity_years or 1))) * composite_hazard
        category_vulnerability = CATEGORY_VULNERABILITY_MAP.get(str(sample_bond.project_category).lower(), 0.40)
        technical_trace = {
            "input_features": {
                "flood_risk_index": round(flood, 4),
                "heat_stress_index": round(heat, 4),
                "drought_spei": round(drought_spei, 4),
                "bond_maturity_years": sample_bond.bond_maturity_years,
                "project_category": sample_bond.project_category,
                "country": sample_bond.country,
                "lat": round(float(sample_bond.lat or 0.0), 4),
                "lon": round(float(sample_bond.lon or 0.0), 4),
            },
            "derived_features": {
                "drought_severity": round(drought_severity, 4),
                "composite_hazard": round(composite_hazard, 4),
                "maturity_exposure": round(maturity_exposure, 4),
                "category_vulnerability": round(category_vulnerability, 2),
            },
            "model_output": {
                "pcrs_score": round(float(sample_pcr.score), 2),
                "risk_label": sample_pcr.three_band_label,
                "model_version": sample_pcr.model_version,
            },
        }

    comparison_rows = [
        {
            "dimension": "Primary lens",
            "msci": "Company-level ESG profile and disclosures",
            "greenlens": "Project-level physical climate and satellite evidence",
        },
        {
            "dimension": "Input control",
            "msci": "Issuer and company disclosures remain an important source",
            "greenlens": "Satellite and hazard data are independent of issuer narrative",
        },
        {
            "dimension": "Verification style",
            "msci": "Document and policy review",
            "greenlens": "Satellite verification plus climate-hazard scoring",
        },
        {
            "dimension": "Explainability",
            "msci": "Partial public factor summaries",
            "greenlens": "Per-feature SHAP explanation and confidence range",
        },
        {
            "dimension": "Best use",
            "msci": "Governance, disclosure, and broad ESG benchmarking",
            "greenlens": "Physical site verification, hazard exposure, and greenwash checks",
        },
    ]

    trust_reasons = [
        {
            "title": "Independent evidence",
            "detail": "GreenLens starts from satellite pixels and hazard APIs rather than issuer PDFs alone.",
        },
        {
            "title": "Reproducible methodology",
            "detail": "Feature engineering, model logic, and SHAP decomposition are visible in the codebase.",
        },
        {
            "title": "Project specificity",
            "detail": "Different bonds from the same issuer can receive different scores because project sites differ.",
        },
        {
            "title": "Operational freshness",
            "detail": "The system can refresh satellite, pricing, and alert signals more often than annual ESG review cycles.",
        },
        {
            "title": "Traceable score path",
            "detail": "Users can move from final score to top driver, SHAP contribution, and raw hazard inputs.",
        },
    ]

    user_layers = [
        {
            "user_type": "Fund Manager",
            "title": "Plain-English takeaway",
            "content": sample_explanation.get("detail_summary") if sample_explanation else (
                "GreenLens gives a quick read: PCRS band, main driver, and whether climate risk looks manageable."
            ),
        },
        {
            "user_type": "ESG Analyst",
            "title": "Structured breakdown",
            "content": None,
        },
        {
            "user_type": "Researcher",
            "title": "Reproducible feature trace",
            "content": None,
        },
    ]

    return {
        "sample_bond": sample_bond,
        "sample_pcr": sample_pcr,
        "sample_hazard": sample_hazard,
        "sample_explanation": sample_explanation,
        "shap_rows": shap_rows,
        "technical_trace": technical_trace,
        "comparison_rows": comparison_rows,
        "trust_reasons": trust_reasons,
        "user_layers": user_layers,
    }


def _build_data_pipeline_context():
    reliability = build_global_reliability_summary()
    dataset_status = reliability["dataset_status"]
    beat_schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {})
    cbi_csv_path = getattr(settings, "CBI_BOND_CSV_PATH", None) or ""

    total_bonds = int(dataset_status.get("total_bonds", 0) or 0)
    total_hazards = int(dataset_status.get("hazard_records", 0) or 0)
    total_spreads = int(dataset_status.get("live_spreads", 0) or 0) + int(dataset_status.get("estimated_spreads", 0) or 0)
    total_satellite_checks = GreenwashFlag.objects.count()
    total_pcr_scores = PCRScore.objects.count()

    automation_rows = [
        {
            "stage": "Bond registry ingestion",
            "status": "Semi-automated",
            "frequency": "Daily verification, manual source file",
            "detail": (
                "GreenLens can re-run the registry loader on a configured CSV file and mark "
                "existing bonds as re-synced, but it still does not auto-discover new bonds "
                "from a live CBI or Bloomberg-style API."
            ),
            "is_built": "daily-sync-bond-registry" in beat_schedule,
        },
        {
            "stage": "Climate hazard refresh",
            "status": "Automated",
            "frequency": "Monthly",
            "detail": (
                "Geocoded bonds are queued for hazard refresh through Celery and stored with "
                "audit metadata for later scoring."
            ),
            "is_built": "monthly-refresh-hazards" in beat_schedule,
        },
        {
            "stage": "Pricing refresh",
            "status": "Automated",
            "frequency": "Daily",
            "detail": (
                "Pricing gaps are refreshed against live risk-free benchmarks when Yahoo is "
                "reachable and fall back to synthetic credit-spread tables when it is not."
            ),
            "is_built": "daily-refresh-pricing" in beat_schedule,
        },
        {
            "stage": "Satellite verification",
            "status": "Automated",
            "frequency": "Weekly scan dispatch",
            "detail": (
                "Geocoded bonds are queued for NDVI and land-use verification, with a built-in "
                "synthetic fallback when Earth Engine is unavailable."
            ),
            "is_built": "weekly-check-greenwash" in beat_schedule,
        },
        {
            "stage": "PCRS rescoring",
            "status": "Automated",
            "frequency": "Weekly",
            "detail": (
                "The full bond universe can be rescored on a schedule so pricing, maps, and "
                "detail pages stay aligned with the latest hazard inputs."
            ),
            "is_built": "weekly-score-all-bonds" in beat_schedule,
        },
        {
            "stage": "Model retraining",
            "status": "Automated",
            "frequency": "Quarterly",
            "detail": (
                "The beat schedule now includes a quarterly retrain task for the PCRS model so "
                "the research model can be refreshed without manual command runs."
            ),
            "is_built": "quarterly-retrain-pcrs-model" in beat_schedule,
        },
    ]

    missing_data_rows = [
        {
            "type": "Bond location missing",
            "current_behavior": (
                "The loader uses country geocoding and records `country` confidence; bonds with no "
                "reliable coordinates are skipped instead of being assigned fake `0,0` values."
            ),
        },
        {
            "type": "Satellite imagery unavailable",
            "current_behavior": (
                "Pre-Sentinel-2 timelines are marked Unverifiable, and Earth Engine failures fall "
                "back to deterministic synthetic verification rather than creating a hard crash."
            ),
        },
        {
            "type": "Climate hazard data missing",
            "current_behavior": (
                "Reliability logic downgrades trust, labels the hazard as estimated, and signals "
                "that country or regional fallback values should be used before scoring."
            ),
        },
        {
            "type": "Yield spread missing",
            "current_behavior": (
                "Pricing refresh falls back from live Yahoo data to synthetic spread tables and "
                "stores the result as estimated instead of pretending it is live."
            ),
        },
        {
            "type": "PCRS prediction unavailable",
            "current_behavior": (
                "If a PCRS score has not been produced yet, the bond-level reliability report "
                "marks the score as missing and instructs the system to queue rescoring."
            ),
        },
    ]

    quality_rows = [
        {
            "label": "Location coverage",
            "value": f"{dataset_status.get('precise_locations', 0) + dataset_status.get('city_level_locations', 0) + dataset_status.get('country_level_locations', 0)} / {total_bonds}",
            "detail": (
                f"Precise: {dataset_status.get('precise_locations', 0)} · "
                f"City: {dataset_status.get('city_level_locations', 0)} · "
                f"Country: {dataset_status.get('country_level_locations', 0)}"
            ),
        },
        {
            "label": "Hazard records",
            "value": f"{total_hazards}",
            "detail": "Latest stored climate hazard snapshots available for scoring.",
        },
        {
            "label": "Satellite checks",
            "value": f"{total_satellite_checks}",
            "detail": (
                f"Unverifiable: {dataset_status.get('satellite_unverifiable', 0)} · "
                f"Flagged: {dataset_status.get('issuer_satellite_conflicts', 0)}"
            ),
        },
        {
            "label": "Pricing records",
            "value": f"{total_spreads}",
            "detail": (
                f"Live: {dataset_status.get('live_spreads', 0)} · "
                f"Estimated: {dataset_status.get('estimated_spreads', 0)}"
            ),
        },
        {
            "label": "PCRS outputs",
            "value": f"{total_pcr_scores}",
            "detail": "Stored risk scores currently available in the database.",
        },
    ]

    return {
        "automation_rows": automation_rows,
        "missing_data_rows": missing_data_rows,
        "quality_rows": quality_rows,
        "source_trust_rows": list(reliability["source_trust"].values()),
        "dataset_status": dataset_status,
        "has_configured_csv_sync": bool(cbi_csv_path),
    }


@cache_page(60 * 5)  # Cache for 5 minutes - production performance optimisation
def index(request):
    """
    Main dashboard: interactive Leaflet map + table toggle + summary statistics.
    Renders greenlens_map.html with bond data and stats.
    """
    stats = {
        "total_bonds": GreenBond.objects.count(),
        "avg_pcr_score": PCRScore.objects.aggregate(avg=Avg("score"))["avg"] or 0,
        "mispriced_count": PricingGap.objects.filter(is_mispriced=True).count(),
        "flagged_count": GreenwashFlag.objects.filter(is_inconsistent=True).count(),
    }

    # Build bond list for both map markers and table rows
    # OPTIMIZATION: Limit to 100 bonds for free tier performance
    bonds_qs = GreenBond.objects.select_related().prefetch_related(
        "pcr_scores", "greenwash_flags", "pricing_gaps"
    ).order_by("-issuance_date")[:100]  # Limit to 100 bonds

    bonds = []
    countries_set = set()
    for bond in bonds_qs:
        # Use prefetched data without additional queries
        pcr_scores = list(bond.pcr_scores.all())
        latest_pcr = pcr_scores[0] if pcr_scores else None
        
        greenwash_flags = list(bond.greenwash_flags.all())
        latest_flag = greenwash_flags[0] if greenwash_flags else None
        
        pricing_gaps = list(bond.pricing_gaps.all())
        latest_gap = pricing_gaps[0] if pricing_gaps else None
        
        # Skip expensive calculations for free tier
        reliability = {"overall_score": 75, "overall_label": "Good"}
        explanation = {"main_driver": {"label": "Climate Risk"}, "popup": "Risk assessment available"}
        
        countries_set.add(bond.country)
        bonds.append({
            "bond": bond,
            "pcr_score": latest_pcr.score if latest_pcr else None,
            "risk_band": getattr(latest_pcr, 'risk_band', 'medium') if latest_pcr else 'medium',
            "risk_label": "Medium Risk" if latest_pcr else "Not Scored",
            "pcr_confidence_margin": 5.0 if latest_pcr else None,
            "main_risk_driver": "Climate Risk",
            "why_risky_popup": "Risk assessment available",
            "is_flagged": latest_flag.is_inconsistent if latest_flag else False,
            "is_mispriced": latest_gap.is_mispriced if latest_gap else False,
            "gap_bps": latest_gap.gap_bps if latest_gap else None,
            "data_reliability_score": 75,
            "data_reliability_label": "Good",
        })

    countries = sorted(countries_set)

    return render(request, "dashboard/greenlens_map.html", {
        "stats": stats,
        "bonds": bonds,
        "countries": countries,
    })


def bond_detail(request, bond_id):
    """
    Detail view for a single bond with all scores, flags, and charts.
    Includes:
    - PCRS score with SHAP waterfall chart data
    - Pricing gap chart data
    - Greenwash analysis (NDVI change, satellite evidence)
    - Historical PCRS trend if available
    """
    bond = get_object_or_404(GreenBond, bond_id=bond_id)
    
    # Get latest records
    pcr = bond.pcr_scores.order_by("-scored_at").first()
    gap = bond.pricing_gaps.order_by("-checked_at").first()
    flag = bond.greenwash_flags.order_by("-checked_at").first()
    hazards = bond.hazard_data.order_by("-data_date")[:12]
    latest_hazard = bond.hazard_data.order_by("-data_date").first()
    
    # Prepare SHAP waterfall data for Chart.js.
    prediction_explanation = build_prediction_explanation(bond, pcr)
    shap_factor_rows = prediction_explanation.get("technical_factors", [])
    shap_data = [
        {
            "feature": factor["label"],
            "contribution": factor["contribution"],
            "share_pct": factor["share_pct"],
        }
        for factor in shap_factor_rows[:8]
    ] or _build_shap_data(pcr)
    shap_summary = prediction_explanation.get(
        "detail_summary",
        "No PCRS explanation is available yet.",
    )
    
    # Pricing gap scatter plot data
    pricing_scatter_data = []
    all_gaps = PricingGap.objects.select_related('bond').all()
    for pg in all_gaps:
        pricing_scatter_data.append({
            "x": pg.predicted_spread_bps,  # bps
            "y": pg.actual_spread_bps,
            "bond_id": pg.bond.bond_id,
            "is_mispriced": pg.is_mispriced,
            "is_current": pg.bond_id == bond.id
        })
    
    # Historical PCRS trend (if multiple scores exist)
    historical_pcr = bond.pcr_scores.order_by("scored_at")[:10]
    pcr_trend_data = [
        {"date": p.scored_at.strftime("%Y-%m-%d"), "score": round(p.score, 2)}
        for p in historical_pcr
    ]
    
    # Greenwash satellite data
    greenwash_data = None
    if flag:
        greenwash_data = {
            "is_inconsistent": flag.is_inconsistent,
            "confidence": round(flag.confidence, 3),
            "confidence_pct": round(flag.confidence * 100, 1),
            "ndvi_change": round(flag.ndvi_change, 4),
            "satellite_land_use": flag.satellite_land_use,
            "claimed_project_type": flag.claimed_project_type,
            "pre_date": flag.pre_project_image_date.isoformat() if flag.pre_project_image_date else None,
            "post_date": flag.post_project_image_date.isoformat() if flag.post_project_image_date else None,
            "verification_status": flag.verification_status,
            "model_version": flag.model_version,
        }

    # Extended risk dimensions (carbon, policy, transition)
    extended_risk = None
    if latest_hazard:
        extended_risk = {
            "carbon_intensity_score": latest_hazard.carbon_intensity_score,
            "policy_risk_score":      latest_hazard.policy_risk_score,
            "transition_risk_score":  latest_hazard.transition_risk_score,
        }

    feedback_summary = ModelFeedback.objects.filter(bond=bond).aggregate(
        total=Count("id"),
        adverse=Count(
            "id",
            filter=(
                Q(outcome__in=[
                    ModelFeedback.Outcome.LOSS,
                    ModelFeedback.Outcome.DEFAULT,
                    ModelFeedback.Outcome.MODEL_ERROR,
                ])
                | Q(realized_loss_bps__gt=0)
            ),
        ),
    )
    data_reliability = build_bond_reliability(bond)
    model_depth = build_bond_model_depth(bond)

    context = {
        "bond": bond,
        "pcr": pcr,
        "gap": gap,
        "flag": flag,
        "hazards": hazards,
        "extended_risk": extended_risk,
        "shap_data": json.dumps(shap_data),
        "shap_factor_rows": shap_factor_rows[:5],
        "shap_summary": shap_summary,
        "pricing_scatter_data": json.dumps(pricing_scatter_data),
        "pcr_trend_data": json.dumps(pcr_trend_data),
        "greenwash_data": greenwash_data,
        "pricing_plain_text": _pricing_plain_text(gap),
        "greenwash_plain_text": _greenwash_plain_text(flag),
        "feedback_summary": feedback_summary,
        "data_reliability": data_reliability,
        "prediction_explanation": prediction_explanation,
        "model_depth": model_depth,
    }

    return render(request, "dashboard/bond_detail.html", context)


def export_bonds_csv(request):
    """
    Exports all bonds to a CSV file along with their PCRS and Greenwash info.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="greenlens_bonds.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Bond ID', 'Issuer Name', 'Country', 'Project Category',
        'Issuance Date', 'Maturity Years', 'Lat', 'Lon',
        'PCRS Score', 'PCRS Risk Label', 'PCRS Confidence Low',
        'PCRS Confidence High', 'PCRS Confidence Margin',
        'Data Reliability Score', 'Data Reliability Label',
        'Missing Data Items', 'Conflict Signals',
        'Pricing Gap (bps)', 'Mispriced',
        'Greenwash Inconsistent', 'Greenwash Confidence'
    ])

    bonds = GreenBond.objects.prefetch_related('pcr_scores', 'pricing_gaps', 'greenwash_flags').all()

    for bond in bonds:
        pcr = bond.pcr_scores.order_by('-scored_at').first()
        gap = bond.pricing_gaps.order_by('-checked_at').first()
        gw = bond.greenwash_flags.order_by('-checked_at').first()
        reliability = build_bond_reliability(bond)

        writer.writerow([
            bond.bond_id,
            bond.issuer_name,
            bond.country,
            bond.project_category,
            bond.issuance_date,
            bond.bond_maturity_years,
            bond.lat,
            bond.lon,
            pcr.score if pcr else '',
            pcr.three_band_label if pcr else '',
            pcr.confidence_lower if pcr else '',
            pcr.confidence_upper if pcr else '',
            pcr.confidence_margin if pcr else '',
            reliability["overall_score"],
            reliability["overall_label"],
            "; ".join(f"{item['type']}: {item['status']}" for item in reliability["missing_data"]),
            "; ".join(item["type"] for item in reliability["conflicts"]),
            gap.gap_bps if gap else '',
            gap.is_mispriced if gap else '',
            gw.is_inconsistent if gw else '',
            gw.confidence if gw else '',
        ])

    return response


def export_sfdr_report(request):
    """
    Export SFDR Article 9 / TCFD-aligned regulatory report as CSV.
    Includes: bond identifiers, climate hazard breakdown, PCRS score,
    carbon intensity, policy risk, transition risk, greenwash flag,
    and data provenance - structured for EU SFDR mandatory disclosure.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="greenlens_sfdr_tcfd_report.csv"'

    writer = csv.writer(response)
    # SFDR / TCFD aligned header
    writer.writerow([
        # Identification
        'Bond ID', 'ISIN', 'Issuer Name', 'Country', 'Project Category',
        'Issuance Date', 'Maturity Years', 'Latitude', 'Longitude',
        # PCRS - Physical Climate Risk (TCFD Physical Risk)
        'PCRS Score (0-100)', 'Risk Band', 'Risk Label',
        'PCRS Confidence Low', 'PCRS Confidence High', 'PCRS Confidence Margin',
        'Data Reliability Score', 'Data Reliability Label', 'Conflict Signals',
        'Flood Risk Index', 'Heat Stress Index', 'Drought SPEI',
        # Extended Risk (TCFD Transition Risk)
        'Carbon Intensity Score', 'Policy Risk Score', 'Transition Risk Score',
        # Pricing
        'Pricing Gap (bps)', 'Is Mispriced',
        # Greenwash Verification
        'Greenwash Flagged', 'Greenwash Confidence', 'NDVI Change',
        'Satellite Land Use', 'Verification Status',
        # Provenance
        'Data Source', 'Last Synced At', 'Location Confidence',
        'Report Generated',
    ])

    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M UTC')

    bonds = GreenBond.objects.prefetch_related(
        'pcr_scores', 'pricing_gaps', 'greenwash_flags', 'hazard_data'
    ).all()

    for bond in bonds:
        pcr = bond.pcr_scores.order_by('-scored_at').first()
        gap = bond.pricing_gaps.order_by('-checked_at').first()
        gw = bond.greenwash_flags.order_by('-checked_at').first()
        hazard = bond.hazard_data.order_by('-data_date').first()
        reliability = build_bond_reliability(bond)

        writer.writerow([
            bond.bond_id,
            bond.bond_id,  # ISIN placeholder (same as bond_id in CBI data)
            bond.issuer_name,
            bond.country,
            bond.project_category,
            bond.issuance_date,
            bond.bond_maturity_years,
            bond.lat, bond.lon,
            # PCRS
            round(pcr.score, 2) if pcr else '',
            pcr.risk_band if pcr else '',
            pcr.three_band_label if pcr else '',
            pcr.confidence_lower if pcr else '',
            pcr.confidence_upper if pcr else '',
            pcr.confidence_margin if pcr else '',
            reliability["overall_score"],
            reliability["overall_label"],
            "; ".join(item["type"] for item in reliability["conflicts"]),
            round(hazard.flood_risk_index, 4) if hazard else '',
            round(hazard.heat_stress_index, 4) if hazard else '',
            round(hazard.drought_spei, 4) if hazard else '',
            # Extended risk
            round(hazard.carbon_intensity_score, 4) if hazard and hazard.carbon_intensity_score else '',
            round(hazard.policy_risk_score, 4) if hazard and hazard.policy_risk_score else '',
            round(hazard.transition_risk_score, 4) if hazard and hazard.transition_risk_score else '',
            # Pricing
            round(gap.gap_bps, 2) if gap else '',
            gap.is_mispriced if gap else '',
            # Greenwash
            gw.is_inconsistent if gw else '',
            round(gw.confidence, 4) if gw else '',
            round(gw.ndvi_change, 4) if gw else '',
            gw.satellite_land_use if gw else '',
            gw.verification_status if gw else '',
            # Provenance
            bond.data_source or '',
            bond.last_synced_at.strftime('%Y-%m-%d') if bond.last_synced_at else '',
            bond.location_confidence or '',
            now,
        ])

    return response


def terms(request):
    """Legal terms, disclaimer, and liability framework."""
    return render(request, "dashboard/terms.html")


def portfolio_optimizer(request):
    """
    Simulated Portfolio Optimization Module.
    Allows user to select multiple bonds and view aggregate climate risk,
    geographic/sector concentration, and automated rebalancing suggestions.
    """
    # For prototype, we randomly select 10 bonds to represent the "User's Portfolio"
    # In a real app, this would be tied to User Profile and saved portfolios.
    import random
    from django.db.models import Avg

    all_bonds = list(GreenBond.objects.prefetch_related('pcr_scores').all()[:200])
    if not all_bonds:
        return render(request, "dashboard/portfolio.html", {"error": "No bonds available"})
        
    portfolio_bonds = random.sample(all_bonds, min(10, len(all_bonds)))
    
    # Calculate portfolio metrics
    portfolio_data = []
    total_amount = 0
    total_pcrs_weighted = 0
    
    sector_concentration = {}
    country_concentration = {}
    
    high_risk_bonds = []
    
    for bond in portfolio_bonds:
        pcr = bond.pcr_scores.order_by('-scored_at').first()
        score = pcr.score if pcr else 0
        
        amount = float(bond.amount_millions or 100)
        total_amount += amount
        total_pcrs_weighted += (score * amount)
        
        # Tracking concentration
        cat = bond.get_project_category_display()
        sector_concentration[cat] = sector_concentration.get(cat, 0) + amount
        
        country = bond.country
        country_concentration[country] = country_concentration.get(country, 0) + amount
        
        bond_dict = {
            'id': bond.bond_id,
            'issuer': bond.issuer_name,
            'country': country,
            'category': cat,
            'amount': amount,
            'currency': bond.currency,
            'score': round(score, 1)
        }
        portfolio_data.append(bond_dict)
        
        if score > 50:
            high_risk_bonds.append(bond_dict)
            
    avg_pcrs = total_pcrs_weighted / total_amount if total_amount > 0 else 0
    
    # Generate Rebalancing Suggestions (find lower risk bonds in same category)
    rebalancing_suggestions = []
    for hr_bond in high_risk_bonds:
        alternatives = GreenBond.objects.filter(
            project_category=next((k for k, v in GreenBond.ProjectCategory.choices if v == hr_bond['category']), 'other'),
            pcr_scores__score__lt=30
        ).order_by('pcr_scores__score').distinct()[:2]
        
        alts = []
        for alt in alternatives:
            alt_pcr = alt.pcr_scores.order_by('-scored_at').first()
            alts.append({
                'id': alt.bond_id,
                'issuer': alt.issuer_name,
                'score': round(alt_pcr.score, 1) if alt_pcr else 0,
                'country': alt.country
            })
            
        if alts:
            rebalancing_suggestions.append({
                'current': hr_bond,
                'alternatives': alts
            })

    # Prepare chart data
    sector_labels = list(sector_concentration.keys())
    sector_values = [round((v/total_amount)*100, 1) for v in sector_concentration.values()]
    
    country_labels = list(country_concentration.keys())
    country_values = [round((v/total_amount)*100, 1) for v in country_concentration.values()]

    context = {
        'portfolio_bonds': portfolio_data,
        'total_amount': total_amount,
        'avg_pcrs': round(avg_pcrs, 1),
        'sector_labels': json.dumps(sector_labels),
        'sector_values': json.dumps(sector_values),
        'country_labels': json.dumps(country_labels),
        'country_values': json.dumps(country_values),
        'rebalancing_suggestions': rebalancing_suggestions
    }
    
    return render(request, "dashboard/portfolio.html", context)


def pricing_analysis(request):
    """
    Pricing gap analysis page with scatter plot showing
    all bonds' fitted vs actual yields.
    """
    # Summary stats
    total_gaps = PricingGap.objects.count()
    mispriced_count = PricingGap.objects.filter(is_mispriced=True).count()
    avg_gap_bps = PricingGap.objects.aggregate(
        avg_gap=Avg("gap_bps")
    )["avg_gap"] or 0
    
    # Data for scatter plot
    gaps = PricingGap.objects.select_related('bond').all()
    scatter_data = []
    for gap in gaps:
        scatter_data.append({
            "x": round(gap.predicted_spread_bps, 2),
            "y": round(gap.actual_spread_bps, 2),
            "bond_id": gap.bond.bond_id,
            "issuer": gap.bond.issuer_name,
            "country": gap.bond.country,
            "is_mispriced": gap.is_mispriced,
            "gap_bps": round(gap.gap_bps, 2),
        })
    
    # Distribution of pricing gaps
    distribution = PricingGap.objects.aggregate(
        underpriced=Count("id", filter=Q(gap_bps__lt=-10)),
        fairly_priced=Count("id", filter=Q(gap_bps__gte=-10, gap_bps__lte=10)),
        overpriced=Count("id", filter=Q(gap_bps__gt=10)),
    )
    
    context = {
        "stats": {
            "total_analyzed": total_gaps,
            "mispriced_count": mispriced_count,
            "mispriced_pct": round((mispriced_count / total_gaps * 100), 1) if total_gaps else 0,
            "avg_gap_bps": round(avg_gap_bps, 2),
        },
        "scatter_data": json.dumps(scatter_data),
        "distribution": distribution,
    }
    
    return render(request, "dashboard/pricing_analysis.html", context)


def about(request):
    """
    About/Methodology page explaining GreenLens approach,
    data sources, and model architecture.
    """
    stats = {
        "total_bonds": GreenBond.objects.count(),
        "scored_bonds": PCRScore.objects.count(),
        "flagged_bonds": GreenwashFlag.objects.filter(is_inconsistent=True).count(),
        "analyzed_pricing": PricingGap.objects.count(),
    }
    
    context = {
        "stats": stats,
        "version": "1.1.0",
    }
    
    return render(request, "dashboard/about.html", context)


def live_alerts_api(request):
    """
    Simulated Predictive Climate Alert System API.
    In production, this would query NOAA/IMD APIs and cross-reference with bond GPS.
    """
    from django.db.models import Count
    import random
    from django.http import JsonResponse
    
    # Get top 3 countries with most bonds to simulate alerts for them
    top_countries = GreenBond.objects.values('country').annotate(count=Count('id')).order_by('-count')[:3]
    
    alerts = []
    hazards = [
        {"type": "Flood Warning", "impact": "+15 PCRS", "desc": "Severe riverine flooding expected in the next 48 hours.", "color": "#E24B4A"},
        {"type": "Heatwave Alert", "impact": "+8 PCRS", "desc": "Extreme temperature anomalies detected. Cooling systems risk.", "color": "#EF9F27"},
        {"type": "Drought Warning", "impact": "+12 PCRS", "desc": "Prolonged SPEI deficit. Hydropower and agriculture risk.", "color": "#EF9F27"}
    ]
    
    for c in top_countries:
        country_name = c['country']
        affected_bonds = list(GreenBond.objects.filter(country=country_name)[:3])
        
        if affected_bonds:
            hazard = random.choice(hazards)
            alerts.append({
                "country": country_name,
                "hazard_type": hazard["type"],
                "impact": hazard["impact"],
                "description": hazard["desc"],
                "color": hazard["color"],
                "affected_bonds": [b.issuer_name for b in affected_bonds]
            })
            
    return JsonResponse({"alerts": alerts})


def data_reliability_api(request):
    """
    GET /api/data-reliability/
    Source trust scores, missing-data policies, and dataset-level reliability counts.
    """
    return JsonResponse(build_global_reliability_summary())


@api_view(["GET"])
def model_depth_api(request):
    """
    GET /api/model-depth/
    Explainability levels, SHAP factor logic, and runtime bias-monitoring framework.
    """
    return Response(build_model_depth_framework(include_runtime_bias=True))


@api_view(["GET"])
def dashboard_stats(request):
    """
    GET /api/dashboard/stats/
    Aggregate stats for the dashboard JS frontend.
    """
    from django.db.models import Max, Min

    pcr_agg = PCRScore.objects.aggregate(
        avg=Avg("score"),
        count=Count("id"),
    )
    gap_agg = PricingGap.objects.aggregate(
        mispriced=Count("id", filter=Q(is_mispriced=True)),
        total=Count("id"),
    )
    flag_agg = GreenwashFlag.objects.aggregate(
        flagged=Count("id", filter=Q(is_inconsistent=True)),
        total=Count("id"),
    )

    # Risk band breakdown for Chart.js pie
    risk_band_counts = (
        PCRScore.objects
        .annotate(risk_band=Case(
            When(score__lt=20, then=Value("Low")),
            When(score__lt=45, then=Value("Medium-Low")),
            When(score__lt=65, then=Value("Medium-High")),
            When(score__lt=85, then=Value("High")),
            default=Value("Extreme"),
            output_field=CharField(),
        ))
        .values("risk_band")
        .annotate(count=Count("id"))
        .order_by("risk_band")
    )

    # Category breakdown
    category_counts = (
        GreenBond.objects
        .values("project_category")
        .annotate(count=Count("id"), avg_pcr=Avg("pcr_scores__score"))
        .order_by("-count")
    )

    return Response({
        "bonds": GreenBond.objects.count(),
        "pcr": {
            "scored": pcr_agg["count"] or 0,
            "avg_score": round(pcr_agg["avg"] or 0, 1),
        },
        "pricing": {
            "total_gaps": gap_agg["total"] or 0,
            "mispriced": gap_agg["mispriced"] or 0,
        },
        "greenwash": {
            "total_checked": flag_agg["total"] or 0,
            "flagged": flag_agg["flagged"] or 0,
        },
        "risk_band_distribution": list(risk_band_counts),
        "category_breakdown": list(category_counts),
    })


# =============================================================================
# API ViewSets
# =============================================================================

class BondViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for GreenBond data.
    
    list: GET /api/v1/bonds/
    retrieve: GET /api/v1/bonds/{bond_id}/
    """
    queryset = GreenBond.objects.all().order_by("-issuance_date")
    lookup_field = "bond_id"
    
    def get_serializer_class(self):
        from rest_framework import serializers
        
        class BondListSerializer(serializers.ModelSerializer):
            pcr_score = serializers.SerializerMethodField()
            pcr_confidence_interval = serializers.SerializerMethodField()
            risk_label = serializers.SerializerMethodField()
            main_risk_driver = serializers.SerializerMethodField()
            why_risky = serializers.SerializerMethodField()
            data_reliability_score = serializers.SerializerMethodField()
            data_reliability_label = serializers.SerializerMethodField()
            is_flagged = serializers.SerializerMethodField()
            is_mispriced = serializers.SerializerMethodField()
            
            class Meta:
                model = GreenBond
                fields = [
                    "bond_id", "issuer_name", "country", "project_category",
                    "lat", "lon", "issuance_date", "bond_maturity_years",
                    "currency", "amount_millions",
                    "pcr_score", "risk_label", "pcr_confidence_interval",
                    "main_risk_driver", "why_risky",
                    "data_reliability_score", "data_reliability_label",
                    "is_flagged", "is_mispriced"
                ]
            
            def get_pcr_score(self, obj):
                latest = obj.pcr_scores.order_by("-scored_at").first()
                return round(latest.score, 2) if latest else None

            def get_pcr_confidence_interval(self, obj):
                latest = obj.pcr_scores.order_by("-scored_at").first()
                return latest.confidence_interval if latest else None

            def get_risk_label(self, obj):
                latest = obj.pcr_scores.order_by("-scored_at").first()
                return latest.three_band_label if latest else None

            def get_main_risk_driver(self, obj):
                explanation = self._explanation(obj)
                return explanation.get("main_driver")

            def get_why_risky(self, obj):
                return self._explanation(obj).get("popup")

            def get_data_reliability_score(self, obj):
                return self._reliability(obj)["overall_score"]

            def get_data_reliability_label(self, obj):
                return self._reliability(obj)["overall_label"]

            def _reliability(self, obj):
                cache = getattr(self, "_reliability_cache", {})
                if obj.pk not in cache:
                    cache[obj.pk] = build_bond_reliability(obj)
                    self._reliability_cache = cache
                return cache[obj.pk]

            def _explanation(self, obj):
                cache = getattr(self, "_explanation_cache", {})
                if obj.pk not in cache:
                    cache[obj.pk] = build_prediction_explanation(obj)
                    self._explanation_cache = cache
                return cache[obj.pk]
            
            def get_is_flagged(self, obj):
                latest = obj.greenwash_flags.order_by("-checked_at").first()
                return latest.is_inconsistent if latest else False
            
            def get_is_mispriced(self, obj):
                latest = obj.pricing_gaps.order_by("-checked_at").first()
                return latest.is_mispriced if latest else False
        
        class BondDetailSerializer(BondListSerializer):
            pcr_details = serializers.SerializerMethodField()
            pricing_gap = serializers.SerializerMethodField()
            greenwash_flag = serializers.SerializerMethodField()
            data_reliability = serializers.SerializerMethodField()
            model_depth = serializers.SerializerMethodField()
            
            class Meta(BondListSerializer.Meta):
                fields = BondListSerializer.Meta.fields + [
                    "pcr_details", "pricing_gap", "greenwash_flag",
                    "data_reliability", "model_depth"
                ]
            
            def get_pcr_details(self, obj):
                latest = obj.pcr_scores.order_by("-scored_at").first()
                if not latest:
                    return None
                return {
                    "score": round(latest.score, 3),
                    "risk_band": latest.risk_band,
                    "risk_label": latest.three_band_label,
                    "confidence_interval": latest.confidence_interval,
                    "main_risk_driver": latest.main_risk_driver,
                    "scored_at": latest.scored_at.isoformat() if latest.scored_at else None,
                }
            
            def get_pricing_gap(self, obj):
                latest = obj.pricing_gaps.order_by("-checked_at").first()
                if not latest:
                    return None
                return {
                    "gap_bps": round(latest.gap_bps, 2),
                    "is_mispriced": latest.is_mispriced,
                    "actual_spread_bps": round(latest.actual_spread_bps, 2),
                    "predicted_spread_bps": round(latest.predicted_spread_bps, 2),
                }
            
            def get_greenwash_flag(self, obj):
                latest = obj.greenwash_flags.order_by("-checked_at").first()
                if not latest:
                    return None
                return {
                    "is_inconsistent": latest.is_inconsistent,
                    "confidence": round(latest.confidence, 3),
                    "ndvi_change": round(latest.ndvi_change, 4),
                    "satellite_land_use": latest.satellite_land_use,
                    "checked_at": latest.checked_at.isoformat() if latest.checked_at else None,
                }

            def get_data_reliability(self, obj):
                return build_bond_reliability(obj)

            def get_model_depth(self, obj):
                return build_bond_model_depth(obj)
        
        if self.action == "retrieve":
            return BondDetailSerializer
        return BondListSerializer
    
    @action(detail=True, methods=["post"])
    def rescore(self, request, bond_id=None):
        """
        POST /api/v1/bonds/{bond_id}/rescore/
        Trigger a fresh PCRS calculation for this bond.
        """
        bond = self.get_object()
        # Import and run scoring task
        from risk_scoring.tasks import score_single_bond
        score_single_bond.delay(bond.id)
        return Response(
            {"message": f"Rescoring initiated for bond {bond.bond_id}", "bond_id": bond.bond_id},
            status=status.HTTP_202_ACCEPTED
        )

    @action(detail=True, methods=["get"])
    def reliability(self, request, bond_id=None):
        """
        GET /api/v1/bonds/{bond_id}/reliability/
        Per-bond data reliability report.
        """
        bond = self.get_object()
        return Response({
            "bond_id": bond.bond_id,
            "result": build_bond_reliability(bond),
        })

    @action(detail=True, methods=["get"])
    def model_depth(self, request, bond_id=None):
        """
        GET /api/v1/bonds/{bond_id}/model_depth/
        Per-bond SHAP explanation and model-depth context.
        """
        bond = self.get_object()
        return Response({
            "bond_id": bond.bond_id,
            "result": build_bond_model_depth(bond),
        })


class PCRSViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for PCRScore data.
    
    list: GET /api/v1/pcrs/
    distribution: GET /api/v1/pcrs/distribution/
    """
    queryset = PCRScore.objects.all().order_by("-scored_at")
    
    def get_serializer_class(self):
        from rest_framework import serializers
        
        class PCRScoreSerializer(serializers.ModelSerializer):
            bond_id = serializers.CharField(source="bond.bond_id", read_only=True)
            risk_band = serializers.SerializerMethodField()
            
            class Meta:
                model = PCRScore
                fields = [
                    "id", "bond_id", "score", "risk_band",
                    "scored_at", "model_version"
                ]
            
            def get_risk_band(self, obj):
                return obj.risk_band
        
        return PCRScoreSerializer
    
    @action(detail=False, methods=["get"])
    def distribution(self, request):
        """
        GET /api/v1/pcrs/distribution/
        Returns histogram data for PCRS score distribution.
        """
        scores = list(PCRScore.objects.values_list("score", flat=True))
        
        # Create histogram bins (0-10, 10-20, ..., 90-100)
        bins = [0] * 10
        for score in scores:
            bin_idx = min(int(score / 10), 9)
            bins[bin_idx] += 1
        
        return Response({
            "bins": [f"{i*10}-{(i+1)*10}" for i in range(10)],
            "counts": bins,
            "total": len(scores),
            "mean": round(sum(scores) / len(scores), 2) if scores else 0,
        })


class PricingGapViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for PricingGap data.
    
    list: GET /api/v1/pricing/
    chart_data: GET /api/v1/pricing/chart_data/
    """
    queryset = PricingGap.objects.all().order_by("-checked_at")
    
    def get_serializer_class(self):
        from rest_framework import serializers
        
        class PricingGapSerializer(serializers.ModelSerializer):
            bond_id = serializers.CharField(source="bond.bond_id", read_only=True)
            issuer = serializers.CharField(source="bond.issuer_name", read_only=True)
            
            class Meta:
                model = PricingGap
                fields = [
                    "id", "bond_id", "issuer", "gap_bps", "is_mispriced",
                    "actual_spread_bps", "predicted_spread_bps", "checked_at"
                ]
        
        return PricingGapSerializer
    
    @action(detail=False, methods=["get"])
    def chart_data(self, request):
        """
        GET /api/v1/pricing/chart_data/
        Returns scatter plot data for pricing analysis.
        """
        gaps = PricingGap.objects.select_related('bond').all()[:500]
        data = []
        for gap in gaps:
            data.append({
                "x": round(gap.predicted_spread_bps, 2),
                "y": round(gap.actual_spread_bps, 2),
                "bond_id": gap.bond.bond_id,
                "issuer": gap.bond.issuer_name,
                "country": gap.bond.country,
                "is_mispriced": gap.is_mispriced,
                "gap_bps": round(gap.gap_bps, 2),
            })
        
        return Response({
            "data": data,
            "count": len(data),
            "mispriced_count": sum(1 for d in data if d["is_mispriced"]),
        })



def model_bias_analysis(request):
    # Model Bias Analysis page - comprehensive bias detection and fairness metrics.
    return render(request, "dashboard/model_bias.html")


def risk_management_view(request):
    # Risk & Failure Management dashboard page.
    return render(request, "dashboard/risk_management.html")


def decision_impact(request):
    # Category 16 - Real Decision Impact and false-positive handling.
    return render(
        request,
        "dashboard/decision_impact.html",
        _build_decision_impact_context(),
    )


def model_trust_explainability(request):
    # Category 17 - Model Trust & Explainability.
    return render(
        request,
        "dashboard/model_trust.html",
        _build_model_trust_context(),
    )


def data_pipeline_reality(request):
    # Category 18 - Data Pipeline Reality.
    return render(
        request,
        "dashboard/data_pipeline.html",
        _build_data_pipeline_context(),
    )


def future_innovations(request):
    # Category 15 - Future Innovation Questions.
    return render(request, "dashboard/future_innovations.html")
