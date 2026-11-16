"""Provenance-gated project pilot; never promotes registry estimates to observations."""

import hashlib
import json
import math
import io
import random
import zipfile

from django.core.exceptions import ValidationError


USPVDB_URL = "https://energy.usgs.gov/uspvdb/assets/data/uspvdbGeoJSON.zip"
USPVDB_CITATION = "https://doi.org/10.5066/P9IA3TUS"


def validate_boundary(boundary):
    from shapely.geometry import shape

    try:
        geometry = shape(boundary)
        if geometry.geom_type not in ("Polygon", "MultiPolygon") or geometry.is_empty or not geometry.is_valid:
            raise ValueError
        west, south, east, north = geometry.bounds
        if not all(math.isfinite(value) for value in geometry.bounds) or not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError
        if east - west > 2 or north - south > 2:
            raise ValueError
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise ValidationError("Use a valid, nonempty WGS84 project Polygon or MultiPolygon with extent under two degrees.") from exc
    return geometry


def boundary_hash(boundary):
    validate_boundary(boundary)
    return hashlib.sha256(json.dumps(boundary, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def fetch_official_projects():
    import requests

    content = bytearray()
    with requests.get(USPVDB_URL, timeout=(10, 60), stream=True) as response:
        response.raise_for_status()
        for chunk in response.iter_content(65536):
            content.extend(chunk)
            if len(content) > 25_000_000:
                raise ValueError("USPVDB download exceeded the 25 MB safety limit.")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = [entry for entry in archive.infolist() if entry.filename.lower().endswith(".geojson")]
        if len(entries) != 1 or entries[0].file_size > 150_000_000:
            raise ValueError("Expected one bounded official GeoJSON release.")
        dataset = json.loads(archive.read(entries[0]))
    return dataset, entries[0].filename, hashlib.sha256(content).hexdigest()


def import_official_projects(dataset, version, source_sha256, state="TX", limit=30):
    from django.db import transaction
    from .models import PilotProject

    if dataset.get("type") != "FeatureCollection" or not 1 <= limit <= 50:
        raise ValueError("Expected a GeoJSON FeatureCollection and a limit between 1 and 50.")
    candidates = [feature for feature in dataset["features"] if (
        feature["properties"].get("p_state") == state
        and feature["properties"].get("p_dig_conf") == 4
        and feature["properties"].get("p_sys_type") == "ground"
        and (feature["properties"].get("p_year") or 0) >= 2017
    )]
    candidates.sort(key=lambda feature: feature["properties"]["case_id"])
    random.Random(42).shuffle(candidates)
    existing_ids = list(PilotProject.objects.filter(region=state, source_id__startswith="USPVDB-").values_list("source_id", flat=True))
    if len(existing_ids) > limit:
        raise ValueError("The existing cohort is larger than the requested limit; imports never silently remove projects.")
    by_id = {f"USPVDB-{int(feature['properties']['case_id'])}": feature for feature in candidates}
    if set(existing_ids) - set(by_id):
        raise ValueError("An existing cohort project is missing or no longer meets source quality criteria; analyst review is required.")
    candidates = [by_id[identifier] for identifier in existing_ids] + [
        feature for feature in candidates if f"USPVDB-{int(feature['properties']['case_id'])}" not in existing_ids
    ]
    if len(candidates) < limit:
        raise ValueError(f"Only {len(candidates)} eligible source polygons are available; no placeholder projects were created.")
    counts = {"created": 0, "unchanged": 0, "boundary_conflicts": [], "selected": limit}
    with transaction.atomic():
        for feature in candidates[:limit]:
            properties, boundary = feature["properties"], feature["geometry"]
            digest = boundary_hash(boundary)
            source_id = f"USPVDB-{int(properties['case_id'])}"
            project, created = PilotProject.objects.get_or_create(source_id=source_id, defaults={
                "name": properties["p_name"], "country": "United States", "region": state,
                "category": "solar", "boundary": boundary, "boundary_sha256": digest,
                "source_url": USPVDB_CITATION, "source_version": version,
                "source_metadata": {**properties, "archive_sha256": source_sha256,
                    "download_url": USPVDB_URL, "selection": "eligible source IDs sorted then shuffled with seed 42",
                    "mapping_limit": "Aerial-image mapped by source; not field verified; no green-bond linkage asserted"},
            })
            if created:
                project.full_clean()
                counts["created"] += 1
            elif project.boundary_sha256 == digest:
                counts["unchanged"] += 1
            else:
                counts["boundary_conflicts"].append(source_id)
    return counts


def run_official_ingestion(state="TX", limit=30):
    from django.utils import timezone
    from .models import PilotIngestionRun

    run = PilotIngestionRun.objects.create(source_url=USPVDB_URL)
    try:
        dataset, version, digest = fetch_official_projects()
        run.source_sha256 = digest
        run.result = import_official_projects(dataset, version, digest, state, limit)
        run.status = "needs_review" if run.result["boundary_conflicts"] else "completed"
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)[:1000]
        raise
    finally:
        run.completed_at = timezone.now()
        run.save()
    return run