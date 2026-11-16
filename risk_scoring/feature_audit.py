"""Cheap, database-backed feature coverage; never fetches remote data on page load."""

import hashlib
import json
import math
from collections import Counter

from django.db.models import OuterRef, Subquery

from data_ingestion.extended_risk_fetcher import CARBON_INTENSITY, POLICY_RISK, TRANSITION_RISK
from data_ingestion.models import ClimateHazardData, GreenBond
from risk_scoring.feature_pipeline import CATEGORY_VULNERABILITY, HAZARD_WEIGHTS, FeatureEngineeringPipeline
from risk_scoring.geography import coastline_status
from risk_scoring.models import PCRScore


FEATURE_GROUPS = [
    ("Primary hazard inputs", [
        ("flood_risk_index", "Flood exposure", "Stored index in [0,1]; country fallback is a proxy, not GPS-level observation."),
        ("heat_stress_index", "Heat stress", "Stored index in [0,1]; source and spatial precision must be checked."),
        ("drought_severity", "Drought severity", "clip(-SPEI / 3, 0, 1); SPEI is the raw input, not the final severity feature."),
    ]),
    ("Extended country context", [
        ("carbon_intensity_score", "Carbon intensity context", "Recorded value or embedded country proxy; no verified live EDGAR import is established."),
        ("policy_risk_score", "Governance / policy context", "Recorded value or embedded governance proxy; it is one feature, not separate country and policy models."),
        ("transition_risk_score", "Transition context", "Recorded value or embedded country proxy; not a live, audited CAT/IEA feed."),
    ]),
    ("Engineered features", [
        ("composite_hazard", "Composite hazard", "clip(0.40 × flood + 0.35 × heat + 0.25 × drought severity, 0, 1)."),
        ("is_coastal", "Coastal exposure flag", "1 within 200 km of the installed coastline geometry, otherwise 0; legacy approximation if data is absent."),
        ("climate_trend", "Climate trend proxy", "Static country ordinal 1–5; not a downloaded, location-specific CMIP6 projection."),
        ("maturity_exposure", "Maturity exposure", "ln(maturity years) × composite hazard; maturity is not a separate direct feature."),
        ("category_vulnerability", "Category vulnerability", "Configured category coefficient; a research assumption, not a calibrated loss probability."),
        ("hazard_x_vulnerability", "Hazard × vulnerability", "Composite hazard × category vulnerability."),
        ("coastal_flood", "Coastal flood interaction", "Coastal exposure flag × flood exposure."),
    ]),
    ("Project-category encoding", [
        ("cat_solar", "Solar", "One-hot category indicator."),
        ("cat_wind", "Wind", "One-hot category indicator."),
        ("cat_water", "Water", "One-hot category indicator."),
        ("cat_transport", "Transport", "One-hot category indicator."),
        ("cat_building", "Building", "One-hot category indicator."),
        ("cat_reforestation", "Reforestation", "One-hot category indicator."),
        ("cat_other", "Other / unknown", "Fallback category; the seven category indicators sum to one."),
    ]),
]


def _latest(model, timestamp):
    selected = model.objects.filter(bond_id=OuterRef("bond_id")).order_by(
        "-" + timestamp, "-pk",
    ).values("pk")[:1]
    return model.objects.filter(pk=Subquery(selected))


def active_manifest():
    from risk_scoring.ml_engine import VERSIONED_MODEL_DIR

    path = VERSIONED_MODEL_DIR / "metadata.json"
    if not path.is_file():
        return {"status": "legacy", "message": "Legacy artifacts have no saved training/source manifest. Retrain to produce an auditable model."}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for filename, key in (("model.pkl", "model_sha256"), ("scaler.pkl", "scaler_sha256")):
            if hashlib.sha256((path.parent / filename).read_bytes()).hexdigest() != payload[key]:
                raise ValueError
        return {"status": "manifest_checked", "message": "Artifact checksums match the training manifest.", **payload}
    except (ValueError, KeyError, OSError):
        return {"status": "invalid", "message": "The active artifact set is incomplete or its checksums do not match."}


def build_pcrs_feature_audit():
    names = FeatureEngineeringPipeline().all_feature_cols
    hazards = {row.bond_id: row for row in _latest(ClimateHazardData, "data_date")}
    scores = {row.bond_id: row for row in _latest(PCRScore, "scored_at")}
    source_counts = Counter()
    extended_counts = {field: Counter() for field in (
        "carbon_intensity_score", "policy_risk_score", "transition_risk_score",
    )}
    values = {name: set() for name in names}
    available = 0
    sample = None
    total = 0
    precise = 0
    for bond in GreenBond.objects.only("pk", "country", "location_confidence").iterator(chunk_size=200):
        total += 1
        precise += bond.location_confidence == "precise"
        hazard = hazards.get(bond.pk)
        iso3 = FeatureEngineeringPipeline._iso3_from_country(bond.country)
        if hazard is None:
            source_counts["missing"] += 1
        else:
            metadata = hazard.raw_metadata if isinstance(hazard.raw_metadata, dict) else {}
            demo = metadata.get("source") == "deployment_bootstrap" or metadata.get("method") == "synthetic"
            source_counts["demo" if demo else "recorded_unverified"] += 1
            inputs = [hazard.flood_risk_index, hazard.heat_stress_index, hazard.drought_spei]
            if (all(value is not None and math.isfinite(float(value)) for value in inputs)
                    and all(0 <= float(value) <= 1 for value in inputs[:2])):
                available += 1
        for field, table in (("carbon_intensity_score", CARBON_INTENSITY),
                             ("policy_risk_score", POLICY_RISK),
                             ("transition_risk_score", TRANSITION_RISK)):
            recorded = hazard is not None and getattr(hazard, field) is not None
            if recorded:
                value = getattr(hazard, field)
                status = "recorded_unverified" if math.isfinite(float(value)) and 0 <= float(value) <= 1 else "invalid"
            else:
                status = "country_proxy" if iso3 in table else "global_default"
            extended_counts[field][status] += 1
        score = scores.get(bond.pk)
        snapshot = score.feature_metadata.get("features", {}) if score and isinstance(score.feature_metadata, dict) else {}
        if sample is None and all(name in snapshot for name in names):
            labels = {name: label for _title, definitions in FEATURE_GROUPS for name, label, _definition in definitions}
            sample = {
                "bond_id": bond.bond_id, "score": score.score, "model_version": score.model_version,
                "primary_status": score.feature_metadata.get("provenance", {}).get("primary_status", "unknown"),
                "base_value": score.feature_metadata.get("base_value"),
                "raw_score": score.feature_metadata.get("raw_score"),
                "rows": [{"name": name, "label": labels[name], "value": snapshot[name],
                          "shap": score.shap_values.get(name)} for name in names],
            }
        for name in names:
            value = snapshot.get(name)
            if isinstance(value, (float, int)) and math.isfinite(value):
                values[name].add(float(value))
    manifest = active_manifest()
    groups = []
    for title, features in FEATURE_GROUPS:
        groups.append({"title": title, "features": [
            {"name": name, "label": label, "definition": definition,
             "mean_abs_shap": manifest.get("mean_abs_shap", {}).get(name),
             "unique_audited_values": len(values[name]),
             "variation": "Not audited" if not values[name] else ("Constant in audited inputs" if len(values[name]) == 1 else "Varies in audited inputs")}
            for name, label, definition in features
        ]})
    coverage = [{
        "dimension": "Physical hazards", "available": available,
        "basis": f"{source_counts['demo']} demo; {source_counts['recorded_unverified']} recorded/unverified; {source_counts['missing']} missing",
        "assessment": "Input availability is not source validation",
    }]
    for field, label in (("carbon_intensity_score", "Carbon context"),
                         ("policy_risk_score", "Governance / policy context"),
                         ("transition_risk_score", "Transition context")):
        counts = extended_counts[field]
        coverage.append({
            "dimension": label,
            "available": counts["recorded_unverified"] + counts["country_proxy"],
            "basis": f"{counts['recorded_unverified']} recorded/unverified; {counts['country_proxy']} country proxies; {counts['global_default']} global defaults; {counts['invalid']} invalid",
            "assessment": "Not an independently verified live feed",
        })
    return {
        "feature_count": len(names), "groups": groups, "coverage": coverage,
        "total_bonds": total, "precise_locations": precise,
        "coastline": coastline_status(), "model": manifest,
        "sample": sample,
        "target_formula": "100 × composite_hazard",
        "assumptions": {"hazard_weights": HAZARD_WEIGHTS, "category_vulnerability": CATEGORY_VULNERABILITY},
        "independently_validated_loss_model": False,
        "limitation": "The target is derived from input hazards, including composite_hazard itself. Proxy-fit metrics do not validate flood/default prediction or independent carbon/policy/transition effects.",
    }