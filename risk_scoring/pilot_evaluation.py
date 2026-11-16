"""Independent-outcome XGBoost evaluation, isolated from production proxy artifacts."""

import hashlib
import json
import math
from datetime import date

import numpy as np
from sklearn.dummy import DummyRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor


FEATURES = ("s2_ndvi", "s2_ndmi", "s1_vv_db", "s1_vh_db", "elevation_m", "slope_deg", "capacity_mw")


def _date(value):
    return value if isinstance(value, date) else date.fromisoformat(value)


def validate_rows(rows):
    identifiers = set()
    for row in rows:
        identifier = row["project_id"]
        if identifier in identifiers:
            raise ValueError("The first pilot evaluation requires one outcome per project; repeated projects could leak across splits.")
        identifiers.add(identifier)
        if not (row.get("boundary_reviewed") and row.get("label_reviewed") and row.get("independently_observed")):
            raise ValueError(f"{identifier}: reviewed boundaries and independently observed, reviewed labels are required.")
        if not row.get("county") or not row.get("label_source_url", "").startswith("https://"):
            raise ValueError(f"{identifier}: a county and HTTPS independent-label source are required.")
        if not _date(row["feature_date"]) < _date(row["outcome_date"]) <= _date(row["label_available_on"]):
            raise ValueError(f"{identifier}: invalid feature/outcome/label-availability chronology.")
        target = row["damage_fraction"]
        if isinstance(target, bool) or not isinstance(target, (float, int)) or not math.isfinite(target) or not 0 <= target <= 1:
            raise ValueError(f"{identifier}: damage_fraction must be an independently observed fraction in [0, 1].")
        if any(word in row.get("label_method", "").lower() for word in ("synthetic", "proxy", "prediction", "simulated")):
            raise ValueError(f"{identifier}: proxy or synthetic targets cannot be used for independent evaluation.")
        if set(row["features"]) != set(FEATURES):
            raise ValueError(f"{identifier}: use exactly the documented baseline feature schema.")
        for name in FEATURES:
            value = row["features"][name]
            provenance = row.get("feature_provenance", {}).get(name, {})
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError(f"{identifier}: {name} is not a finite measurement.")
            if (provenance.get("kind") not in ("observed", "official_measurement")
                    or not provenance.get("source_url", "").startswith("https://")
                    or not provenance.get("available_on")
                    or _date(provenance["available_on"]) > _date(row["feature_date"])):
                raise ValueError(f"{identifier}: {name} lacks known-at-prediction-time measured provenance.")
    return rows


def split_rows(rows, train_before, calibrate_before, held_out_counties):
    if not rows:
        raise ValueError("No independently reviewed outcomes are available; measured satellite inputs cannot substitute for outcome labels.")
    validate_rows(rows)
    train_before, calibrate_before = _date(train_before), _date(calibrate_before)
    if not train_before < calibrate_before or not held_out_counties:
        raise ValueError("Specify ordered train/calibration cutoffs and held-out counties before evaluating.")
    splits = {"train": [], "calibration": [], "temporal_test": [], "geographic_test": [], "excluded": []}
    for row in rows:
        feature_date, available = _date(row["feature_date"]), _date(row["label_available_on"])
        if row["county"] in held_out_counties:
            key = "geographic_test" if feature_date >= calibrate_before else "excluded"
        elif feature_date < train_before and available < train_before:
            key = "train"
        elif train_before <= feature_date < calibrate_before and available < calibrate_before:
            key = "calibration"
        elif feature_date >= calibrate_before:
            key = "temporal_test"
        else:
            key = "excluded"
        splits[key].append(row)
    if len(splits["train"]) < 10 or not splits["temporal_test"] or not splits["geographic_test"]:
        raise ValueError("Need at least ten training projects plus nonempty later-time and held-out-county test sets.")
    return splits


def conformal_radius(actual, predicted, alpha=0.1):
    if not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be finite and strictly between zero and one.")
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if actual.shape != predicted.shape or actual.ndim != 1 or not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Calibration requires aligned finite one-dimensional observations and predictions.")
    rank = math.ceil((len(actual) + 1) * (1 - alpha))
    if not len(actual) or rank > len(actual):
        raise ValueError("Calibration sample too small for a finite interval at this requested coverage. Collect more independent labels.")
    return float(np.sort(np.abs(actual - predicted))[rank - 1])


def interval_metrics(rows, predicted, radius):
    actual = np.asarray([row["damage_fraction"] for row in rows])
    predicted = np.asarray(predicted)
    lower, upper = np.maximum(0, predicted - radius), np.minimum(1, predicted + radius)
    covered = (actual >= lower) & (actual <= upper)
    regional = {}
    for county in sorted({row["county"] for row in rows}):
        indices = [index for index, row in enumerate(rows) if row["county"] == county]
        regional[county] = {
            "n": len(indices), "empirical_coverage": float(covered[indices].mean()),
            "mean_width": float((upper - lower)[indices].mean()),
            "assessment": "insufficient sample for regional assurance" if len(indices) < 20 else "empirical evaluation; not a guarantee under shift",
        }
    return {
        "n": len(rows), "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        "empirical_coverage": float(covered.mean()), "mean_width": float((upper - lower).mean()),
        "counties": regional,
    }


def evaluate_pilot(rows, train_before, calibrate_before, held_out_counties, alpha=0.1):
    splits = split_rows(rows, train_before, calibrate_before, held_out_counties)
    if not splits["calibration"]:
        raise ValueError("An untouched calibration set is required; test labels cannot calibrate intervals.")

    def matrix(part):
        return np.asarray([[row["features"][name] for name in FEATURES] for row in part], dtype=float)

    train = splits["train"]
    targets = np.asarray([row["damage_fraction"] for row in train])
    model = XGBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42, n_jobs=1)
    model.fit(matrix(train), targets)
    baseline = DummyRegressor(strategy="mean").fit(matrix(train), targets)
    calibration = splits["calibration"]
    calibrated_predictions = np.clip(model.predict(matrix(calibration)), 0, 1)
    radius = conformal_radius([row["damage_fraction"] for row in calibration], calibrated_predictions, alpha)
    report = {
        "status": "evaluated_not_promoted", "target": "independently observed damage_fraction",
        "model": "XGBoost baseline", "features": list(FEATURES), "alpha": alpha,
        "interval_method": "split conformal absolute residuals; finite-sample order statistic",
        "conformal_radius": radius, "train_before": str(train_before), "calibrate_before": str(calibrate_before),
        "held_out_counties": sorted(held_out_counties),
        "split_project_ids": {name: [row["project_id"] for row in part] for name, part in splits.items()},
        "dataset_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest(),
        "limitations": [
            "No automatic replacement of the production PCRS proxy model.",
            "Exchangeability is not guaranteed across geography or time; coverage must be measured.",
            "Damage-fraction evaluation is not a credit-default or financial-return validation.",
            "Features and labels require independently documented review; source provenance alone does not eliminate bias.",
        ],
    }
    for name in ("temporal_test", "geographic_test"):
        part = splits[name]
        predicted = np.clip(model.predict(matrix(part)), 0, 1)
        report[name] = interval_metrics(part, predicted, radius)
        report[name]["mean_baseline_mae"] = float(mean_absolute_error(
            [row["damage_fraction"] for row in part], baseline.predict(matrix(part)),
        ))
    return model, report


def outcome_row(outcome):
    project = outcome.project
    return {
            "project_id": project.source_id, "county": project.source_metadata.get("p_county"),
            "boundary_sha256": project.boundary_sha256,
            "boundary_reviewed": project.review_status == "approved" and bool(project.reviewed_by_id and project.reviewed_at),
            "label_reviewed": bool(outcome.reviewed_by_id and outcome.reviewed_at and outcome.notes),
            "independently_observed": outcome.independently_observed,
            "feature_date": outcome.feature_date.isoformat(), "outcome_date": outcome.outcome_date.isoformat(),
            "label_available_on": outcome.label_available_on.isoformat(), "damage_fraction": outcome.damage_fraction,
            "label_source_url": outcome.label_source_url, "label_method": outcome.label_method,
            "features": outcome.features, "feature_provenance": outcome.feature_provenance,
        }


def reviewed_outcome_rows():
    from data_ingestion.models import PilotOutcome

    return [outcome_row(outcome) for outcome in PilotOutcome.objects.select_related("project").order_by("pk")]