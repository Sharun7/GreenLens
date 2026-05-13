# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
data_ingestion/tasks.py — Celery tasks for climate hazard data ingestion.
"""
import logging
import os
from pathlib import Path

from celery import shared_task

logger = logging.getLogger("greenlens.ingestion_tasks")


@shared_task(
    name="data_ingestion.fetch_climate_hazards_for_bond",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def fetch_climate_hazards_for_bond(self, bond_id: int):
    """
    Fetch NASA climate hazard data for a single bond and save to ClimateHazardData.
    """
    from data_ingestion.models import GreenBond, ClimateHazardData
    from data_ingestion.nasa_fetcher import NASAClimateDataFetcher

    try:
        bond = GreenBond.objects.get(pk=bond_id)
    except GreenBond.DoesNotExist:
        logger.error("fetch_climate_hazards: bond %d not found", bond_id)
        return

    if bond.lat is None or bond.lon is None:
        logger.warning("Bond %d has no coordinates — skipping hazard fetch", bond_id)
        return

    try:
        fetcher = NASAClimateDataFetcher()
        hazards = fetcher.get_all_hazards(bond.lat, bond.lon)
        from datetime import date

        # Category 19 — India-specific climate enhancements
        india_hazards = {}
        if bond.country == "India":
            try:
                from risk_scoring.india_climate_enhancer import IndiaClimateEnhancer
                enhancer = IndiaClimateEnhancer()
                
                # Extract state from project description or use None
                state = None  # TODO: Add state field to GreenBond model
                
                india_hazards = {
                    "monsoon_risk_index": enhancer.get_monsoon_risk(bond.lat, bond.lon, state),
                    "cyclone_risk_index": enhancer.get_cyclone_risk(bond.lat, bond.lon, state),
                    "heat_wave_risk_index": enhancer.get_heat_wave_risk(bond.lat, bond.lon, state),
                }
                logger.info(
                    "India-specific hazards calculated for bond %d: monsoon=%.2f cyclone=%.2f heat_wave=%.2f",
                    bond_id,
                    india_hazards["monsoon_risk_index"],
                    india_hazards["cyclone_risk_index"],
                    india_hazards["heat_wave_risk_index"],
                )
            except Exception as india_exc:
                logger.warning("Failed to calculate India-specific hazards for bond %d: %s", bond_id, india_exc)
                india_hazards = {}

        ClimateHazardData.objects.update_or_create(
            bond=bond,
            defaults={
                "flood_risk_index": hazards["flood_risk_index"],
                "drought_spei": hazards["drought_spei"],
                "heat_stress_index": hazards["heat_stress_index"],
                "source": "nasa",
                "data_date": date.today(),
                **india_hazards,  # Add India-specific hazards if available
            },
        )
        logger.info(
            "Hazards saved for bond %d: flood=%.2f drought=%.2f heat=%.2f",
            bond_id,
            hazards["flood_risk_index"],
            hazards["drought_spei"],
            hazards["heat_stress_index"],
        )
        return f"Bond {bond_id}: hazards fetched OK"

    except Exception as exc:
        logger.error("Error fetching hazards for bond %d: %s", bond_id, exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(name="data_ingestion.sync_bond_registry")
def sync_bond_registry():
    """
    Periodic task to reconcile registry status with the latest manually supplied
    source file when available.

    GreenLens does not yet auto-discover new bonds from a live registry API.
    If `CBI_BOND_CSV_PATH` is configured and exists, this task runs the manual
    loader against that file as a semi-automated sync step. Otherwise it
    honestly falls back to marking existing records as re-verified.
    """
    from django.core.management import call_command
    from django.utils import timezone
    from data_ingestion.models import GreenBond
    import time

    logger.info("Starting scheduled bond registry sync...")
    start_time = time.time()
    csv_path = os.environ.get("CBI_BOND_CSV_PATH", "").strip()

    try:
        if csv_path and Path(csv_path).exists():
            call_command("load_cbi_bonds", file=csv_path, latest_only=True)
            logger.info("Registry sync imported data from %s", csv_path)
        else:
            logger.info(
                "CBI_BOND_CSV_PATH is not configured. Skipping auto-import and "
                "marking existing bonds as manually verified."
            )

        now = timezone.now()
        updated = GreenBond.objects.all().update(last_synced_at=now)
        elapsed = time.time() - start_time
        logger.info(
            "Bond registry sync completed successfully in %.2f seconds. Updated %d bonds.",
            elapsed,
            updated,
        )
        return f"Sync complete. Updated {updated} bonds in {elapsed:.2f}s"

    except Exception as exc:
        logger.error("Scheduled bond registry sync failed: %s", exc, exc_info=True)
        raise


@shared_task(name="data_ingestion.refresh_all_climate_hazards")
def refresh_all_climate_hazards():
    """
    Scheduled task: re-fetch NASA hazard data for all geocoded bonds.
    Run monthly (configured in celery beat schedule).
    """
    from data_ingestion.models import GreenBond

    bonds = GreenBond.objects.filter(
        lat__isnull=False,
        lon__isnull=False,
    ).values_list("id", flat=True)

    count = 0
    for bond_id in bonds:
        fetch_climate_hazards_for_bond.delay(bond_id)
        count += 1

    logger.info("refresh_all_climate_hazards: queued %d bonds", count)
    return f"Queued {count} hazard fetch tasks"
