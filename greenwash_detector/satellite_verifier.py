# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
greenwash_detector/satellite_verifier.py — Step 5.1: NDVI Change Detection.

Uses Google Earth Engine (Sentinel-2 SR HARMONIZED) and ESA WorldCover to:
  1. Compute NDVI change between before/after project windows.
  2. Classify land cover using ESA WorldCover 10 m.
  3. Check greenwash consistency between satellite evidence and bond claims.

GEE authentication project: drought-module2
"""
import hashlib
import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("greenlens.satellite_verifier")

GEE_PROJECT = "drought-module2"

# ── ESA WorldCover 10 m class codes ──────────────────────────────────────────
WORLDCOVER_CLASSES = {
    10:  "forest",
    20:  "shrubland",
    30:  "grassland",
    40:  "cropland",
    50:  "built-up",
    60:  "bare",
    70:  "snow_ice",
    80:  "water",
    90:  "wetland",
    95:  "mangrove",
    100: "moss_lichen",
}


# ── GEE initialisation helper ─────────────────────────────────────────────────

def _init_ee():
    """
    Initialise Google Earth Engine using a service-account JSON stored in
    the EARTHENGINE_TOKEN environment variable (set in Render dashboard).

    Falls back to synthetic NDVI if the token is absent or invalid.
    """
    import os
    import json as _json

    try:
        import ee
        from google.oauth2 import service_account as _sa
    except ImportError:
        logger.warning("earthengine-api or google-auth not installed — GEE unavailable")
        return None

    token = os.getenv("EARTHENGINE_TOKEN")

    if token:
        # ── Render / production: use service-account JSON from env var ──────
        try:
            info = _json.loads(token)
            credentials = _sa.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/earthengine"],
            )
            ee.Initialize(credentials, project=info.get("project_id", GEE_PROJECT))
            logger.info("GEE initialised via EARTHENGINE_TOKEN service account")
            return ee
        except Exception as exc:
            logger.warning("GEE service-account init failed (%s) — synthetic NDVI will be used", exc)
            return None
    else:
        # ── Local dev: try existing credentials / interactive auth ───────────
        try:
            ee.Initialize(project=GEE_PROJECT)
            logger.info("GEE initialised (local credentials, project=%s)", GEE_PROJECT)
            return ee
        except ee.EEException:
            try:
                logger.info("GEE credentials absent — running ee.Authenticate() for local dev")
                ee.Authenticate()
                ee.Initialize(project=GEE_PROJECT)
                logger.info("GEE initialised after local authentication")
                return ee
            except Exception as exc:
                logger.warning("GEE local auth failed (%s) — synthetic NDVI will be used", exc)
                return None
        except Exception as exc:
            logger.warning("GEE initialisation failed (%s) — synthetic NDVI will be used", exc)
            return None


# ── GEE cache ─────────────────────────────────────────────────────────────────
GEE_TIMEOUT = 45  # seconds per .getInfo() call
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "gee_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(prefix: str, lat: float, lon: float, *args) -> str:
    """Deterministic hash for a GEE query."""
    payload = f"{prefix}:{lat:.5f}:{lon:.5f}:{':'.join(str(a) for a in args)}"
    return hashlib.md5(payload.encode()).hexdigest()


def _cache_path(prefix: str, lat: float, lon: float, *args) -> Path:
    return CACHE_DIR / f"{_cache_key(prefix, lat, lon, *args)}.json"


def _read_cache(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(path: Path, data: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        logger.warning("Could not write GEE cache %s: %s", path, exc)


def _getinfo_with_timeout(ee_obj, timeout: float = GEE_TIMEOUT):
    """Wrap GEE .getInfo() with a thread-pool timeout (Windows-safe)."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(ee_obj.getInfo)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            logger.warning("GEE .getInfo() timed out after %.1fs", timeout)
            raise


def get_dynamic_radius(project_category: str) -> float:
    """Determine physical boundary radius dynamically based on project type."""
    cat = (project_category or "").lower()
    if "wind" in cat:
        return 20.0  # Wind farms span tens of kilometers
    elif "solar" in cat:
        return 5.0   # Large utility solar footprint
    elif "building" in cat or "transport" in cat:
        return 1.0   # Highly localized urban infrastructure
    return 2.0       # Default baseline

# ── SatelliteVerifier ─────────────────────────────────────────────────────────

class SatelliteVerifier:
    """
    Satellite-based greenwash evidence provider for GreenLens.

    Primary data source: Google Earth Engine (Sentinel-2 L2A + ESA WorldCover).
    Fallback:            Deterministic synthetic NDVI derived from bond metadata.

    Usage:
        verifier = SatelliteVerifier()
        result   = verifier.get_ndvi_change(lat, lon, "2020-01-01", "2022-01-01")
        land_use = verifier.classify_land_use(lat, lon, "2022-01-01")
        check    = verifier.check_project_consistency("AND_Sustainabili_2021")
    """

    def __init__(self, skip_gee: bool = False):
        self._ee = None if skip_gee else _init_ee()

    # ──────────────────────────────────────────────────────────────────────────
    # Step 5.1a — NDVI change
    # ──────────────────────────────────────────────────────────────────────────

    def get_ndvi_change(
        self,
        lat: float,
        lon: float,
        before_date: str,
        after_date: str,
        radius_km: float = 2.0,
    ) -> dict:
        """
        Compute NDVI change between two date anchors at a project site.

        Each anchor date is expanded to a 12-month window
        (±182 days) so the median composite has enough cloud-free images.

        Parameters
        ----------
        lat, lon      : Project site coordinates.
        before_date   : ISO date for the *before* anchor  (e.g. bond issuance date − 1 year).
        after_date    : ISO date for the *after* anchor   (e.g. bond issuance date + 1 year).
        radius_km     : Radius around the point (km) used for spatial averaging.

        Returns
        -------
        dict with keys:
            before_ndvi     float   median NDVI in before window
            after_ndvi      float   median NDVI in after window
            change          float   after_ndvi − before_ndvi
            change_pct      float   (change / |before_ndvi|) × 100
            n_images_before int     cloud-free scenes in before window
            n_images_after  int     cloud-free scenes in after window
            source          str     "gee" | "synthetic"
        """
        if self._ee is not None:
            gee_result = self._gee_ndvi_change(lat, lon, before_date, after_date, radius_km)
            if gee_result is not None:
                return gee_result
        return self._synthetic_ndvi_change(lat, lon, before_date)

    def _gee_ndvi_change(
        self, lat, lon, before_date, after_date, radius_km
    ) -> Optional[dict]:
        ee = self._ee
        cache = _read_cache(_cache_path("ndvi", lat, lon, before_date, after_date, radius_km))
        if cache is not None:
            logger.debug("NDVI cache hit at (%.4f, %.4f)", lat, lon)
            return cache

        try:
            point = ee.Geometry.Point([float(lon), float(lat)])
            roi   = point.buffer(radius_km * 1000)  # metres

            # Expand each anchor to ±182 days (≈ 12 months)
            b_dt = datetime.strptime(before_date, "%Y-%m-%d")
            a_dt = datetime.strptime(after_date,  "%Y-%m-%d")

            b_start = (b_dt - timedelta(days=182)).strftime("%Y-%m-%d")
            b_end   = (b_dt + timedelta(days=182)).strftime("%Y-%m-%d")
            a_start = (a_dt - timedelta(days=182)).strftime("%Y-%m-%d")
            a_end   = (a_dt + timedelta(days=182)).strftime("%Y-%m-%d")

            def _median_ndvi(start: str, end: str) -> tuple[Optional[float], int]:
                """Return (median NDVI, n_scenes) for a date window."""
                col = (
                    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                    .filterBounds(roi)
                    .filterDate(start, end)
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
                )
                n = int(_getinfo_with_timeout(col.size()))
                if n == 0:
                    return None, 0
                ndvi_col = col.map(
                    lambda img: img.normalizedDifference(["B8", "B4"]).rename("NDVI")
                )
                median_img = ndvi_col.median()
                val = _getinfo_with_timeout(
                    median_img.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=roi,
                        scale=10,
                        maxPixels=1e8,
                    )
                )
                return val.get("NDVI"), n

            before_ndvi, n_before = _median_ndvi(b_start, b_end)
            after_ndvi,  n_after  = _median_ndvi(a_start, a_end)

            if before_ndvi is None or after_ndvi is None:
                logger.warning(
                    "GEE returned None NDVI at (%.4f, %.4f) — insufficient cloud-free scenes", lat, lon
                )
                return None

            before_ndvi = float(before_ndvi)
            after_ndvi  = float(after_ndvi)
            change      = after_ndvi - before_ndvi
            change_pct  = (change / abs(before_ndvi) * 100) if before_ndvi != 0 else 0.0

            result = {
                "before_ndvi":      round(before_ndvi, 4),
                "after_ndvi":       round(after_ndvi, 4),
                "change":           round(change, 4),
                "change_pct":       round(change_pct, 2),
                "n_images_before":  n_before,
                "n_images_after":   n_after,
                "source":           "gee",
            }
            _write_cache(_cache_path("ndvi", lat, lon, before_date, after_date, radius_km), result)

            logger.info(
                "GEE NDVI at (%.4f, %.4f): before=%.4f after=%.4f change=%.4f "
                "(n_before=%d n_after=%d)",
                lat, lon, before_ndvi, after_ndvi, change, n_before, n_after,
            )
            return result

        except Exception as exc:
            logger.error("GEE NDVI failed at (%.4f, %.4f): %s", lat, lon, exc)
            # Brief back-off before falling through to synthetic
            time.sleep(1)
            return None

    def get_visualisation_urls(self, lat: float, lon: float, before_date: str, after_date: str, radius_km: float = 2.0) -> dict:
        """Fetch RGB thumbnail URLs from GEE for before/after composite imagery."""
        if self._ee is None:
            return {"source": "synthetic", "before_url": "", "after_url": ""}
        
        ee = self._ee
        try:
            point = ee.Geometry.Point([float(lon), float(lat)])
            roi = point.buffer(radius_km * 1000)
            
            b_dt = datetime.strptime(before_date, "%Y-%m-%d")
            a_dt = datetime.strptime(after_date,  "%Y-%m-%d")

            b_start = (b_dt - timedelta(days=182)).strftime("%Y-%m-%d")
            b_end   = (b_dt + timedelta(days=182)).strftime("%Y-%m-%d")
            a_start = (a_dt - timedelta(days=182)).strftime("%Y-%m-%d")
            a_end   = (a_dt + timedelta(days=182)).strftime("%Y-%m-%d")

            def _get_url(start, end):
                col = (
                    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                    .filterBounds(roi)
                    .filterDate(start, end)
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
                )
                if int(_getinfo_with_timeout(col.size())) == 0:
                    return ""
                median_img = col.median().clip(roi)
                return _getinfo_with_timeout(median_img.getThumbURL({
                    "min": 0, "max": 3000, 
                    "bands": ["B4", "B3", "B2"], 
                    "dimensions": 500,
                    "format": "jpg"
                }))

            return {
                "source": "gee",
                "before_url": _get_url(b_start, b_end),
                "after_url": _get_url(a_start, a_end)
            }
            
        except Exception as exc:
            logger.error("GEE URL gen failed at (%.4f, %.4f): %s", lat, lon, exc)
            return {"source": "synthetic", "before_url": "", "after_url": ""}

    def generate_thumbnail_urls(
        self,
        lat: float,
        lon: float,
        before_date: str,
        after_date: str,
        radius_km: float = 3.0,
    ) -> dict:
        """
        Generate 512×512 PNG thumbnail URLs from GEE for before/after Sentinel-2
        composites. Used to populate GreenwashFlag.before_image_url / after_image_url.

        Parameters
        ----------
        lat, lon       : Project site coordinates.
        before_date    : ISO date string — start of the pre-project window.
        after_date     : ISO date string — start of the post-project window.
        radius_km      : Buffer radius around the point in km (default 3 km).

        Returns
        -------
        dict with keys:
            before_url  str | None   PNG thumbnail URL for pre-project period
            after_url   str | None   PNG thumbnail URL for post-project period
            source      str          "gee" or "unavailable"
        """
        if self._ee is None:
            logger.debug("GEE unavailable — skipping thumbnail generation")
            return {"before_url": None, "after_url": None, "source": "unavailable"}

        ee = self._ee
        try:
            point = ee.Geometry.Point([float(lon), float(lat)])
            region = point.buffer(radius_km * 1000)  # metres

            b_dt = datetime.strptime(before_date, "%Y-%m-%d")
            a_dt = datetime.strptime(after_date,  "%Y-%m-%d")

            b_start = b_dt.strftime("%Y-%m-%d")
            b_end   = (b_dt + timedelta(days=180)).strftime("%Y-%m-%d")
            a_start = a_dt.strftime("%Y-%m-%d")
            a_end   = (a_dt + timedelta(days=180)).strftime("%Y-%m-%d")

            thumb_params = {
                "region":     region,
                "dimensions": "512x512",
                "format":     "png",
                "min":        0,
                "max":        3000,
                "gamma":      1.4,
                "bands":      ["B4", "B3", "B2"],
            }

            def _thumb(start: str, end: str) -> Optional[str]:
                col = (
                    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                    .filterBounds(region)
                    .filterDate(start, end)
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
                )
                n = int(_getinfo_with_timeout(col.size()))
                if n == 0:
                    logger.debug(
                        "No cloud-free Sentinel-2 scenes in %s–%s at (%.4f, %.4f)",
                        start, end, lat, lon,
                    )
                    return None
                composite = col.median().clip(region)
                url = _getinfo_with_timeout(composite.getThumbURL(thumb_params))
                return url if url else None

            before_url = _thumb(b_start, b_end)
            after_url  = _thumb(a_start, a_end)

            logger.info(
                "Thumbnail URLs generated at (%.4f, %.4f): before=%s after=%s",
                lat, lon,
                "ok" if before_url else "none",
                "ok" if after_url  else "none",
            )
            return {"before_url": before_url, "after_url": after_url, "source": "gee"}

        except Exception as exc:
            logger.error(
                "generate_thumbnail_urls failed at (%.4f, %.4f): %s", lat, lon, exc
            )
            return {"before_url": None, "after_url": None, "source": "unavailable"}

    def _synthetic_ndvi_change(self, lat: float, lon: float, before_date: str) -> dict:
        """
        Deterministic synthetic NDVI when GEE is unavailable.
        Seeded from coordinates for reproducibility across runs.
        """
        seed = int(
            hashlib.md5(f"{lat:.4f}{lon:.4f}{before_date}".encode()).hexdigest(), 16
        ) % (2 ** 31)
        rng = random.Random(seed)

        # Latitude-based vegetation baseline
        if abs(lat) < 15:
            base = rng.uniform(0.55, 0.75)   # tropical
        elif abs(lat) < 35:
            base = rng.uniform(0.30, 0.55)   # subtropical
        else:
            base = rng.uniform(0.10, 0.40)   # temperate / boreal

        change = rng.uniform(-0.10, 0.12)
        after  = max(-1.0, min(1.0, base + change))
        change_pct = (change / abs(base) * 100) if base != 0 else 0.0

        return {
            "before_ndvi":     round(base, 4),
            "after_ndvi":      round(after, 4),
            "change":          round(change, 4),
            "change_pct":      round(change_pct, 2),
            "n_images_before": rng.randint(4, 18),
            "n_images_after":  rng.randint(4, 18),
            "source":          "synthetic",
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Step 5.1b — ESA WorldCover land classification
    # ──────────────────────────────────────────────────────────────────────────

    def classify_land_use(self, lat: float, lon: float, date: str) -> str:
        """
        Return the dominant ESA WorldCover 10 m land cover class at a location.

        Uses ESA/WorldCover/v200 (2021 map) from GEE.
        Falls back to a latitude-based heuristic when GEE is unavailable.

        Returns one of: forest, shrubland, grassland, cropland, built-up,
                        bare, water, wetland, mangrove, snow_ice, unknown.
        """
        if self._ee is not None:
            result = self._gee_worldcover(lat, lon)
            if result is not None:
                return result
        return self._heuristic_land_use(lat)

    def _gee_worldcover(self, lat: float, lon: float) -> Optional[str]:
        cache = _read_cache(_cache_path("wc", lat, lon))
        if cache is not None:
            logger.debug("WorldCover cache hit at (%.4f, %.4f)", lat, lon)
            return cache.get("label")

        ee = self._ee
        try:
            point = ee.Geometry.Point([float(lon), float(lat)])
            roi   = point.buffer(500)   # 500 m radius for mode aggregation
            wc    = ee.ImageCollection("ESA/WorldCover/v200").first()
            val   = _getinfo_with_timeout(
                wc.reduceRegion(
                    reducer=ee.Reducer.mode(),
                    geometry=roi,
                    scale=10,
                    maxPixels=1e6,
                )
            )
            code = val.get("Map")
            if code is not None:
                label = WORLDCOVER_CLASSES.get(int(code), "unknown")
                logger.debug(
                    "ESA WorldCover at (%.4f, %.4f): code=%s label=%s", lat, lon, code, label
                )
                _write_cache(_cache_path("wc", lat, lon), {"label": label, "code": int(code)})
                return label
            return None
        except Exception as exc:
            logger.error("GEE WorldCover failed at (%.4f, %.4f): %s", lat, lon, exc)
            return None

    @staticmethod
    def _heuristic_land_use(lat: float) -> str:
        """Rough latitude-band land-use heuristic used when GEE is offline."""
        if abs(lat) < 10:
            return "forest"
        if abs(lat) < 25:
            return "cropland"
        if abs(lat) < 50:
            return "grassland"
        if abs(lat) < 65:
            return "shrubland"
        return "bare"

    # ──────────────────────────────────────────────────────────────────────────
    # Step 5.1c — Project consistency check
    # ──────────────────────────────────────────────────────────────────────────

    def check_project_consistency(self, bond_id: str) -> dict:
        """
        Retrieve a bond's coordinates and claimed project type from the database,
        run NDVI + land-cover analysis, and apply consistency rules.

        Consistency rules (from spec):
          reforestation : NDVI change must be > +0.10 (vegetation increase)
          solar         : NDVI change must be < −0.05  (land cleared for panels)
          wind          : any NDVI change is acceptable
          water         : ESA WorldCover must show water or wetland

        Returns
        -------
        dict with keys:
            is_consistent   bool
            ndvi_change     float
            evidence_summary str
            confidence      float  0–1
        """
        from data_ingestion.models import GreenBond

        try:
            bond = GreenBond.objects.get(bond_id=bond_id)
        except GreenBond.DoesNotExist:
            return {
                "is_consistent":   True,
                "ndvi_change":     0.0,
                "evidence_summary": f"Bond '{bond_id}' not found in database.",
                "confidence":      0.0,
            }

        lat      = float(bond.lat)
        lon      = float(bond.lon)
        issuance = bond.issuance_date

        before_str = (issuance - timedelta(days=365)).isoformat()
        after_str  = (issuance + timedelta(days=365)).isoformat()

        ndvi_result = self.get_ndvi_change(lat, lon, before_str, after_str)
        land_use    = self.classify_land_use(lat, lon, issuance.isoformat())

        category = bond.project_category
        change   = ndvi_result["change"]

        # ── Apply rules ───────────────────────────────────────────────────────
        flags: list[str] = []

        if category == "reforestation":
            if change < 0.10:
                flags.append(
                    f"Reforestation claimed but NDVI change is {change:+.4f} "
                    f"(threshold +0.10 required)"
                )

        elif category == "solar":
            if change > -0.05:
                flags.append(
                    f"Solar farm claimed but NDVI change is {change:+.4f} "
                    f"(expected < -0.05 — land should be cleared for panels)"
                )

        elif category == "wind":
            pass  # Wind turbines don't require significant vegetation clearing

        elif category in ("water", "waterways", "flood_management"):
            if land_use not in ("water", "wetland"):
                flags.append(
                    f"Water project claimed but satellite shows '{land_use}' "
                    f"(expected water or wetland)"
                )

        is_consistent = len(flags) == 0

        # ── Confidence ────────────────────────────────────────────────────────
        if is_consistent:
            # Higher confidence when evidence strongly matches expectations
            if category == "reforestation" and change >= 0.20:
                confidence = 0.95
            elif category == "solar" and change <= -0.15:
                confidence = 0.95
            else:
                confidence = 0.80
        else:
            # Confidence scaled by magnitude of the anomaly
            max_anomaly = max(abs(change - 0.10), abs(change + 0.05), 0.01)
            confidence = min(0.95, 0.50 + max_anomaly * 1.5)

        # ── Evidence summary ──────────────────────────────────────────────────
        source_note = f"(source: {ndvi_result['source']})"
        if is_consistent:
            summary = (
                f"Satellite evidence CONSISTENT with '{category}' claim. "
                f"NDVI change: {change:+.4f}. "
                f"Land cover: {land_use}. {source_note}"
            )
        else:
            summary = (
                f"INCONSISTENCY DETECTED: {'; '.join(flags)}. "
                f"Land cover: {land_use}. {source_note}"
            )

        logger.info(
            "check_project_consistency bond=%s is_consistent=%s confidence=%.2f",
            bond_id, is_consistent, confidence,
        )
        return {
            "is_consistent":    is_consistent,
            "ndvi_change":      change,
            "evidence_summary": summary,
            "confidence":       round(confidence, 4),
        }
