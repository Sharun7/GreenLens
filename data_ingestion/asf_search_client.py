"""Bounded, cached ASF catalog discovery. Never downloads raw satellite products."""

import hashlib
import math
import os
from datetime import date
from urllib.parse import quote, urlsplit

import asf_search as asf
from django.core.cache import cache


class MetadataSession(asf.ASFSession):
    def request(self, method, url, **kwargs):
        kwargs["timeout"] = (5, 12)
        kwargs["allow_redirects"] = False
        return super().request(method, url, **kwargs)


def _browse_url(properties):
    candidates = properties.get("browse") or []
    if isinstance(candidates, str):
        candidates = [candidates]
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        parsed = urlsplit(candidate)
        host = parsed.hostname or ""
        if (parsed.scheme == "https" and not parsed.username and not parsed.password
                and (host.endswith(".asf.alaska.edu") or host.endswith(".earthdata.nasa.gov"))
                and not parsed.query):
            return candidate
    return None


def search_sar_metadata(lat, lon, start, end, limit=6):
    """Return public granule metadata; empty coverage is distinct from service failure."""
    latitude, longitude = float(lat), float(lon)
    start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
    if (not math.isfinite(latitude) or not math.isfinite(longitude)
            or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
            or not start_date <= end_date or (end_date - start_date).days > 3660
            or not 1 <= int(limit) <= 12):
        raise ValueError("Enter valid coordinates, a date range of at most ten years, and a limit from 1 to 12.")
    token = os.environ.get("EARTHDATA_TOKEN", "").strip()
    payload = f"{latitude:.5f}:{longitude:.5f}:{start}:{end}:{int(limit)}:{bool(token)}"
    cache_key = "asf-metadata-v2:" + hashlib.sha256(payload.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    result = {"granules": [], "datasets": [], "cached": False, "authenticated_request": bool(token)}
    session = MetadataSession()
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    try:
        for name, dataset in (("NISAR", asf.DATASET.NISAR_SCIENCE_PRODUCTS), ("Sentinel-1", asf.DATASET.SENTINEL1)):
            try:
                products = asf.search(
                    dataset=dataset, intersectsWith=f"POINT({longitude} {latitude})",
                    start=start, end=end, maxResults=int(limit), session=session,
                )
                if getattr(products, "searchComplete", True) is False:
                    raise RuntimeError("Incomplete metadata search")
                granules = []
                for product in products[:int(limit)]:
                    properties = product.properties
                    identifier = str(properties.get("sceneName") or properties.get("fileID") or "")
                    granules.append({
                        "dataset": name, "granule_id": identifier,
                        "acquired_at": str(properties.get("startTime") or ""),
                        "browse_url": _browse_url(properties),
                        "catalog_url": "https://search.asf.alaska.edu/#/?granule=" + quote(identifier, safe=""),
                    })
                result["granules"].extend(granules)
                result["datasets"].append({
                    "name": name, "status": "available" if granules else "empty",
                    "count": len(granules),
                    "reason": ("Metadata found" if granules else (
                        "No NISAR coverage yet for this location and date range."
                        if name == "NISAR" else "No Sentinel-1 granules found for this location and date range."
                    )),
                })
            except Exception:
                result["datasets"].append({
                    "name": name, "status": "unavailable", "count": 0,
                    "reason": "ASF search unavailable. Check service availability and token permissions if configured; coverage is unknown.",
                })
    finally:
        session.headers.pop("Authorization", None)
        session.close()
    cache.set(cache_key, result, 60 if any(
        item["status"] == "unavailable" for item in result["datasets"]
    ) else 900)
    return result