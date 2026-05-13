# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
data_ingestion/reliability.py — data reliability framework for GreenLens.

This module turns Category 10 into executable product logic: source trust
scores, missing-data handling, and conflict resolution are computed per bond.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SOURCE_TRUST = {
    "satellite": {
        "name": "Satellite physical evidence",
        "sources": "ESA Sentinel-2 / NASA Earthdata",
        "trust_score": 9,
        "trust_label": "Most trustworthy",
        "reason": "Independent physical observation; issuer cannot rewrite satellite pixels.",
    },
    "climate": {
        "name": "Climate hazard data",
        "sources": "World Bank Climate API / NASA Earthdata",
        "trust_score": 8,
        "trust_label": "Very trustworthy",
        "reason": "Intergovernmental and peer-reviewed climate datasets.",
    },
    "registry": {
        "name": "Bond registry data",
        "sources": "CBI / IMF / Refinitiv plus issuer disclosures",
        "trust_score": 6,
        "trust_label": "Partially trustworthy",
        "reason": "Core registry data is useful, but project-level location can be incomplete.",
    },
    "market": {
        "name": "Yield spread data",
        "sources": "Yahoo Finance / synthetic spread table fallback",
        "trust_score": 6,
        "trust_label": "Moderately trustworthy",
        "reason": "Market-responsive, but coverage is uneven for emerging market bonds.",
    },
    "pcrs": {
        "name": "PCRS model output",
        "sources": "XGBoost + SHAP research model",
        "trust_score": 5,
        "trust_label": "Research grade",
        "reason": "Useful indicator, not a certified financial rating.",
    },
}

EVIDENCE_HIERARCHY = [
    {
        "level": 1,
        "name": "Satellite physical evidence",
        "rule": "Highest priority when issuer claims conflict with observed land use.",
    },
    {
        "level": 2,
        "name": "Intergovernmental climate APIs",
        "rule": "Used for physical hazard baselines and conservative hazard comparison.",
    },
    {
        "level": 3,
        "name": "Market financial data",
        "rule": "Shown alongside model-implied spread; conflicts become mispricing signals.",
    },
    {
        "level": 4,
        "name": "Issuer self-reported data",
        "rule": "Lowest priority; used as a claim to verify, not as final proof.",
    },
]

MISSING_DATA_POLICIES = [
    {
        "type": "Bond location missing",
        "handling": "Use city centroid, then country centroid; skip only when no usable location exists.",
    },
    {
        "type": "Satellite imagery missing",
        "handling": "Try multiple date windows and cloud filtering; mark Unverifiable instead of flagging.",
    },
    {
        "type": "Yield spread missing",
        "handling": "Use a credit-spread estimate and label it Estimated, not live market data.",
    },
    {
        "type": "Climate hazard data missing",
        "handling": "Use country/regional fallback values and mark the hazard source as estimated.",
    },
]


@dataclass(frozen=True)
class SourceStatus:
    key: str
    name: str
    sources: str
    trust_score: int
    effective_score: int
    status: str
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "sources": self.sources,
            "trust_score": self.trust_score,
            "effective_score": self.effective_score,
            "status": self.status,
            "note": self.note,
        }


def _latest_related(bond, related_name: str, date_field: str):
    return getattr(bond, related_name).order_by(f"-{date_field}").first()


def _source_status(
    key: str,
    *,
    effective_score: int | None = None,
    status: str,
    note: str,
) -> SourceStatus:
    base = SOURCE_TRUST[key]
    return SourceStatus(
        key=key,
        name=base["name"],
        sources=base["sources"],
        trust_score=base["trust_score"],
        effective_score=effective_score if effective_score is not None else base["trust_score"],
        status=status,
        note=note,
    )


def _location_missing_status(bond) -> dict[str, Any]:
    if bond.lat is None or bond.lon is None:
        return {
            "type": "Bond location",
            "status": "missing",
            "action": "Bond is excluded from spatial scoring until a usable project location is available.",
        }

    if bond.location_confidence == "precise":
        return {
            "type": "Bond location",
            "status": "exact",
            "action": "GPS/address-level coordinates used directly.",
        }
    if bond.location_confidence == "city":
        return {
            "type": "Bond location",
            "status": "city-level fallback",
            "action": "City centroid used; PCRS confidence interval is widened.",
        }
    return {
        "type": "Bond location",
        "status": "country-level fallback",
        "action": "Country centroid used; PCRS confidence interval is widened materially.",
    }


def build_bond_reliability(bond) -> dict[str, Any]:
    """
    Build a per-bond reliability report.

    The result is JSON-serialisable and safe to use in APIs, templates, and CSV
    exports.
    """
    pcr = _latest_related(bond, "pcr_scores", "scored_at")
    gap = _latest_related(bond, "pricing_gaps", "checked_at")
    flag = _latest_related(bond, "greenwash_flags", "checked_at")
    hazard = _latest_related(bond, "hazard_data", "data_date")

    source_statuses: list[SourceStatus] = []
    missing_data: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    missing_data.append(_location_missing_status(bond))

    # Registry / issuer data
    registry_score = 6
    if bond.location_confidence == "city":
        registry_score = 5
    elif bond.location_confidence == "country":
        registry_score = 4
    if bond.lat is None or bond.lon is None:
        registry_score = 2
    source_statuses.append(_source_status(
        "registry",
        effective_score=registry_score,
        status=bond.location_confidence if bond.lat is not None and bond.lon is not None else "missing location",
        note=f"{bond.data_source or 'registry'} data used; location confidence is {bond.location_confidence}.",
    ))

    # Satellite evidence
    if flag is None:
        source_statuses.append(_source_status(
            "satellite",
            effective_score=0,
            status="missing",
            note="No satellite verification record is available yet.",
        ))
        missing_data.append({
            "type": "Satellite imagery",
            "status": "not checked",
            "action": "Queue greenwash verification; do not infer consistency from missing imagery.",
        })
    elif flag.verification_status == "unverifiable":
        source_statuses.append(_source_status(
            "satellite",
            effective_score=0,
            status="unverifiable",
            note="Satellite verification is unavailable for this bond timeline.",
        ))
        missing_data.append({
            "type": "Satellite imagery",
            "status": "unverifiable",
            "action": "Show Unverifiable and avoid false greenwash flags.",
        })
    else:
        flag_meta = flag.raw_ee_metadata or {}
        if not isinstance(flag_meta, dict):
            flag_meta = {}
        raw_source = flag_meta.get("method") or flag_meta.get("source", "gee_or_cnn")
        effective = 9 if raw_source != "synthetic" else 6
        source_statuses.append(_source_status(
            "satellite",
            effective_score=effective,
            status="verified" if not flag.is_inconsistent else "conflict detected",
            note=f"Observed land use: {flag.satellite_land_use}; claimed: {flag.claimed_project_type}.",
        ))
        if flag.is_inconsistent:
            conflicts.append({
                "type": "Issuer claim vs satellite evidence",
                "source_a": "Issuer claim",
                "source_b": "Satellite / CNN / NDVI",
                "resolution": "Satellite physical evidence has priority; greenwash review flag raised.",
                "severity": "high",
            })

    # Climate hazard data
    if hazard is None:
        source_statuses.append(_source_status(
            "climate",
            effective_score=0,
            status="missing",
            note="No climate hazard record is available yet.",
        ))
        missing_data.append({
            "type": "Climate hazard data",
            "status": "missing",
            "action": "Use country/regional fallback before scoring, then label as estimated.",
        })
    else:
        raw_meta = hazard.raw_metadata or {}
        if not isinstance(raw_meta, dict):
            raw_meta = {}
        is_estimate = bool(
            raw_meta.get("regional_estimate")
            or raw_meta.get("heuristic_fallback")
            or raw_meta.get("fallback")
        )
        source_statuses.append(_source_status(
            "climate",
            effective_score=6 if is_estimate else 8,
            status="regional estimate" if is_estimate else "available",
            note=f"Climate source: {hazard.get_source_display()}; latest date: {hazard.data_date}.",
        ))

        nasa_flood = raw_meta.get("nasa_flood_risk")
        wb_flood = raw_meta.get("world_bank_flood_risk")
        if nasa_flood is not None and wb_flood is not None:
            delta = abs(float(nasa_flood) - float(wb_flood))
            if delta >= 0.2:
                conflicts.append({
                    "type": "Climate source disagreement",
                    "source_a": "NASA flood history",
                    "source_b": "World Bank flood risk",
                    "resolution": "Use the higher risk value and mark uncertainty.",
                    "severity": "medium",
                })

    # Market spread data
    if gap is None:
        source_statuses.append(_source_status(
            "market",
            effective_score=0,
            status="missing",
            note="No pricing gap record is available yet.",
        ))
        missing_data.append({
            "type": "Yield spread",
            "status": "missing",
            "action": "Use synthetic credit spread estimate and label it Estimated.",
        })
    else:
        source_statuses.append(_source_status(
            "market",
            effective_score=6 if gap.is_live else 4,
            status="live" if gap.is_live else "estimated",
            note=f"{gap.data_source} spread; gap is {gap.gap_bps:+.1f} bps.",
        ))
        if gap.is_mispriced:
            conflicts.append({
                "type": "Market pricing vs PCRS model",
                "source_a": "Yahoo/market spread",
                "source_b": "PCRS-implied fair spread",
                "resolution": "Show both values and flag as mispriced; user decides investment action.",
                "severity": "medium",
            })

    # PCRS model output
    if pcr is None:
        source_statuses.append(_source_status(
            "pcrs",
            effective_score=0,
            status="missing",
            note="No PCRS prediction is available yet.",
        ))
        missing_data.append({
            "type": "PCRS score",
            "status": "missing",
            "action": "Queue rescoring before showing a risk recommendation.",
        })
    else:
        margin = pcr.confidence_margin
        source_statuses.append(_source_status(
            "pcrs",
            effective_score=5,
            status="research indicator",
            note=f"PCRS {pcr.score:.1f} ± {margin:.0f}; interval based on location confidence.",
        ))

    effective_scores = [s.effective_score for s in source_statuses if s.effective_score > 0]
    overall_score = round(sum(effective_scores) / len(effective_scores), 1) if effective_scores else 0.0

    return {
        "overall_score": overall_score,
        "overall_label": _overall_label(overall_score),
        "sources": [status.as_dict() for status in source_statuses],
        "missing_data": missing_data,
        "conflicts": conflicts,
        "evidence_hierarchy": EVIDENCE_HIERARCHY,
        "missing_data_policies": MISSING_DATA_POLICIES,
    }


def _overall_label(score: float) -> str:
    if score >= 7.5:
        return "High reliability"
    if score >= 5.0:
        return "Moderate reliability"
    if score > 0:
        return "Low reliability"
    return "Insufficient data"


def build_global_reliability_summary() -> dict[str, Any]:
    """Aggregate reliability framework metadata and dataset-level counts."""
    from data_ingestion.models import GreenBond, ClimateHazardData
    from greenwash_detector.models import GreenwashFlag
    from pricing_analysis.models import PricingGap

    total = GreenBond.objects.count()
    return {
        "source_trust": SOURCE_TRUST,
        "evidence_hierarchy": EVIDENCE_HIERARCHY,
        "missing_data_policies": MISSING_DATA_POLICIES,
        "dataset_status": {
            "total_bonds": total,
            "precise_locations": GreenBond.objects.filter(location_confidence="precise").count(),
            "city_level_locations": GreenBond.objects.filter(location_confidence="city").count(),
            "country_level_locations": GreenBond.objects.filter(location_confidence="country").count(),
            "hazard_records": ClimateHazardData.objects.count(),
            "satellite_unverifiable": GreenwashFlag.objects.filter(verification_status="unverifiable").count(),
            "estimated_spreads": PricingGap.objects.filter(is_live=False).count(),
            "live_spreads": PricingGap.objects.filter(is_live=True).count(),
            "pricing_conflicts": PricingGap.objects.filter(is_mispriced=True).count(),
            "issuer_satellite_conflicts": GreenwashFlag.objects.filter(is_inconsistent=True).count(),
        },
    }
