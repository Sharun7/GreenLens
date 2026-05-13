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
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import shap
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

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


# ── Training ──────────────────────────────────────────────────────────────────

def train_pcrs_model(bond_ids: Optional[list[int]] = None) -> dict:
    """
    Full training pipeline:
    1. Feature engineering (fit+transform)
    2. 70/15/15 stratified split
    3. XGBoost fit with early stopping
    4. Evaluation metrics
    5. SHAP summary plot
    6. Persist model + scaler

    Returns a metrics dict.
    """
    logger.info("Starting PCRS model training …")

    # ── 1. Feature engineering ────────────────────────────────────────────────
    pipeline = FeatureEngineeringPipeline()
    X, y, feature_names = pipeline.fit_transform(bond_ids)
    logger.info("Training data: %d samples × %d features", *X.shape)

    if len(X) < 20:
        raise ValueError(
            f"Too few training samples ({len(X)}). "
            "Load more bond data before training."
        )

    # ── 2. Stratified split (70 / 15 / 15) ───────────────────────────────────
    # Stratify by PCRS quintile so each split has similar score distribution
    y_strat = np.digitize(y, bins=np.percentile(y, [20, 40, 60, 80]))

    X_train, X_tmp, y_train, y_tmp, s_train, s_tmp = train_test_split(
        X, y, y_strat, test_size=0.30, random_state=42, stratify=y_strat
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_tmp, y_tmp, test_size=0.50, random_state=42
    )
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
        n_jobs=-1,
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
        "model_version": MODEL_VERSION,
    }
    logger.info("Test metrics: R²=%.4f  RMSE=%.4f  MAE=%.4f", r2, rmse, mae)

    # ── 5. SHAP summary plot ──────────────────────────────────────────────────
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
        plt.savefig(str(SHAP_PLOT), dpi=120)
        plt.close("all")
        logger.info("SHAP summary plot saved → %s", SHAP_PLOT)
    except Exception as exc:
        logger.warning("SHAP plot failed (non-fatal): %s", exc)

    # ── 6. Persist artefacts ──────────────────────────────────────────────────
    joblib.dump(model,           MODEL_PATH)
    joblib.dump(pipeline.scaler, SCALER_PATH)
    logger.info("Model saved → %s", MODEL_PATH)
    logger.info("Scaler saved → %s", SCALER_PATH)

    return metrics


# ── SHAP explanation ──────────────────────────────────────────────────────────

def explain_prediction(bond_pk: int, model=None, pipeline=None) -> dict[str, float]:
    """
    Returns {feature_name: shap_value} for a single bond prediction,
    sorted by absolute impact (largest first).
    """
    if model is None:
        model = joblib.load(MODEL_PATH)
    if pipeline is None:
        from sklearn.preprocessing import MinMaxScaler
        scaler = joblib.load(SCALER_PATH)
        pipeline = FeatureEngineeringPipeline(scaler=scaler)
        pipeline._fitted = True

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

    def __init__(self):
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model not found at {MODEL_PATH}. "
                "Run: python manage.py train_pcrs_model"
            )
        self.model   = joblib.load(MODEL_PATH)
        self.scaler  = joblib.load(SCALER_PATH)

        from sklearn.preprocessing import MinMaxScaler
        self.pipeline = FeatureEngineeringPipeline(scaler=self.scaler)
        self.pipeline._fitted = True

        self._explainer = shap.TreeExplainer(self.model)
        logger.info("PCRSPredictor loaded model version %s", MODEL_VERSION)

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

        # Persist to DB (update latest score for this bond)
        score_obj, _ = PCRScore.objects.update_or_create(
            bond=bond,
            model_version=MODEL_VERSION,
            defaults={
                "score":                round(score, 2),
                "flood_contribution":   round(flood_shap, 4),
                "heat_contribution":    round(heat_shap, 4),
                "drought_contribution": round(drought_shap, 4),
                "shap_values":          shap_dict,
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
            "model_version":        MODEL_VERSION,
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
