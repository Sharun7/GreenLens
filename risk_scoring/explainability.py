# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""Reusable explainability helpers for GreenLens PCRS outputs."""
import json

from .bias_detection import get_region, generate_bias_summary_table
from .models import _humanize_feature_name


FAIRNESS_METRICS = [
    {
        "metric": "Regional SHAP variance",
        "purpose": "Detects geographic uncertainty and possible uneven model coverage.",
    },
    {
        "metric": "Prediction interval width",
        "purpose": "Quantifies score uncertainty caused by location precision and data quality.",
    },
    {
        "metric": "Coverage error per region",
        "purpose": "Compares satellite verification coverage and consistency across geographies.",
    },
    {
        "metric": "Calibration curve",
        "purpose": "Tracks whether high PCRS scores line up with realized adverse outcomes over time.",
    },
]


def _latest_pcr(bond):
    if not bond:
        return None
    return bond.pcr_scores.order_by("-scored_at").first()


def _coerce_float(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _coerce_shap_values(pcr) -> dict:
    if not pcr:
        return {}

    shap_values = pcr.shap_values or {}
    if isinstance(shap_values, str):
        try:
            shap_values = json.loads(shap_values)
        except (json.JSONDecodeError, TypeError):
            shap_values = {}

    clean_values = {}
    if isinstance(shap_values, dict):
        for feature, contribution in shap_values.items():
            clean_values[str(feature)] = _coerce_float(contribution)

    if clean_values:
        return clean_values

    return {
        "flood_risk_index": _coerce_float(pcr.flood_contribution),
        "heat_stress_index": _coerce_float(pcr.heat_contribution),
        "drought_severity": _coerce_float(pcr.drought_contribution),
    }


def build_shap_factor_table(pcr, limit: int | None = None) -> list[dict]:
    """Return SHAP factors sorted by absolute contribution."""
    shap_values = _coerce_shap_values(pcr)
    total_abs = sum(abs(value) for value in shap_values.values()) or 0.0

    rows = []
    for feature, contribution in sorted(
        shap_values.items(),
        key=lambda item: abs(item[1]),
        reverse=True,
    ):
        share_pct = (abs(contribution) / total_abs * 100.0) if total_abs else 0.0
        rows.append({
            "feature": feature,
            "label": _humanize_feature_name(feature),
            "contribution": round(contribution, 4),
            "abs_contribution": round(abs(contribution), 4),
            "share_pct": round(share_pct, 1),
            "direction": "adds risk" if contribution >= 0 else "reduces risk",
        })

    return rows[:limit] if limit else rows


def build_prediction_explanation(bond=None, pcr=None) -> dict:
    """
    Three-level answer to: "Why is this bond risky?"

    Level 1 goes to map popups, level 2 to the detail summary, and level 3 to
    the SHAP technical chart/API payload.
    """
    pcr = pcr or _latest_pcr(bond)
    if not pcr:
        return {
            "available": False,
            "popup": "PCRS not available yet.",
            "detail_summary": "No PCRS score has been generated for this bond yet.",
            "technical_factors": [],
        }

    factors = build_shap_factor_table(pcr)
    top = factors[0] if factors else None
    country = getattr(bond or pcr.bond, "country", "the project site") or "the project site"
    risk_label = pcr.three_band_label

    if not top:
        return {
            "available": True,
            "score": round(float(pcr.score), 2),
            "risk_label": risk_label,
            "confidence_interval": pcr.confidence_interval,
            "popup": f"PCRS {pcr.score:.1f} - {risk_label}. Main driver: unavailable.",
            "detail_summary": f"This bond's project site in {country} is rated {risk_label.lower()}.",
            "technical_factors": [],
        }

    top_three = factors[:3]
    factor_clauses = [
        (
            f"{factor['label']} {factor['direction']} "
            f"({factor['share_pct']}% of explanation, "
            f"{abs(factor['contribution']):.2f} score points)"
        )
        for factor in top_three
    ]
    if len(factor_clauses) == 1:
        driver_sentence = factor_clauses[0]
    elif len(factor_clauses) == 2:
        driver_sentence = f"{factor_clauses[0]}, followed by {factor_clauses[1]}"
    else:
        driver_sentence = (
            f"{factor_clauses[0]}, followed by {factor_clauses[1]} "
            f"and {factor_clauses[2]}"
        )

    return {
        "available": True,
        "score": round(float(pcr.score), 2),
        "risk_label": risk_label,
        "confidence_interval": pcr.confidence_interval,
        "main_driver": top,
        "popup": f"PCRS {pcr.score:.1f} - {risk_label}. Main driver: {top['label']}.",
        "detail_summary": (
            f"This bond's project site in {country} is rated {risk_label.lower()}. "
            f"{driver_sentence}."
        ),
        "technical_factors": factors,
    }


def build_model_depth_framework(include_runtime_bias: bool = False) -> dict:
    """Return the model-depth framework used by UI and APIs."""
    bias_detection = None
    if include_runtime_bias:
        from .bias_detection import BiasDetector

        bias_detection = BiasDetector().run_full_analysis()

    return {
        "explainability": {
            "status": "implemented",
            "method": "SHAP",
            "levels": [
                {
                    "level": 1,
                    "name": "Popup answer",
                    "purpose": "5-second fund-manager read: PCRS band and main risk driver.",
                },
                {
                    "level": 2,
                    "name": "Detail summary",
                    "purpose": "Plain-English explanation with top SHAP contributors and shares.",
                },
                {
                    "level": 3,
                    "name": "Technical breakdown",
                    "purpose": "Full per-feature SHAP table/chart for audit and model review.",
                },
            ],
        },
        "bias_monitoring": {
            "status": "implemented",
            "runtime_bias_detection": bias_detection,
            "known_biases": generate_bias_summary_table()["biases"],
            "fairness_metrics": FAIRNESS_METRICS,
        },
    }


def build_bond_model_depth(bond, bias_results: dict | None = None) -> dict:
    """Per-bond explainability and current regional bias context."""
    pcr = _latest_pcr(bond)
    region = get_region(getattr(bond, "country", ""))
    region_stats = None
    if bias_results:
        region_stats = (
            bias_results.get("geographic_bias", {})
            .get("regional_stats", {})
            .get(region)
        )

    return {
        "region": region,
        "prediction_explanation": build_prediction_explanation(bond, pcr),
        "regional_bias_status": region_stats,
        "known_biases": generate_bias_summary_table()["biases"],
        "fairness_metrics": FAIRNESS_METRICS,
    }
