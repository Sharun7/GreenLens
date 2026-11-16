"""Evidence-backed review signals for the four-step GreenLens workflow."""

from django.db.models import OuterRef, Subquery
from django.conf import settings

from data_ingestion.models import GreenBond
from greenwash_detector.models import GreenwashFlag
from pricing_analysis.models import PricingGap
from risk_scoring.models import PCRScore


def latest_records(model, timestamp):
    latest = model.objects.filter(bond_id=OuterRef("bond_id")).order_by(
        "-" + timestamp, "-pk",
    ).values("pk")[:1]
    return model.objects.filter(pk=Subquery(latest))


def has_satellite_evidence(flag):
    metadata = flag.raw_ee_metadata or {}
    return (
        flag.verification_status == "verifiable"
        and not flag.model_version.startswith("bootstrap")
        and metadata.get("source") not in ("synthetic", "deployment_bootstrap")
        and metadata.get("method") != "synthetic"
        and (metadata.get("source") == "gee"
             or metadata.get("collection") == "COPERNICUS/S2_SR_HARMONIZED")
    )


def build_review_alerts(limit=10):
    alerts = []
    flags = latest_records(GreenwashFlag, "checked_at").filter(
        is_inconsistent=True,
    ).select_related("bond").order_by("-checked_at")
    for flag in flags.iterator(chunk_size=100):
        if not has_satellite_evidence(flag):
            continue
        alerts.append({
            "kind": "satellite", "bond_id": flag.bond.bond_id,
            "country": flag.bond.country, "hazard_type": "Satellite review",
            "description": "Stored satellite observations conflict with the claimed project category. Analyst review is required; this is not proof of greenwashing.",
            "impact": f"NDVI change: {flag.ndvi_change:+.3f}", "color": "#E24B4A",
            "affected_bonds": [flag.bond.issuer_name],
            "source": "gee", "checked_at": flag.checked_at.isoformat(),
        })
        if len(alerts) >= limit:
            return alerts
    gaps = latest_records(PricingGap, "checked_at").filter(
        is_mispriced=True,
    ).select_related("bond").order_by("-checked_at")[:limit - len(alerts)]
    for gap in gaps:
        alerts.append({
            "kind": "pricing", "bond_id": gap.bond.bond_id,
            "country": gap.bond.country, "hazard_type": "Estimated pricing review",
            "description": "The stored spread estimate differs from the model-implied spread beyond its configured threshold. This is a research estimate, not an observed trade or a trading recommendation.",
            "impact": f"Estimated gap: {gap.gap_bps:+.1f} bps", "color": "#EF9F27",
            "affected_bonds": [gap.bond.issuer_name],
            "source": gap.data_source, "checked_at": gap.checked_at.isoformat(),
        })
    return alerts


def build_workflow_status():
    from risk_scoring.feature_pipeline import FeatureEngineeringPipeline

    total = GreenBond.objects.count()
    observed = sum(
        has_satellite_evidence(flag)
        for flag in latest_records(GreenwashFlag, "checked_at").iterator(chunk_size=200)
    )
    scores = latest_records(PCRScore, "scored_at")
    demo_scores = non_demo_scores = 0
    for row in scores.values("model_version", "feature_metadata").iterator(chunk_size=200):
        metadata = row["feature_metadata"] if isinstance(row["feature_metadata"], dict) else {}
        demo = row["model_version"].startswith("bootstrap") or metadata.get("provenance", {}).get("primary_status") == "demo"
        demo_scores += demo
        non_demo_scores += not demo
    pricing = latest_records(PricingGap, "checked_at").count()
    alerts = build_review_alerts()
    return {
        "total_bonds": total,
        "satellite": {
            "observed_count": observed, "without_evidence": max(0, total - observed),
            "label": "Satellite observations stored" if observed else "Awaiting real imagery",
        },
        "risk": {
            "feature_count": len(FeatureEngineeringPipeline.NUMERIC_FEATURES)
                + len(FeatureEngineeringPipeline.CATEGORY_FEATURES),
            "demo_count": demo_scores, "non_demo_count": non_demo_scores,
            "label": "Non-demo scores stored" if non_demo_scores else (
                "Demo estimates only" if demo_scores else "Not scored"
            ),
            "training_target": "hazard-derived proxy, not observed losses",
        },
        "pricing": {
            "stored_count": pricing,
            "label": "Spread estimates available" if pricing else "Not computed",
            "individual_market_yields_connected": False,
        },
        "alerts": {
            "review_count": len(alerts),
            "label": "Review signals available" if alerts else "No stored review signals",
            "weather_forecasts_connected": False,
        },
        "automation_note": (
            "A task broker is configured; worker and scheduler availability has not been verified."
            if settings.CELERY_BROKER_URL else
            "Automatic scanning is not running: scheduled jobs need a configured broker, worker, and scheduler."
        ),
    }