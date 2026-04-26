"""
greenwash_detector/tasks.py — Celery tasks for satellite greenwash detection.
"""
import logging

from celery import shared_task

logger = logging.getLogger("greenlens.greenwash_tasks")


@shared_task(
    name="greenwash_detector.check_single_bond",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    soft_time_limit=300,  # 5 min — GEE calls can be slow
)
def check_single_bond(self, bond_pk: int) -> dict:
    """
    Run greenwash detection for a single bond and persist the GreenwashFlag.
    Called via: check_single_bond.delay(bond_pk)
    """
    from data_ingestion.models import GreenBond
    from greenwash_detector.models import GreenwashFlag
    from greenwash_detector.detection_engine import GreenwashDetector

    try:
        bond = GreenBond.objects.get(pk=bond_pk)
    except GreenBond.DoesNotExist:
        logger.error("check_single_bond: bond %d not found", bond_pk)
        return {"error": f"Bond {bond_pk} not found"}

    try:
        detector = GreenwashDetector()
        result = detector.check_bond(bond)
        flag, created = GreenwashFlag.objects.update_or_create(
            bond=bond,
            defaults={k: v for k, v in result.items() if k != "bond"},
        )
        action = "created" if created else "updated"
        logger.info(
            "check_single_bond: bond %d %s — inconsistent=%s confidence=%.3f",
            bond_pk,
            action,
            flag.is_inconsistent,
            float(flag.confidence or 0),
        )
        return {
            "bond_pk": bond_pk,
            "bond_id": bond.bond_id,
            "is_inconsistent": flag.is_inconsistent,
            "confidence": float(flag.confidence or 0),
            "satellite_land_use": flag.satellite_land_use,
            "ndvi_change": float(flag.ndvi_change or 0),
        }
    except Exception as exc:
        logger.error("check_single_bond error for bond %d: %s", bond_pk, exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="greenwash_detector.check_all_bonds",
    bind=True,
    soft_time_limit=14400,  # 4-hour ceiling — dispatches sub-tasks, doesn't block
)
def check_all_bonds(self) -> str:
    """
    Scheduled task: queue greenwash detection for all geocoded bonds.
    Dispatches individual check_single_bond tasks so each runs with its own retry/timeout.
    Run weekly via django-celery-beat (Monday 04:00 UTC).
    """
    from data_ingestion.models import GreenBond

    bond_pks = list(
        GreenBond.objects.filter(
            lat__isnull=False,
            lon__isnull=False,
        ).values_list("pk", flat=True)
    )

    total = len(bond_pks)
    logger.info("check_all_bonds: queuing %d bonds for greenwash check", total)

    for pk in bond_pks:
        check_single_bond.delay(pk)

    summary = f"check_all_bonds: queued {total} greenwash detection tasks"
    logger.info(summary)
    return summary
