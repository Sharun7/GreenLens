# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_scoring/ml_engine.py — XGBoost PCRS model training, SHAP explanation,
and PCRSPredictor inference class.

Training:
    python manage.py train_pcrs_model

Inference (programmatic):
    predictor = PCRSPredictor()
    result = predictor.predict(bond_pk)
"""
import logging
import os
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import shap
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit

from risk_scoring.feature_pipeline import FeatureEngineeringPipeline

logger = logging.getLogger("greenlens.ml_engine")

# ── Model artefact paths ───────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)

MODEL_PATH  = MODEL_DIR / "pcrs_model_v1.pkl"
SCALER_PATH = MODEL_DIR / "pcrs_scaler_v1.pkl"
SHAP_PLOT   = MODEL_DIR / "shap_summary.png"

MODEL_VERSION = "v1.0.0"
VERSIONED_MODEL_DIR = MODEL_DIR / "pcrs_v2"


# ── Training ──────────────────────────────────────────────────────────────────

def train_pcrs_model(bond_ids: Optional[list[int]] = None, output_dir=None, make_plot=True, allow_demo=False) -> dict:
    """
    Full training pipeline:
    1. Unscaled feature engineering
    2. Country-held-out split; scaler fitted on training rows only
    3. XGBoost fit with early stopping
    4. Evaluation metrics
    5. SHAP summary plot
    6. Persist model + scaler

    Returns a metrics dict.
    """
    logger.info("Starting PCRS model training …")

    # ── 1. Feature engineering ────────────────────────────────────────────────
    pipeline = FeatureEngineeringPipeline()
    X, y, feature_names = pipeline.prepare_training_data(bond_ids)
    logger.info("Training data: %d samples × %d features", *X.shape)
    input_status = dict(Counter(
        item.get("primary_status", "unknown")
        for item in getattr(pipeline, "input_provenance_", {}).values()
    )) or {"unknown": len(X)}
    if input_status.get("demo", 0) and not allow_demo:
        raise ValueError("Demo hazard inputs detected. Use --allow-demo only for an explicitly labelled research run.")

    if len(X) < 20:
        raise ValueError(
            f"Too few training samples ({len(X)}). "
            "Load more bond data before training."
        )

    groups = np.asarray(pipeline._training_groups)
    if len(set(groups)) < 4:
        raise ValueError("Country-held-out training requires at least four distinct country groups")
    training, remaining = next(GroupShuffleSplit(
        n_splits=1, test_size=0.30, random_state=42,
    ).split(X, y, groups=groups))
    validation_relative, testing_relative = next(GroupShuffleSplit(
        n_splits=1, test_size=0.50, random_state=42,
    ).split(X[remaining], y[remaining], groups=groups[remaining]))
    validation, testing = remaining[validation_relative], remaining[testing_relative]
    if min(len(training), len(validation), len(testing)) < 2:
        raise ValueError("Each country-held-out split requires at least two samples")
    X_train = pipeline.scale_features(X[training], fit=True)
    X_val = pipeline.scale_features(X[validation])
    X_test = pipeline.scale_features(X[testing])
    y_train, y_val, y_test = y[training], y[validation], y[testing]
    logger.info(
        "Split: train=%d  val=%d  test=%d", len(X_train), len(X_val), len(X_test)
    )

    # ── 3. XGBoost model ──────────────────────────────────────────────────────
    model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=2,
        eval_metric="rmse",
        early_stopping_rounds=50,
        verbosity=0,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )
    logger.info(
        "Training complete. Best iteration: %d", model.best_iteration
    )

    # ── 4. Evaluation ─────────────────────────────────────────────────────────
    y_pred = model.predict(X_test)
    r2   = float(r2_score(y_test, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    mae  = float(mean_absolute_error(y_test, y_pred))

    metrics = {
        "r2":   round(r2, 4),
        "rmse": round(rmse, 4),
        "mae":  round(mae, 4),
        "n_train": len(X_train),
        "n_val":   len(X_val),
        "n_test":  len(X_test),
        "best_iteration": int(model.best_iteration),
        "model_version": "v2.0.0-proxy",
        "target_kind": "hazard_derived_proxy",
        "validation_kind": "country_held_out_proxy_fit_not_loss_backtest",
        "scaler_fit": "training_split_only",
        "feature_names": feature_names,
        "mean_abs_shap": dict(zip(feature_names, np.abs(shap.TreeExplainer(model).shap_values(X_test)).mean(axis=0).astype(float).tolist())),
        "input_status_counts": input_status,
        "hyperparameters": {name: model.get_params()[name] for name in (
            "n_estimators", "max_depth", "learning_rate", "subsample", "colsample_bytree",
            "reg_alpha", "reg_lambda", "random_state", "n_jobs", "early_stopping_rounds",
        )},
        "countries": {
            "train": sorted(set(groups[training])),
            "validation": sorted(set(groups[validation])),
            "test": sorted(set(groups[testing])),
        },
    }
    logger.info("Test metrics: R²=%.4f  RMSE=%.4f  MAE=%.4f", r2, rmse, mae)

    artifact_dir = Path(output_dir) if output_dir is not None else VERSIONED_MODEL_DIR
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if make_plot:
        _save_shap_plot(model, X_test, feature_names, artifact_dir / "shap_summary.png")
    model_path, scaler_path = artifact_dir / "model.pkl", artifact_dir / "scaler.pkl"
    joblib.dump(model, model_path)
    joblib.dump(pipeline.scaler, scaler_path)
    from risk_scoring.geography import coastline_status

    metadata = {
        **metrics, "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_schema": "pcrs-20-v2",
        "coastline": coastline_status(),
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "scaler_sha256": hashlib.sha256(scaler_path.read_bytes()).hexdigest(),
        "warning": "Proxy fit does not establish loss prediction or independent extended-risk effects.",
    }
    temporary = artifact_dir / "metadata.json.part"
    temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    temporary.replace(artifact_dir / "metadata.json")
    return {**metrics, "artifact_dir": str(artifact_dir)}


def _save_shap_plot(model, X_test, feature_names, destination):
    try:
        import matplotlib
        matplotlib.use("Agg")   # non-interactive backend
        import matplotlib.pyplot as plt

        explainer   = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_test)

        plt.figure(figsize=(10, 6))
        shap.summary_plot(
            shap_values, X_test,
            feature_names=feature_names,
            show=False, plot_type="bar",
        )
        plt.tight_layout()
        plt.savefig(str(destination), dpi=120)
        plt.close("all")
        logger.info("SHAP summary plot saved → %s", destination)
    except Exception as exc:
        logger.warning("SHAP plot failed (non-fatal): %s", exc)

# ── SHAP explanation ──────────────────────────────────────────────────────────

def explain_prediction(bond_pk: int, model=None, pipeline=None) -> dict[str, float]:
    """
    Returns {feature_name: shap_value} for a single bond prediction,
    sorted by absolute impact (largest first).
    """
    if model is None or pipeline is None:
        predictor = PCRSPredictor()
        model = predictor.model if model is None else model
        pipeline = predictor.pipeline if pipeline is None else pipeline

    X, _, feature_names = pipeline.transform_single(bond_pk)

    explainer   = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)

    shap_dict = {
        name: float(val)
        for name, val in zip(feature_names, shap_values[0])
    }
    return dict(
        sorted(shap_dict.items(), key=lambda kv: abs(kv[1]), reverse=True)
    )


# ── PCRSPredictor ─────────────────────────────────────────────────────────────

class PCRSPredictor:
    """
    Loads trained PCRS model + scaler and performs inference for a single bond.

    Usage:
        predictor = PCRSPredictor()
        result = predictor.predict(bond_pk=42)
        # → {"score": 67.3, "risk_band": "High", "shap_values": {...}, ...}
    """

    def __init__(self, artifact_dir=None):
        directory = Path(artifact_dir) if artifact_dir is not None else VERSIONED_MODEL_DIR
        metadata_path = directory / "metadata.json"
        self.metadata = {}
        if artifact_dir is not None or metadata_path.is_file():
            self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            model_path, scaler_path = directory / "model.pkl", directory / "scaler.pkl"
            for path, key in ((model_path, "model_sha256"), (scaler_path, "scaler_sha256")):
                if hashlib.sha256(path.read_bytes()).hexdigest() != self.metadata.get(key):
                    raise ValueError("PCRS model/scaler checksum mismatch; publish a complete artifact set")
            if self.metadata.get("feature_names") != FeatureEngineeringPipeline().all_feature_cols:
                raise ValueError("PCRS artifact feature schema does not match the installed pipeline")
            from risk_scoring.geography import coastline_status

            expected_geography = self.metadata.get("coastline", {}).get("method")
            if expected_geography and expected_geography != coastline_status()["method"]:
                raise ValueError("PCRS coastline preprocessing differs from training. Prepare the matching coastline dataset or retrain.")
        else:
            model_path, scaler_path = MODEL_PATH, SCALER_PATH
            logger.warning("Using legacy PCRS artifacts without a versioned training manifest")
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {model_path}. "
                "Run: python manage.py train_pcrs_model"
            )
        self.model   = joblib.load(model_path)
        self.scaler  = joblib.load(scaler_path)
        self.artifact_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
        self.model_version = self.metadata.get("model_version", MODEL_VERSION)
        if self.model.n_features_in_ != len(FeatureEngineeringPipeline().all_feature_cols):
            raise ValueError("PCRS model input dimension does not match the feature pipeline")

        from sklearn.preprocessing import MinMaxScaler
        self.pipeline = FeatureEngineeringPipeline(scaler=self.scaler)
        self.pipeline._fitted = True

        self._explainer = shap.TreeExplainer(self.model)
        logger.info("PCRSPredictor loaded model version %s", self.model_version)

    def predict(self, bond_pk: int) -> dict:
        """
        Run PCRS inference for a single bond, persist the PCRScore record,
        and return the full result dict.

        Returns:
            {
                "bond_pk":      int,
                "score":        float (0–100),
                "risk_band":    str,
                "shap_values":  dict[str, float],
                "flood_contribution":   float,
                "heat_contribution":    float,
                "drought_contribution": float,
                "model_version": str,
            }
        """
        from data_ingestion.models import GreenBond
        from risk_scoring.models import PCRScore

        bond = GreenBond.objects.get(pk=bond_pk)

        # Feature transform
        X, _, feature_names = self.pipeline.transform_single(bond_pk)

        # Predict
        raw_score = float(self.model.predict(X)[0])
        if not np.isfinite(raw_score):
            raise ValueError("PCRS model produced a non-finite prediction")
        score     = max(0.0, min(100.0, raw_score))

        # SHAP
        shap_vals = self._explainer.shap_values(X)[0]
        shap_dict = {
            name: round(float(val), 4)
            for name, val in zip(feature_names, shap_vals)
        }

        # Extract named SHAP contributions
        flood_shap   = shap_dict.get("flood_risk_index", 0.0)
        heat_shap    = shap_dict.get("heat_stress_index", 0.0)
        drought_shap = shap_dict.get("drought_severity", 0.0)
        from risk_scoring.geography import coastline_status

        feature_metadata = {
            "features": self.pipeline.feature_values_[bond_pk],
            "provenance": self.pipeline.input_provenance_[bond_pk],
            "coastline": coastline_status(),
            "base_value": float(np.asarray(self._explainer.expected_value).reshape(-1)[0]),
            "raw_score": raw_score,
            "clipping_adjustment": score - raw_score,
            "target_kind": "hazard_derived_proxy",
            "artifact_status": "manifest_checked" if self.metadata else "legacy_unverified",
            "model_sha256": self.artifact_sha256,
        }

        # Persist to DB (update latest score for this bond)
        score_obj, _ = PCRScore.objects.update_or_create(
            bond=bond,
            model_version=self.model_version,
            defaults={
                "score":                round(score, 2),
                "flood_contribution":   round(flood_shap, 4),
                "heat_contribution":    round(heat_shap, 4),
                "drought_contribution": round(drought_shap, 4),
                "shap_values":          shap_dict,
                "feature_metadata":     feature_metadata,
            },
        )

        risk_band = _risk_band(score)
        logger.info(
            "Predicted bond %s: score=%.1f [%s]", bond.bond_id, score, risk_band
        )

        return {
            "bond_pk":              bond_pk,
            "bond_id":              bond.bond_id,
            "score":                round(score, 2),
            "risk_band":            risk_band,
            "risk_label":           score_obj.three_band_label,
            "confidence_interval":  score_obj.confidence_interval,
            "main_risk_driver":     score_obj.main_risk_driver,
            "shap_values":          shap_dict,
            "flood_contribution":   round(flood_shap, 4),
            "heat_contribution":    round(heat_shap, 4),
            "drought_contribution": round(drought_shap, 4),
            "model_version":        self.model_version,
            "feature_metadata":     feature_metadata,
        }

    def predict_batch(self, bond_pks: list[int]) -> list[dict]:
        """Predict for a list of bond PKs and return list of result dicts."""
        results = []
        for pk in bond_pks:
            try:
                results.append(self.predict(pk))
            except Exception as exc:
                logger.error("Predict failed for bond pk=%d: %s", pk, exc)
        return results


def _risk_band(score: float) -> str:
    if score < 20:   return "Low"
    if score < 45:   return "Medium-Low"
    if score < 65:   return "Medium-High"
    if score < 85:   return "High"
    return "Extreme"
