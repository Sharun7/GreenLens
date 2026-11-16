"""Compare exported encoder/head predictions on one frozen, independently labeled test set."""

import hashlib
import json
import math

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error

from .pilot_evaluation import validate_rows


def benchmark_encoders(rows, evaluation, bundles):
    validate_rows(rows)
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()
    if evaluation.get("dataset_sha256") != digest:
        raise ValueError("Labels or features changed after the split was frozen. Re-evaluate before benchmarking.")
    split = evaluation["split_project_ids"]
    test_ids = split["temporal_test"] + split["geographic_test"]
    if not test_ids or len(test_ids) != len(set(test_ids)):
        raise ValueError("Disjoint frozen test IDs are required.")
    lookup = {row["project_id"]: row for row in rows}
    if not set(test_ids) <= set(lookup):
        raise ValueError("The frozen test set does not match the label dataset.")
    names = {bundle["encoder"] for bundle in bundles}
    if "resnet18" not in names or not names.intersection({"prithvi", "satmae"}) or len(names) != len(bundles):
        raise ValueError("Provide a unique ResNet-18 baseline and at least one Prithvi or SatMAE prediction bundle.")
    metrics = {}
    for bundle in bundles:
        if bundle["encoder"] not in {"resnet18", "prithvi", "satmae"}:
            raise ValueError("Unsupported encoder bundle.")
        for field in ("weights_sha256", "preprocessing_sha256"):
            digest = bundle.get(field, "")
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ValueError("Checkpoint and preprocessing SHA-256 identifiers are required.")
        if (not bundle.get("checkpoint_url", "").startswith("https://")
                or not bundle.get("license_url", "").startswith("https://")
                or not bundle.get("input_bands") or not bundle.get("head_recipe")
                or set(bundle.get("training_project_ids", [])) != set(split["train"])):
            raise ValueError("Each bundle needs licensed checkpoint provenance, spectral bands, a head recipe, and exactly the frozen training IDs.")
        predictions = bundle["predictions"]
        if set(predictions) != set(test_ids):
            raise ValueError("Every encoder must predict exactly the same untouched test projects.")
        predicted = [predictions[identifier] for identifier in test_ids]
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1 for value in predicted):
            raise ValueError("Encoder/head predictions must be finite damage fractions.")
        actual = [lookup[identifier]["damage_fraction"] for identifier in test_ids]
        metrics[bundle["encoder"]] = {
            "n": len(test_ids), "mae": float(mean_absolute_error(actual, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
            "weights_sha256": bundle["weights_sha256"], "preprocessing_sha256": bundle["preprocessing_sha256"],
            "checkpoint_url": bundle["checkpoint_url"], "input_bands": bundle["input_bands"], "head_recipe": bundle["head_recipe"],
        }
    return {"status": "exported_predictions_evaluated", "target": "independently observed damage fraction",
            "dataset_sha256": evaluation["dataset_sha256"], "test_project_ids": test_ids, "encoders": metrics,
            "limitation": "This evaluates supplied prediction artifacts, not execution or reproduction of encoder training. No foundation-model accuracy claim is made without real labels and artifacts."}