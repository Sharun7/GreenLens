"""Sentinel-1 evidence screening; all category and flood rules are unvalidated heuristics."""

import json
import math
import os
from datetime import date

import requests
from django.conf import settings


COLLECTION = "COPERNICUS/S1_GRD"
WATER_COLLECTION = "JRC/GSW1_4/YearlyHistory"
TIMEOUT_SECONDS = 45
BUFFER_METRES = 2000


def _orbit_counts(histogram):
    counts = {}
    if not isinstance(histogram, dict):
        return counts
    for orbit, count in histogram.items():
        try:
            orbit_number, scene_count = float(orbit), float(count)
        except (ValueError, TypeError):
            continue
        if (math.isfinite(orbit_number) and orbit_number.is_integer()
                and 1 <= orbit_number <= 175 and math.isfinite(scene_count)
                and scene_count.is_integer() and scene_count >= 0):
            counts[int(orbit_number)] = int(scene_count)
    return counts


class SarVerifier:
    """Compare explicit, non-overlapping date windows without synthetic fallback.

    The injected evaluator is for offline testing. Production evaluations use the
    Earth Engine REST endpoint to avoid getInfo's implicit retries. A verifier
    owns its HTTP session and should not be shared between batch worker threads.
    """

    def __init__(self, ee_module=None, evaluator=None):
        self._ee = ee_module
        self._evaluator = evaluator
        self._session = None
        self.project = settings.EE_PROJECT_ID or "drought-module2"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _initialize(self):
        import ee
        import httplib2
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account

        service_json = os.environ.get("EARTHENGINE_TOKEN", "").strip()
        if service_json:
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(service_json),
                scopes=["https://www.googleapis.com/auth/earthengine"],
            )
        elif settings.EE_SERVICE_ACCOUNT and settings.EE_PRIVATE_KEY_FILE:
            credentials = ee.ServiceAccountCredentials(
                settings.EE_SERVICE_ACCOUNT, settings.EE_PRIVATE_KEY_FILE,
            )
        else:
            credentials = ee.data.get_persistent_credentials()
        ee.Initialize(
            credentials=credentials, project=self.project,
            http_transport=httplib2.Http(timeout=TIMEOUT_SECONDS),
        )
        self._session = AuthorizedSession(
            credentials, max_refresh_attempts=0, refresh_timeout=TIMEOUT_SECONDS,
        )
        self._ee = ee

    def _request_value(self, expression):
        response = self._session.post(
            f"https://earthengine.googleapis.com/v1/projects/{self.project}/value:compute",
            json={"expression": self._ee.serializer.encode(expression, for_cloud_api=True)},
            timeout=TIMEOUT_SECONDS,
            max_allowed_time=TIMEOUT_SECONDS,
        )
        try:
            payload = response.json()
            error = payload.get("error", {})
            error_message = str(error.get("message", "")).lower()
            if (response.status_code in (408, 504)
                    or error.get("status") == "DEADLINE_EXCEEDED"
                    or "computation timed out" in error_message):
                raise TimeoutError("Earth Engine computation deadline exceeded")
            response.raise_for_status()
            return payload["result"]
        finally:
            response.close()

    def _evaluate(self, expression):
        evaluate = self._evaluator or self._request_value
        for attempt in range(2):
            try:
                return evaluate(expression)
            except (TimeoutError, requests.Timeout):
                if attempt == 1:
                    raise

    def close(self):
        if self._session is not None:
            self._session.close()
            self._session = None

    def verify(
        self, lat, lon, before_start, before_end, after_start, after_end,
        claimed_category, boundary=None,
    ):
        """Dates are ISO dates; starts are inclusive and ends are exclusive."""
        result = {
            "status": "unverifiable", "reason": "SAR evidence has not been computed.",
            "collection": COLLECTION, "buffer_m": BUFFER_METRES,
            "before_start": before_start, "before_end": before_end,
            "after_start": after_start, "after_end": after_end,
            "sar_before_db": None, "sar_after_db": None, "sar_change_db": None,
            "before_vh_db": None, "after_vh_db": None, "vh_change_db": None,
            "before_vh_vv_ratio": None, "after_vh_vv_ratio": None,
            "flooded_fraction": None, "observed_fraction": None,
            "water_map_coverage_fraction": None,
            "permanent_water_policy": "Exclude known pre-event JRC class-3 water; unmapped pixels are not assumed to be confirmed dry land.",
            "before_scene_count": 0, "after_scene_count": 0,
            "relative_orbit": None, "water_mask_year": None,
            "orbit_pass": settings.SAR_ORBIT_PASS,
            "thresholds": {
                "flood_change_db": settings.SAR_FLOOD_CHANGE_DB,
                "flood_max_after_db": settings.SAR_FLOOD_MAX_AFTER_DB,
                "min_observed_fraction": settings.SAR_MIN_OBSERVED_FRACTION,
                "min_scenes": settings.SAR_MIN_SCENES,
                "category": settings.SAR_CATEGORY_THRESHOLDS.get(claimed_category),
            },
            "method": "Heuristic SAR consistency screen, not proof of project existence or greenwashing.",
        }
        if boundary is not None:
            from django.core.exceptions import ValidationError
            from data_ingestion.pilot import boundary_hash

            try:
                result["boundary_sha256"] = boundary_hash(boundary)
            except (ValidationError, TypeError, ValueError):
                result["reason"] = "Invalid project polygon; no point-buffer fallback was substituted."
                return result
            result["buffer_m"] = None
            result["geometry_kind"] = "project_polygon"
        try:
            latitude, longitude = float(lat), float(lon)
            if not (math.isfinite(latitude) and math.isfinite(longitude)
                    and -90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError
            dates = [date.fromisoformat(value) for value in (
                before_start, before_end, after_start, after_end,
            )]
            if not dates[0] < dates[1] <= dates[2] < dates[3]:
                raise ValueError
            if (settings.SAR_ORBIT_PASS not in ("ASCENDING", "DESCENDING")
                    or settings.SAR_MIN_SCENES < 1
                    or settings.SAR_REDUCTION_SCALE_METRES <= 0
                    or not 0 < settings.SAR_MIN_OBSERVED_FRACTION <= 1
                    or not math.isfinite(settings.SAR_FLOOD_CHANGE_DB)
                    or settings.SAR_FLOOD_CHANGE_DB >= 0
                    or not math.isfinite(settings.SAR_FLOOD_MAX_AFTER_DB)):
                raise ValueError
        except (ValueError, TypeError):
            result["reason"] = "Invalid coordinates, date windows, or SAR configuration."
            return result

        if self._ee is None:
            try:
                self._initialize()
            except Exception:
                self.close()
                result["reason"] = (
                    "GEE initialization failed. Configure authorized service-account credentials "
                    "or run earthengine authenticate locally; interactive authentication was not started."
                )
                return result

        try:
            ee = self._ee
            region = ee.Geometry(boundary, proj="EPSG:4326", geodesic=False) if boundary is not None else ee.Geometry.Point([longitude, latitude]).buffer(BUFFER_METRES)
            collection = (
                ee.ImageCollection(COLLECTION).filterBounds(region)
                .filter(ee.Filter.eq("instrumentMode", "IW"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
                .filter(ee.Filter.eq("orbitProperties_pass", settings.SAR_ORBIT_PASS))
                .filter(ee.Filter.eq("resolution_meters", 10))
            )
            before = collection.filterDate(before_start, before_end)
            after = collection.filterDate(after_start, after_end)
            water = (
                ee.ImageCollection(WATER_COLLECTION)
                .filterDate("1984-01-01", f"{dates[0].year}-01-01")
                .sort("system:time_start", False)
            )
            metadata = self._evaluate(ee.Dictionary({
                "before_orbits": before.aggregate_histogram("relativeOrbitNumber_start"),
                "after_orbits": after.aggregate_histogram("relativeOrbitNumber_start"),
                "water_count": water.size(),
            }))
            before_orbits = _orbit_counts(metadata.get("before_orbits"))
            after_orbits = _orbit_counts(metadata.get("after_orbits"))
            common = [
                orbit for orbit in before_orbits.keys() & after_orbits.keys()
                if min(before_orbits[orbit], after_orbits[orbit]) >= settings.SAR_MIN_SCENES
            ]
            if not common:
                result["reason"] = (
                    "Insufficient Sentinel-1 IW VV/VH scenes on a shared relative orbit "
                    "for the selected pass and date windows."
                )
                return result
            if not metadata.get("water_count"):
                result["reason"] = "No pre-event JRC permanent-water map is available."
                return result
            orbit = max(common, key=lambda value: (
                min(before_orbits[value], after_orbits[value]), -int(value),
            ))
            result.update({
                "relative_orbit": int(orbit),
                "before_scene_count": int(before_orbits[orbit]),
                "after_scene_count": int(after_orbits[orbit]),
            })
            before_image = before.filter(
                ee.Filter.eq("relativeOrbitNumber_start", int(orbit)),
            ).select(["VV", "VH"]).median()
            after_image = after.filter(
                ee.Filter.eq("relativeOrbitNumber_start", int(orbit)),
            ).select(["VV", "VH"]).median()
            water_image = ee.Image(water.first())
            permanent_water = water_image.select("waterClass")
            measurements = self._measure(before_image, after_image, permanent_water, region)
            measurements["water_mask_year"] = water_image.get("year")
            values = self._evaluate(ee.Dictionary(measurements))
            return self._interpret(result, values, claimed_category)
        except (TimeoutError, requests.Timeout):
            result["reason"] = "Earth Engine timed out after 45 seconds per attempt; one retry was exhausted."
        except Exception:
            result["reason"] = (
                "Earth Engine SAR processing is unavailable. Check GEE credentials, "
                "project access, quota, and dataset availability; no synthetic result was substituted."
            )
        return result

    def _measure(self, before, after, water_class, region):
        ee = self._ee
        valid = (
            before.select("VV").mask().And(before.select("VH").mask())
            .And(after.select("VV").mask()).And(after.select("VH").mask())
        )
        permanent_water = water_class.eq(3).unmask(0)
        change = after.select("VV").subtract(before.select("VV"))
        flood = (
            change.lt(settings.SAR_FLOOD_CHANGE_DB)
            .And(after.select("VV").lt(settings.SAR_FLOOD_MAX_AFTER_DB))
            .And(permanent_water.Not()).updateMask(valid)
        )

        def bands(image, prefix):
            ratio = ee.Image.constant(10).pow(
                image.select("VH").subtract(image.select("VV")).divide(10),
            ).rename(prefix + "_vh_vv_ratio")
            return image.select(
                ["VV", "VH"], [prefix + "_vv_db", prefix + "_vh_db"],
            ).addBands(ratio)

        reduction = {
            "geometry": region, "scale": settings.SAR_REDUCTION_SCALE_METRES,
            "maxPixels": 1000000, "tileScale": 2,
        }
        backscatter = (
            bands(before, "before").addBands(bands(after, "after"))
            .addBands(change.rename("vv_change_db"))
            .addBands(after.select("VH").subtract(before.select("VH")).rename("vh_change_db"))
            .updateMask(valid)
            .reduceRegion(reducer=ee.Reducer.mean(), **reduction)
        )
        area = ee.Image.pixelArea()
        areas = (
            area.multiply(flood.unmask(0)).rename("flooded_area_m2")
            .addBands(area.multiply(valid.unmask(0)).rename("observed_area_m2"))
            .addBands(area.multiply(water_class.mask().unmask(0)).rename("water_map_area_m2"))
            .reduceRegion(reducer=ee.Reducer.sum(), **reduction)
        )
        return {"backscatter": backscatter, "areas": areas, "buffer_area_m2": region.area(1)}

    @staticmethod
    def _interpret(result, values, category):
        measurements = values.get("backscatter") or {}
        areas = values.get("areas") or {}
        names = (
            "before_vv_db", "before_vh_db", "before_vh_vv_ratio",
            "after_vv_db", "after_vh_db", "after_vh_vv_ratio",
            "vv_change_db", "vh_change_db",
        )
        required = [measurements.get(name) for name in names]
        required.extend([
            areas.get("flooded_area_m2"), areas.get("observed_area_m2"),
            values.get("buffer_area_m2"),
        ])
        if any(value is None or not math.isfinite(float(value)) for value in required):
            result["reason"] = "No valid overlapping SAR pixels or water-mask measurements in the buffer."
            return result
        flooded_area = float(areas["flooded_area_m2"])
        observed_area = float(areas["observed_area_m2"])
        buffer_area = float(values["buffer_area_m2"])
        if buffer_area <= 0 or observed_area <= 0 or flooded_area < 0 or flooded_area > observed_area:
            result["reason"] = "Invalid or missing SAR area measurements."
            return result
        observed_fraction = min(1.0, observed_area / buffer_area)
        result["observed_fraction"] = round(observed_fraction, 6)
        water_map_area = areas.get("water_map_area_m2")
        if water_map_area is not None and math.isfinite(float(water_map_area)):
            result["water_map_coverage_fraction"] = round(min(1.0, max(0.0, float(water_map_area) / buffer_area)), 6)
        if observed_fraction < settings.SAR_MIN_OBSERVED_FRACTION:
            result["reason"] = "Insufficient observed buffer coverage; missing pixels are not treated as dry land."
            return result
        result.update({
            "sar_before_db": float(measurements["before_vv_db"]),
            "sar_after_db": float(measurements["after_vv_db"]),
            "sar_change_db": float(measurements["vv_change_db"]),
            "before_vh_db": float(measurements["before_vh_db"]),
            "after_vh_db": float(measurements["after_vh_db"]),
            "vh_change_db": float(measurements["vh_change_db"]),
            "before_vh_vv_ratio": float(measurements["before_vh_vv_ratio"]),
            "after_vh_vv_ratio": float(measurements["after_vh_vv_ratio"]),
            "flooded_fraction": round(min(1.0, flooded_area / buffer_area), 6),
            "water_mask_year": values.get("water_mask_year"),
        })
        rules = settings.SAR_CATEGORY_THRESHOLDS.get(category)
        if not rules:
            result["reason"] = "SAR measurements are available, but no category heuristic is configured."
            return result
        conflicts = []
        for feature, bounds in rules.items():
            value = measurements.get("after_" + feature)
            if value is None:
                result["reason"] = "Category heuristic refers to an unavailable SAR measurement."
                return result
            lower, upper = bounds
            if (lower is not None and value < lower) or (upper is not None and value > upper):
                conflicts.append(feature)
        if conflicts:
            result["status"] = "inconsistent"
            result["reason"] = (
                f"SAR observations conflict with the configured {category} heuristic "
                f"({', '.join(conflicts)}). This is not proof of greenwashing."
            )
        else:
            result["status"] = "verified"
            result["reason"] = (
                f"Valid SAR observations pass the configured {category} heuristic. "
                "This does not prove project existence, construction, or environmental benefit."
            )
        return result