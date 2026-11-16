"""Local coastline geometry for PCRS; downloads happen only by explicit command."""

import math
from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile

import requests


COASTLINE_URL = "https://naturalearth.s3.amazonaws.com/50m_physical/ne_50m_coastline.zip"
COASTLINE_PATH = Path(__file__).resolve().parents[1] / "data" / "cache" / "ne_50m_coastline.zip"


def download_coastline():
    if COASTLINE_PATH.is_file():
        return coastline_status()
    COASTLINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = COASTLINE_PATH.with_suffix(".zip.part")
    try:
        with requests.get(COASTLINE_URL, stream=True, timeout=(10, 30)) as response:
            response.raise_for_status()
            size = 0
            with temporary.open("wb") as output:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 8000000:
                        raise ValueError("Coastline download exceeded the 8 MB safety limit")
                    output.write(chunk)
        with ZipFile(temporary) as archive:
            names = {Path(name).name for name in archive.namelist()}
            required = {"ne_50m_coastline" + suffix for suffix in (".shp", ".shx", ".dbf", ".prj")}
            if not required.issubset(names):
                raise ValueError("Coastline archive is missing required geometry files")
            if sum(item.file_size for item in archive.infolist()) > 40000000:
                raise ValueError("Coastline archive is too large to load safely")
        temporary.replace(COASTLINE_PATH)
        _coastline_index.cache_clear()
    finally:
        temporary.unlink(missing_ok=True)
    return coastline_status()


def coastline_status():
    available = COASTLINE_PATH.is_file()
    return {
        "available": available,
        "method": "Natural Earth 1:50m coastline" if available else "Legacy reference-point heuristic",
        "source_url": COASTLINE_URL,
    }


@lru_cache(maxsize=1)
def _coastline_index():
    import fiona
    from shapely.geometry import shape
    from shapely.strtree import STRtree

    with fiona.open("zip://" + COASTLINE_PATH.as_posix()) as source:
        geometries = [shape(feature["geometry"]) for feature in source]
    return geometries, STRtree(geometries)


def near_coastline(lat, lon, threshold_km=200.0):
    """Return a coastline flag, or None when the optional local dataset is absent."""
    if not COASTLINE_PATH.is_file():
        return None
    from pyproj import Transformer
    from shapely.geometry import Point, box
    from shapely.ops import transform, unary_union

    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and threshold_km > 0):
        raise ValueError("Invalid coastline query")
    latitude_span = threshold_km / 110.574 + 0.1
    longitude_span = min(180, threshold_km / (111.32 * max(0.001, math.cos(math.radians(lat)))) + 0.1)
    if abs(lat) + latitude_span >= 90:
        longitude_span = 180
    south, north = max(-90, lat - latitude_span), min(90, lat + latitude_span)
    west, east = lon - longitude_span, lon + longitude_span
    if longitude_span == 180:
        windows = [box(-180, south, 180, north)]
    elif west < -180:
        windows = [box(-180, south, east, north), box(west + 360, south, 180, north)]
    elif east > 180:
        windows = [box(west, south, 180, north), box(-180, south, east - 360, north)]
    else:
        windows = [box(west, south, east, north)]
    region = unary_union(windows)
    geometries, index = _coastline_index()
    candidates = index.query(region)
    if len(candidates) == 0:
        return False
    transformer = Transformer.from_crs(
        "EPSG:4326", f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m",
        always_xy=True,
    )
    origin = Point(0, 0)
    for candidate in candidates:
        geometry = geometries[int(candidate)].intersection(region)
        projected = transform(transformer.transform, geometry)
        if origin.distance(projected) <= threshold_km * 1000:
            return True
    return False