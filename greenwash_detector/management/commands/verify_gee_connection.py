"""Compute an explicit GEE reference check offline; never updates registry verdicts."""

import io
import json
import math
import uuid
from datetime import date

import requests
from PIL import Image
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from greenwash_detector import live_connection
from greenwash_detector.sar_verifier import SarVerifier
from greenwash_detector.satellite_verifier import SatelliteVerifier


def _download_preview(url, destination):
    body = bytearray()
    with requests.get(url, stream=True, timeout=(10, 30)) as response:
        response.raise_for_status()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body) > 2000000:
                raise ValueError("Preview exceeded the 2 MB limit")
    with Image.open(io.BytesIO(body)) as image:
        if image.format != "PNG" or max(image.size) > 1024:
            raise ValueError("Unexpected preview format or dimensions")
        image.verify()
    destination.write_bytes(body)


class Command(BaseCommand):
    help = "Check configured GEE access and cache real optical/SAR reference evidence without changing bond records"

    def add_arguments(self, parser):
        parser.add_argument("--latitude", type=float, default=9.5)
        parser.add_argument("--longitude", type=float, default=76.4)
        parser.add_argument("--before-year", type=int, default=date.today().year - 2)
        parser.add_argument("--after-year", type=int, default=date.today().year - 1)

    def handle(self, *args, **options):
        lat, lon = options["latitude"], options["longitude"]
        before_year, after_year = options["before_year"], options["after_year"]
        if (not math.isfinite(lat) or not math.isfinite(lon)
                or not -90 <= lat <= 90 or not -180 <= lon <= 180
                or not 2018 <= before_year < after_year < date.today().year):
            raise CommandError("Use valid coordinates and completed years with 2018 <= before < after.")
        if not settings.EE_PROJECT_ID:
            raise CommandError("Set EE_PROJECT_ID to the registered Cloud project ID.")
        before, after = f"{before_year}-01-01", f"{after_year}-01-01"
        check_id = uuid.uuid4().hex
        directory = live_connection.CACHE_DIR
        directory.mkdir(parents=True, exist_ok=True)
        try:
            optical = SatelliteVerifier()
            if optical._ee is None:
                raise CommandError("GEE initialization failed. Check the project registration and private credentials.")
            optical._ee.data.setDeadline(45000)
            if optical._ee.Number(1).add(1).getInfo() != 2:
                raise CommandError("GEE scalar check failed.")
            ndvi = optical.get_ndvi_change(lat, lon, before, after, radius_km=2)
            thumbs = optical.generate_thumbnail_urls(lat, lon, before, after)
            if (ndvi.get("source") != "gee" or thumbs.get("source") != "gee"
                    or not thumbs.get("before_url") or not thumbs.get("after_url")):
                raise CommandError("Real optical evidence is unavailable; no synthetic images or values were saved.")
            for period in ("before", "after"):
                _download_preview(thumbs[period + "_url"], directory / f"{check_id}-{period}.png")
            with SarVerifier() as verifier:
                sar = verifier.verify(
                    lat, lon, before, f"{before_year}-04-01",
                    after, f"{after_year}-04-01", "water",
                )
            receipt = {
                "check_id": check_id, "project": settings.EE_PROJECT_ID,
                "checked_at": timezone.now().isoformat(),
                "location": {"latitude": lat, "longitude": lon},
                "before_year": before_year, "after_year": after_year,
                "ndvi": ndvi, "sar": sar,
                "purpose": "Reference-location functional check, not bond verification or a flood/loss backtest.",
                "optical_windows": "NDVI uses 12-month anchor windows; previews use 180-day windows starting January 1.",
            }
            temporary = directory / f"{check_id}.json.part"
            temporary.write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding="utf-8")
            temporary.replace(directory / "latest.json")
        except CommandError:
            raise
        except Exception as error:
            raise CommandError(f"Live check failed ({type(error).__name__}); no credential details are logged.") from None
        self.stdout.write(self.style.SUCCESS("GEE reference check cached; no bond records changed."))
        self.stdout.write(f"Project: {settings.EE_PROJECT_ID}; NDVI source: gee; SAR: {sar['status']}")
        if sar["sar_change_db"] is None:
            self.stdout.write(self.style.WARNING(sar["reason"]))