# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
ai_features/tasks.py — Celery tasks for AI features.

Tasks:
1. refresh_regulatory_updates - Fetch latest regulatory news daily
2. generate_regulatory_alerts - Create alerts for new regulations
"""
import logging
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger("greenlens.ai_tasks")


@shared_task(name="ai_features.refresh_regulatory_updates")
def refresh_regulatory_updates():
    """
    Fetch latest regulatory updates from EU SFDR and SEBI.
    
    Runs daily at 6 AM via Celery Beat.
    
    Returns:
        Result dict with fetch statistics
    """
    from ai_features.regulatory_fetcher import fetch_and_save_regulatory_updates
    
    logger.info("Starting regulatory updates refresh task...")
    
    try:
        result = fetch_and_save_regulatory_updates()
        
        if result["success"]:
            logger.info(
                f"Regulatory updates refresh complete: "
                f"{result['updates_fetched']} fetched, "
                f"{result['updates_saved']} saved"
            )
            
            # Cache last update timestamp
            cache.set("regulatory_last_updated", result["last_updated"], timeout=None)
            
            # Trigger alert generation for new regulations
            if result["updates_saved"] > 0:
                logger.info("Triggering regulatory alert generation...")
                generate_regulatory_alerts.delay()
        else:
            logger.error(f"Regulatory updates refresh failed: {result['error']}")
        
        return result
    
    except Exception as e:
        logger.error(f"Regulatory updates task failed: {e}", exc_info=True)
        return {
            "success": False,
            "updates_fetched": 0,
            "updates_saved": 0,
            "last_updated": None,
            "error": str(e),
        }


@shared_task(name="ai_features.generate_regulatory_alerts")
def generate_regulatory_alerts():
    """
    Generate automated alerts for new regulatory updates.
    
    Runs after refresh_regulatory_updates() completes.
    
    Logic:
    - For each new RegulatoryMonitor entry (created in last 24 hours)
    - Find affected bonds based on regulatory framework:
      * EU regulations → bonds with regulatory_framework='EU_GBS'
      * SEBI regulations → bonds with regulatory_framework='SEBI'
    - Create AutomatedAlert with alert_type='regulatory'
    - Set affected_bonds ManyToMany relation
    - Avoid duplicate alerts
    
    Returns:
        Result dict with alert generation statistics
    """
    from ai_features.models import RegulatoryMonitor, AutomatedAlert
    from data_ingestion.models import GreenBond
    from datetime import timedelta
    
    logger.info("Starting regulatory alert generation task...")
    
    try:
        # Get new regulations from last 24 hours
        cutoff_time = timezone.now() - timedelta(hours=24)
        new_regulations = RegulatoryMonitor.objects.filter(
            created_at__gte=cutoff_time
        ).order_by("-created_at")
        
        if not new_regulations.exists():
            logger.info("No new regulations found in last 24 hours")
            return {
                "success": True,
                "regulations_processed": 0,
                "alerts_created": 0,
                "alerts_skipped": 0,
            }
        
        alerts_created = 0
        alerts_skipped = 0
        
        for regulation in new_regulations:
            # Check if alert already exists for this regulation
            existing_alert = AutomatedAlert.objects.filter(
                alert_type="regulatory",
                title__icontains=regulation.title[:50],  # Match on first 50 chars
            ).first()
            
            if existing_alert:
                logger.info(f"Alert already exists for regulation: {regulation.title}")
                alerts_skipped += 1
                continue
            
            # Determine affected bonds based on regulation type
            affected_bonds = _find_affected_bonds(regulation)
            
            if not affected_bonds:
                logger.warning(f"No affected bonds found for regulation: {regulation.title}")
                alerts_skipped += 1
                continue
            
            # Create alert
            alert = _create_regulatory_alert(regulation, affected_bonds)
            
            if alert:
                alerts_created += 1
                logger.info(
                    f"Created regulatory alert: {alert.title} "
                    f"({affected_bonds.count()} bonds affected)"
                )
            else:
                alerts_skipped += 1
        
        result = {
            "success": True,
            "regulations_processed": new_regulations.count(),
            "alerts_created": alerts_created,
            "alerts_skipped": alerts_skipped,
        }
        
        logger.info(
            f"Regulatory alert generation complete: "
            f"{alerts_created} created, {alerts_skipped} skipped"
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Regulatory alert generation failed: {e}", exc_info=True)
        return {
            "success": False,
            "regulations_processed": 0,
            "alerts_created": 0,
            "alerts_skipped": 0,
            "error": str(e),
        }


def _find_affected_bonds(regulation):
    """
    Find bonds affected by a regulatory update.
    
    Args:
        regulation: RegulatoryMonitor instance
    
    Returns:
        QuerySet of affected GreenBond instances
    """
    from data_ingestion.models import GreenBond
    
    # Map regulation types to regulatory frameworks
    regulation_mapping = {
        "eu_sfdr": "EU_GBS",
        "eu_taxonomy": "EU_GBS",
        "sebi_brsr": "SEBI",
        "rbi_climate": "SEBI",  # RBI affects Indian bonds
        "sec_climate": "OTHER",  # SEC affects US bonds (use OTHER for now)
    }
    
    framework = regulation_mapping.get(regulation.regulation_type)
    
    if not framework:
        logger.warning(f"Unknown regulation type: {regulation.regulation_type}")
        return GreenBond.objects.none()
    
    # Find bonds with matching regulatory framework
    affected_bonds = GreenBond.objects.filter(regulatory_framework=framework)
    
    # Additional filtering for specific regulation types
    if regulation.regulation_type in ["sebi_brsr", "rbi_climate"]:
        # Also filter by country for Indian regulations
        affected_bonds = affected_bonds.filter(country="India")
    elif regulation.regulation_type in ["eu_sfdr", "eu_taxonomy"]:
        # Filter by EU countries
        eu_countries = [
            "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic",
            "Denmark", "Estonia", "Finland", "France", "Germany", "Greece", "Hungary",
            "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta",
            "Netherlands", "Poland", "Portugal", "Romania", "Slovakia", "Slovenia",
            "Spain", "Sweden"
        ]
        affected_bonds = affected_bonds.filter(country__in=eu_countries)
    
    return affected_bonds


def _create_regulatory_alert(regulation, affected_bonds):
    """
    Create an AutomatedAlert for a regulatory update.
    
    Args:
        regulation: RegulatoryMonitor instance
        affected_bonds: QuerySet of affected GreenBond instances
    
    Returns:
        AutomatedAlert instance or None
    """
    from ai_features.models import AutomatedAlert
    from datetime import datetime
    
    try:
        # Calculate days until effective date
        days_until_effective = (regulation.effective_date - timezone.now().date()).days
        
        # Determine urgency
        if days_until_effective < 30:
            urgency = "URGENT"
        elif days_until_effective < 90:
            urgency = "HIGH"
        else:
            urgency = "MEDIUM"
        
        # Build description
        description = (
            f"{regulation.get_regulation_type_display()} update: {regulation.description}\n\n"
            f"Effective Date: {regulation.effective_date.strftime('%B %d, %Y')} "
            f"({days_until_effective} days from now)\n\n"
        )
        
        if regulation.compliance_required:
            description += f"⚠️ Compliance Required: {regulation.action_required or 'Review and update documentation'}\n\n"
        
        description += f"Impact: {regulation.impact_description}\n\n"
        description += f"Affected Bonds: {affected_bonds.count()} bonds in your portfolio"
        
        # Create alert
        alert = AutomatedAlert.objects.create(
            alert_type="regulatory",
            title=f"{urgency}: {regulation.title}",
            description=description,
            alert_data={
                "regulation_id": regulation.id,
                "regulation_type": regulation.regulation_type,
                "announcement_date": regulation.announcement_date.isoformat(),
                "effective_date": regulation.effective_date.isoformat(),
                "days_until_effective": days_until_effective,
                "compliance_required": regulation.compliance_required,
                "action_required": regulation.action_required,
                "affected_bonds_count": affected_bonds.count(),
                "source_url": regulation.source_url,
                "urgency": urgency,
            },
            status="pending",
            delivery_method="dashboard",
        )
        
        # Set affected bonds (ManyToMany)
        alert.affected_bonds.set(affected_bonds)
        
        # Update regulation with affected bonds count
        regulation.affected_bonds_count = affected_bonds.count()
        regulation.save(update_fields=["affected_bonds_count"])
        
        return alert
    
    except Exception as e:
        logger.error(f"Failed to create regulatory alert: {e}", exc_info=True)
        return None
