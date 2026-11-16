"""Polygon-based optical and SAR measurements; no inferred damage labels."""

import math
from datetime import date

from data_ingestion.pilot import boundary_hash, validate_boundary
from greenwash_detector.sar_verifier import SarVerifier


OPTICAL_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"


def optical_quality(values, min_scenes=2, min_coverage=0.9):
    for period in ("before", "after"):
        measurement = values.get(period, {})
        required = [measurement.get(name) for name in ("ndvi", "ndmi", "observed_fraction")]
        if (measurement.get("scene_count", 0) < min_scenes
                or any(value is None or not math.isfinite(float(value)) for value in required)
                or not min_coverage <= float(measurement["observed_fraction"]) <= 1.01):
            return "unavailable"
    return "observed"


def collect_optical(verifier, boundary, windows):
    result = {"status": "unavailable", "collection": OPTICAL_COLLECTION,
              "cloud_mask": "SCL excludes shadow, medium/high cloud, cirrus and snow", "scale_m": 20}
    if verifier._ee is None:
        result["reason"] = "Earth Engine was unavailable; no synthetic fallback."
        return result
    try:
        ee = verifier._ee
        region = ee.Geometry(boundary, proj="EPSG:4326", geodesic=False)

        def cloud_mask(image):
            scl = image.select("SCL")
            valid = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
            return image.updateMask(valid)

        values = {}
        for period in ("before", "after"):
            collection = (ee.ImageCollection(OPTICAL_COLLECTION).filterBounds(region)
                          .filterDate(windows[f"{period}_start"], windows[f"{period}_end"])
                          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 70)).map(cloud_mask))
            image = collection.median()
            ndvi = image.normalizedDifference(["B8", "B4"]).rename("ndvi")
            ndmi = image.normalizedDifference(["B8", "B11"]).rename("ndmi")
            reduction = {"geometry": region, "scale": 20, "maxPixels": 1000000, "tileScale": 2}
            means = ndvi.addBands(ndmi).reduceRegion(reducer=ee.Reducer.mean(), **reduction)
            valid_area = ee.Image.pixelArea().updateMask(ndvi.mask().And(ndmi.mask())).reduceRegion(reducer=ee.Reducer.sum(), **reduction).get("area")
            values[period] = ee.Dictionary({
                "ndvi": means.get("ndvi"), "ndmi": means.get("ndmi"),
                "scene_count": collection.size(), "observed_area_m2": valid_area,
                "polygon_area_m2": region.area(1),
            })
        dem = ee.Image("USGS/SRTMGL1_003").select("elevation")
        values["terrain"] = dem.addBands(ee.Terrain.slope(dem).rename("slope_deg")).reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=30, maxPixels=1000000,
        )
        measured = verifier._evaluate(ee.Dictionary(values))
        for period in ("before", "after"):
            measurement = measured.get(period) or {}
            area = measurement.get("polygon_area_m2")
            covered = measurement.get("observed_area_m2")
            measurement["observed_fraction"] = covered / area if covered is not None and area and area > 0 else None
            measured[period] = measurement
        result.update(measured)
        result["status"] = optical_quality(measured)
        result["reason"] = "Cloud-screened polygon composites, not damage or project-performance labels." if result["status"] == "observed" else "Insufficient cloud-screened observations or polygon coverage."
    except Exception:
        result["reason"] = "Optical processing unavailable or exceeded its deadline; no estimated values substituted."
    return result


def collect_project_evidence(project, windows):
    from data_ingestion.models import PilotEvidence

    parsed = [date.fromisoformat(windows[key]) for key in ("before_start", "before_end", "after_start", "after_end")]
    if not parsed[0] < parsed[1] <= parsed[2] < parsed[3] or (parsed[1] - parsed[0]).days > 366 or (parsed[3] - parsed[2]).days > 366:
        raise ValueError("Use ordered, nonoverlapping windows of at most one year each.")
    if (parsed[0].month, parsed[0].day, parsed[1].month, parsed[1].day) != (parsed[2].month, parsed[2].day, parsed[3].month, parsed[3].day):
        raise ValueError("Pilot comparisons require matching seasonal windows across different years.")
    geometry = validate_boundary(project.boundary)
    center = geometry.representative_point()
    digest = boundary_hash(project.boundary)
    with SarVerifier() as verifier:
        sar = verifier.verify(center.y, center.x, **windows, claimed_category=project.category, boundary=project.boundary)
        optical = collect_optical(verifier, project.boundary, windows)
    optical_observed = optical["status"] == "observed"
    sar_observed = sar.get("sar_change_db") is not None and sar.get("observed_fraction", 0) is not None and sar.get("observed_fraction", 0) >= 0.9
    status = "both_observed" if optical_observed and sar_observed else "partial" if optical_observed or sar_observed else "unavailable"
    return PilotEvidence.objects.create(
        project=project, boundary_sha256=digest, windows=windows,
        status=status, optical=optical, sar=sar,
    )