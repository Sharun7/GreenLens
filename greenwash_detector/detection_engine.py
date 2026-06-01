# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
greenwash_detector/detection_engine.py — Greenwash Detection Engine.

Strategy:
  1. Attempt Google Earth Engine (GEE) NDVI time-series analysis
  2. Fall back to rule-based synthetic classifier using project metadata

NDVI Logic:
  - Compute mean NDVI in a 5 km radius around the project site
  - Compare 2-year pre-project baseline vs 2-year post-project window
  - Large negative NDVI change inconsistent with "reforestation" / "green" claims

Rule-Based Fallback:
  - Uses project_category, country, and climate hazard data
  - Applies heuristics for common greenwashing patterns (e.g. solar farm
    with high NDVI → land-use conflict; reforestation with negative NDVI)
"""
import logging
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from data_ingestion.models import GreenBond
from greenwash_detector.satellite_verifier import SatelliteVerifier, get_dynamic_radius

# SatelliteVerifier is used when GEE is available (lazy import to avoid
# loading earthengine-api at startup when it may not be needed).
_verifiers = {}


def _get_verifier(skip_gee: bool = False):
    if skip_gee not in _verifiers:
        _verifiers[skip_gee] = SatelliteVerifier(skip_gee=skip_gee)
    return _verifiers[skip_gee]

logger = logging.getLogger("greenlens.greenwash_detector")

# ── NDVI thresholds ────────────────────────────────────────────────────────────
# Typical NDVI ranges:
#   < 0.1  : bare soil / urban
#   0.1-0.3: shrubland, grassland
#   0.3-0.5: moderate vegetation / cropland
#   > 0.5  : dense forest / tropical
NDVI_FOREST_MIN = 0.40
NDVI_BARE_SOIL_MAX = 0.15
NDVI_CHANGE_FLAG_THRESHOLD = -0.08   # >8% vegetation loss triggers flag

# ── Category-specific rules ───────────────────────────────────────────────────
# Maps project_category → {min_expected_ndvi_post, flag_if_ndvi_change_below}
CATEGORY_RULES = {
    "reforestation": {"min_post_ndvi": 0.30, "max_ndvi_drop": -0.05, "land_use_expected": ["forest", "shrubland", "grassland"]},
    "solar":         {"min_post_ndvi": -1.0,  "max_ndvi_drop": -0.30, "land_use_expected": ["bare_soil", "urban", "grassland", "shrubland"]},
    "wind":          {"min_post_ndvi": -1.0,  "max_ndvi_drop": -0.20, "land_use_expected": ["bare_soil", "grassland", "shrubland", "cropland"]},
    "water":         {"min_post_ndvi": -1.0,  "max_ndvi_drop": -0.40, "land_use_expected": ["water", "bare_soil", "urban"]},
    "transport":     {"min_post_ndvi": -1.0,  "max_ndvi_drop": -0.50, "land_use_expected": ["urban", "bare_soil", "cropland"]},
    "building":      {"min_post_ndvi": -1.0,  "max_ndvi_drop": -0.50, "land_use_expected": ["urban", "bare_soil"]},
    "other":         {"min_post_ndvi": -1.0,  "max_ndvi_drop": -0.50, "land_use_expected": []},
}


@dataclass
class NDVIResult:
    pre_ndvi: float
    post_ndvi: float
    ndvi_change: float
    pre_date: date
    post_date: date
    land_use: str
    source: str  # "gee" or "synthetic"
    raw_metadata: dict


# ── CNN → bond category mapping ──────────────────────────────────────────────
CNN_CLASS_MAP = {
    "solar_farm": "solar",
    "wind_farm": "wind",
    "forest": "reforestation",
    "water_body": "water",
    "urban": "building",
    "bare_land": "solar",
}


class GreenwashDetector:
    """
    Analyses a GreenBond for potential greenwashing using satellite-derived
    NDVI, land-use data, and a fine-tuned ResNet-18 CNN classifier.

    Usage:
        detector = GreenwashDetector()
        flag = detector.check_bond(bond)
    """

    def __init__(self, skip_gee: bool = False):
        self._verifier = _get_verifier(skip_gee=skip_gee)
        # Keep _ee flag for backward compatibility checks
        self._ee = self._verifier._ee

        # Lazy-load CNN classifier if model file exists
        self._classifier = None
        model_path = Path(__file__).resolve().parent.parent / "models" / "satellite_classifier.pt"
        if model_path.exists():
            try:
                from greenwash_detector.satellite_classifier import SatelliteClassifier
                self._classifier = SatelliteClassifier(skip_gee=skip_gee)
                self._classifier.load_model(str(model_path))
                logger.info("SatelliteClassifier loaded from %s", model_path)
            except Exception as exc:
                logger.warning("Could not load SatelliteClassifier: %s", exc)

    def _load_earth_engine(self):
        """Kept for compatibility — GEE is now managed by SatelliteVerifier."""
        return self._verifier._ee if self._verifier else None

    # ── Public API ─────────────────────────────────────────────────────────────

    def check_bond(self, bond: GreenBond) -> dict:
        """
        Run greenwash check for a single bond.
        Returns a dict suitable for creating/updating a GreenwashFlag record.
        """
        logger.info("Checking bond %s (lat=%.4f lon=%.4f)", bond.bond_id, bond.lat, bond.lon)

        if bond.issuance_date < date(2015, 6, 23):
            logger.info("Bond %s issued before Sentinel-2 launch (2015-06-23). Marking as unverifiable.", bond.bond_id)
            return {
                "bond": bond,
                "verification_status": "unverifiable",
                "ndvi_change": 0.0,
                "satellite_land_use": "unknown",
                "pre_project_image_date": None,
                "post_project_image_date": None,
                "claimed_project_type": bond.project_category,
                "is_inconsistent": False,
                "confidence": 0.0,
                "model_version": "v1.1.0",
                "raw_ee_metadata": {"reason": "pre_sentinel2"},
            }

        ndvi_result = self._get_ndvi(bond)

        # Run CNN classifier if available (synthetic patch when GEE is offline)
        cnn_result = self._get_cnn_result(bond)
        raw_meta = ndvi_result.raw_metadata.copy()
        if cnn_result:
            raw_meta["cnn"] = cnn_result

        inconsistency, confidence = self._classify(bond, ndvi_result, cnn_result)

        return {
            "bond": bond,
            "verification_status": "verifiable",
            "ndvi_change": ndvi_result.ndvi_change,
            "satellite_land_use": ndvi_result.land_use,
            "pre_project_image_date": ndvi_result.pre_date,
            "post_project_image_date": ndvi_result.post_date,
            "claimed_project_type": bond.project_category,
            "is_inconsistent": inconsistency,
            "confidence": confidence,
            "model_version": "v1.1.0",
            "raw_ee_metadata": raw_meta,
        }

    def _get_cnn_result(self, bond: GreenBond) -> Optional[dict]:
        """Run ResNet-18 patch classifier if model is loaded."""
        if self._classifier is None:
            return None
        try:
            issue_str = bond.issuance_date.isoformat()
            result = self._classifier.classify_patch(
                float(bond.lat), float(bond.lon), issue_str
            )
            return {
                "predicted_class": result["predicted_class"],
                "confidence": result["confidence"],
                "all_probs": result["all_probs"],
            }
        except Exception as exc:
            logger.warning("CNN classification failed for %s: %s", bond.bond_id, exc)
            return None

    # ── NDVI retrieval ─────────────────────────────────────────────────────────

    def _get_ndvi(self, bond: GreenBond) -> NDVIResult:
        """Fetch NDVI data — GEE if available, else synthetic."""
        if self._ee is not None:
            result = self._gee_ndvi(bond)
            if result is not None:
                return result
        return self._synthetic_ndvi(bond)

    def _gee_ndvi(self, bond: GreenBond) -> Optional[NDVIResult]:
        """Fetch Sentinel-2 NDVI via SatelliteVerifier (Google Earth Engine)."""
        try:
            issue_dt   = bond.issuance_date
            before_str = (issue_dt - timedelta(days=365)).isoformat()
            after_str  = (issue_dt + timedelta(days=365)).isoformat()

            dynamic_radius = get_dynamic_radius(bond.project_category)

            result = self._verifier.get_ndvi_change(
                lat=float(bond.lat),
                lon=float(bond.lon),
                before_date=before_str,
                after_date=after_str,
                radius_km=dynamic_radius,
            )

            if result["source"] == "synthetic":
                # SatelliteVerifier fell back to synthetic — return None so
                # _synthetic_ndvi() runs directly for consistent source tracking
                return None

            pre_ndvi  = result["before_ndvi"]
            post_ndvi = result["after_ndvi"]
            ndvi_change = result["change"]
            land_use  = self._verifier.classify_land_use(
                float(bond.lat), float(bond.lon), issue_dt.isoformat()
            )

            return NDVIResult(
                pre_ndvi=pre_ndvi,
                post_ndvi=post_ndvi,
                ndvi_change=ndvi_change,
                pre_date=issue_dt - timedelta(days=365),
                post_date=issue_dt + timedelta(days=365),
                land_use=land_use,
                source="gee",
                raw_metadata={
                    "pre_ndvi":       pre_ndvi,
                    "post_ndvi":      post_ndvi,
                    "roi_buffer_m":   int(dynamic_radius * 1000),
                    "collection":     "COPERNICUS/S2_SR_HARMONIZED",
                    "n_images_before": result.get("n_images_before"),
                    "n_images_after":  result.get("n_images_after"),
                },
            )
        except Exception as exc:
            logger.error("GEE NDVI failed for bond %s: %s", bond.bond_id, exc)
            return None

    def _synthetic_ndvi(self, bond: GreenBond) -> NDVIResult:
        """
        Generate deterministic synthetic NDVI based on bond metadata.
        Used when GEE is unavailable. Seeds from bond_id for reproducibility.

        Logic mirrors real-world expectations:
          - Reforestation bonds in tropical latitudes → positive NDVI change
          - Urban/transport bonds → neutral or negative NDVI
          - Solar bonds in desert regions → negative NDVI (land clearing)
        """
        # Deterministic seed from bond_id hash
        rng = random.Random(hash(bond.bond_id) % (2**31))

        category = bond.project_category
        lat = float(bond.lat)
        issue_dt = bond.issuance_date

        # Base NDVI by latitude (tropics are greener)
        if abs(lat) < 15:
            base_ndvi = rng.uniform(0.55, 0.75)
        elif abs(lat) < 35:
            base_ndvi = rng.uniform(0.30, 0.55)
        else:
            base_ndvi = rng.uniform(0.10, 0.40)

        # Category-based NDVI change
        change_map = {
            "reforestation": rng.uniform(0.05, 0.20),    # positive: trees growing
            "solar":         rng.uniform(-0.15, -0.02),  # mild negative: some clearing
            "wind":          rng.uniform(-0.05, 0.05),   # near neutral
            "water":         rng.uniform(-0.10, 0.02),   # mild negative
            "transport":     rng.uniform(-0.20, -0.05),  # negative: construction
            "building":      rng.uniform(-0.25, -0.05),  # negative: urbanisation
            "other":         rng.uniform(-0.08, 0.08),   # neutral
        }
        ndvi_change = change_map.get(category, rng.uniform(-0.08, 0.08))

        # Inject occasional greenwashing signals for realism (10% of bonds)
        if rng.random() < 0.10:
            if category == "reforestation":
                ndvi_change = rng.uniform(-0.25, -0.10)  # claimed reforestation, actual deforestation
            elif category in ("solar", "wind"):
                ndvi_change = rng.uniform(-0.45, -0.25)  # more clearing than expected
            else:
                ndvi_change = rng.uniform(-0.30, -0.12)  # general land clearing

        post_ndvi = max(-1.0, min(1.0, base_ndvi + ndvi_change))
        land_use = self._classify_land_use_from_ndvi(post_ndvi)

        return NDVIResult(
            pre_ndvi=round(base_ndvi, 4),
            post_ndvi=round(post_ndvi, 4),
            ndvi_change=round(ndvi_change, 4),
            pre_date=issue_dt - timedelta(days=365),
            post_date=issue_dt + timedelta(days=365),
            land_use=land_use,
            source="synthetic",
            raw_metadata={
                "method": "synthetic",
                "base_ndvi": round(base_ndvi, 4),
                "category": category,
                "lat": lat,
            },
        )

    # ── Classification helpers ─────────────────────────────────────────────────

    @staticmethod
    def _classify_land_use_from_ndvi(ndvi: float) -> str:
        """Map NDVI value to a land-use class label."""
        if ndvi < 0.05:
            return "water_or_urban"
        if ndvi < NDVI_BARE_SOIL_MAX:
            return "bare_soil"
        if ndvi < 0.25:
            return "shrubland"
        if ndvi < 0.35:
            return "grassland"
        if ndvi < 0.50:
            return "cropland"
        return "forest"

    def _classify(self, bond: GreenBond, ndvi: NDVIResult, cnn_result: Optional[dict] = None) -> tuple[bool, float]:
        """
        Determine if the bond is inconsistent with its claimed project type.
        Returns (is_inconsistent: bool, confidence: float 0-1).
        """
        category = bond.project_category
        rules = CATEGORY_RULES.get(category, CATEGORY_RULES["other"])
        reasons = []
        confidence_signals = []

        # Rule 1: Reforestation with negative NDVI change
        if category == "reforestation":
            if ndvi.ndvi_change < rules["max_ndvi_drop"]:
                reasons.append(
                    f"Reforestation claimed but NDVI dropped {ndvi.ndvi_change:.3f} "
                    f"(threshold {rules['max_ndvi_drop']})"
                )
                confidence_signals.append(min(1.0, abs(ndvi.ndvi_change) / 0.3))

        # Rule 2: Post-project NDVI below minimum for category
        if rules["min_post_ndvi"] > 0 and ndvi.post_ndvi < rules["min_post_ndvi"]:
            reasons.append(
                f"Post-project NDVI {ndvi.post_ndvi:.3f} below minimum "
                f"{rules['min_post_ndvi']} for {category}"
            )
            confidence_signals.append(
                min(1.0, (rules["min_post_ndvi"] - ndvi.post_ndvi) / rules["min_post_ndvi"])
            )

        # Rule 3: Land use inconsistent with expected land-use types
        expected = rules["land_use_expected"]
        if expected and ndvi.land_use not in expected:
            reasons.append(
                f"Observed land use '{ndvi.land_use}' not expected for {category} "
                f"(expected: {expected})"
            )
            confidence_signals.append(0.5)

        # Rule 4: General severe NDVI drop (any category)
        if ndvi.ndvi_change < NDVI_CHANGE_FLAG_THRESHOLD and category not in ("building", "transport"):
            reasons.append(
                f"Significant vegetation loss: NDVI change {ndvi.ndvi_change:.3f} "
                f"< threshold {NDVI_CHANGE_FLAG_THRESHOLD}"
            )
            confidence_signals.append(min(1.0, abs(ndvi.ndvi_change) / 0.2))

        # Rule 5: CNN classifier mismatch (bonus signal)
        if cnn_result and category != "other":
            cnn_pred = cnn_result["predicted_class"]
            cnn_conf = cnn_result["confidence"]
            mapped = CNN_CLASS_MAP.get(cnn_pred, "other")
            if mapped != category and cnn_conf > 0.75:
                reasons.append(
                    f"CNN classifier predicts '{cnn_pred}' (mapped to {mapped}) "
                    f"with confidence {cnn_conf:.2f}, inconsistent with claimed '{category}'"
                )
                confidence_signals.append(cnn_conf * 0.5)

        is_inconsistent = len(reasons) > 0
        if confidence_signals:
            confidence = round(min(1.0, sum(confidence_signals) / len(confidence_signals)), 4)
        else:
            confidence = 0.0

        # Minimum confidence gate: weak signals should not be flagged
        MIN_FLAG_CONFIDENCE = 0.40
        if is_inconsistent and confidence < MIN_FLAG_CONFIDENCE:
            is_inconsistent = False

        if is_inconsistent:
            logger.warning(
                "Greenwash flag for bond %s: %s (conf=%.2f)",
                bond.bond_id, "; ".join(reasons), confidence,
            )
        else:
            logger.info("Bond %s passed greenwash check (conf=%.2f)", bond.bond_id, confidence)

        return is_inconsistent, confidence
