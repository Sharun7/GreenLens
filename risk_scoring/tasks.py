"""
risk_scoring/tasks.py — Celery tasks for PCRS scoring.
"""
import logging

from celery import shared_task

logger = logging.getLogger("greenlens.scoring_tasks")


@shared_task(
    name="risk_scoring.score_single_bond",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def score_single_bond(self, bond_pk: int) -> dict:
    """
    Score a single bond and persist the PCRScore record.
    Called via: score_single_bond.delay(bond_pk)
    """
    try:
        from risk_scoring.ml_engine import PCRSPredictor
        predictor = PCRSPredictor()
        result = predictor.predict(bond_pk)
        logger.info("score_single_bond: bond_pk=%d score=%.1f", bond_pk, result["score"])
        return result
    except FileNotFoundError as exc:
        logger.error("Model not trained yet: %s", exc)
        return {"error": str(exc), "bond_pk": bond_pk}
    except Exception as exc:
        logger.error("Error scoring bond %d: %s", bond_pk, exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="risk_scoring.score_all_bonds",
    bind=True,
    soft_time_limit=7200,    # 2 hours
)
def score_all_bonds(self) -> str:
    """
    Scheduled task: (re)score all bonds in the database.
    Run weekly via django-celery-beat.
    """
    from data_ingestion.models import GreenBond
    from risk_scoring.ml_engine import PCRSPredictor

    try:
        predictor = PCRSPredictor()
    except FileNotFoundError:
        msg = "score_all_bonds: model not trained yet — run train_pcrs_model first"
        logger.error(msg)
        return msg

    bond_pks = list(GreenBond.objects.values_list("pk", flat=True))
    total = len(bond_pks)
    logger.info("score_all_bonds: scoring %d bonds", total)

    success = errors = 0
    for pk in bond_pks:
        try:
            predictor.predict(pk)
            success += 1
        except Exception as exc:
            errors += 1
            logger.error("Scoring failed for bond %d: %s", pk, exc)

    summary = f"score_all_bonds: {success}/{total} OK, {errors} errors"
    logger.info(summary)
    return summary


@shared_task(name="risk_scoring.train_model_task")
def train_model_task() -> dict:
    """
    On-demand task to re-train the PCRS model.
    """
    from risk_scoring.ml_engine import train_pcrs_model
    metrics = train_pcrs_model()
    logger.info("train_model_task complete: %s", metrics)
    return metrics
