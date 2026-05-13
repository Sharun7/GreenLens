# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_management/tasks.py — Celery tasks for automatic monitoring.

Periodic tasks:
1. API health monitoring (every 5 minutes)
2. Model drift detection (daily)
3. Data quality checks (daily)
4. Regulatory updates scraping (weekly)
"""
import logging
from celery import shared_task

logger = logging.getLogger("greenlens.risk_tasks")


@shared_task(name="risk_management.monitor_system_health")
def monitor_system_health():
    """
    Monitor system health (APIs, model drift, data quality).
    
    Runs every 5 minutes via Celery Beat.
    """
    from risk_management.monitoring import run_all_monitors
    
    logger.info("Starting system health monitoring task...")
    
    try:
        results = run_all_monitors()
        logger.info(f"System health monitoring complete: {results}")
        return results
    except Exception as e:
        logger.error(f"System health monitoring failed: {e}", exc_info=True)
        raise


@shared_task(name="risk_management.monitor_api_health")
def monitor_api_health():
    """
    Monitor external API health (Google Earth Engine, World Bank, Yahoo Finance).
    
    Runs every 30 minutes via Celery Beat.
    Auto-creates IncidentLog if any API fails.
    """
    from risk_management.monitoring import APIHealthMonitor
    
    logger.info("Starting API health monitoring task...")
    
    try:
        monitor = APIHealthMonitor()
        results = monitor.check_all_apis()
        
        # Count failures
        failed_apis = [name for name, status in results.items() if not status["healthy"]]
        
        if failed_apis:
            logger.warning(f"API health check found {len(failed_apis)} failures: {failed_apis}")
        else:
            logger.info("All APIs are healthy")
        
        return {
            "total_apis": len(results),
            "failed_apis": failed_apis,
            "results": results,
        }
    
    except Exception as e:
        logger.error(f"API health monitoring failed: {e}", exc_info=True)
        raise


@shared_task(name="risk_management.detect_model_drift")
def detect_model_drift():
    """
    Detect model drift by analyzing regional prediction variance.
    
    Runs weekly via Celery Beat.
    Creates ModelDriftAlert if variance exceeds thresholds:
    - European bonds: variance > 15%
    - Emerging markets: variance > 25%
    """
    from risk_management.monitoring import ModelDriftMonitor
    
    logger.info("Starting model drift detection task...")
    
    try:
        monitor = ModelDriftMonitor()
        results = monitor.check_model_drift()
        
        if results is None:
            logger.info("Insufficient data for model drift detection")
            return {"status": "insufficient_data"}
        
        if results.get("drift_detected"):
            logger.warning(f"Model drift detected: {results}")
        else:
            logger.info("No model drift detected")
        
        return results
    
    except Exception as e:
        logger.error(f"Model drift detection failed: {e}", exc_info=True)
        raise


@shared_task(name="risk_management.check_data_quality")
def check_data_quality():
    """
    Check data quality across all data sources.
    
    Runs daily via Celery Beat.
    Auto-updates DataQualityMetric records:
    - Location confidence (country-level vs precise)
    - Greenwash verification coverage
    - Pricing data freshness (older than 7 days)
    """
    from risk_management.monitoring import DataQualityMonitor
    
    logger.info("Starting data quality check task...")
    
    try:
        monitor = DataQualityMonitor()
        results = monitor.check_data_quality()
        
        quality_score = results.get("overall_quality_score", 0)
        
        if quality_score < 70:
            logger.warning(f"Data quality below threshold: {quality_score:.1f}%")
        else:
            logger.info(f"Data quality check complete: {quality_score:.1f}%")
        
        return results
    
    except Exception as e:
        logger.error(f"Data quality check failed: {e}", exc_info=True)
        raise


@shared_task(name="risk_management.scrape_regulatory_updates")
def scrape_regulatory_updates():
    """
    Scrape regulatory updates from official sources.
    
    Runs weekly via Celery Beat.
    """
    from ai_features.regulatory_scraper import scrape_and_save_regulatory_updates, load_manual_regulatory_updates
    
    logger.info("Starting regulatory updates scraping task...")
    
    try:
        # Try scraping
        saved_count = scrape_and_save_regulatory_updates()
        
        # If scraping failed, load manual updates
        if saved_count == 0:
            logger.info("Scraping returned no updates, loading manual fallback...")
            saved_count = load_manual_regulatory_updates()
        
        logger.info(f"Regulatory updates task complete. Saved {saved_count} updates.")
        return {"saved_count": saved_count}
    
    except Exception as e:
        logger.error(f"Regulatory updates scraping failed: {e}", exc_info=True)
        # Load manual updates as fallback
        try:
            saved_count = load_manual_regulatory_updates()
            logger.info(f"Loaded {saved_count} manual regulatory updates as fallback")
            return {"saved_count": saved_count, "fallback": True}
        except Exception as fallback_error:
            logger.error(f"Manual regulatory updates also failed: {fallback_error}")
            raise


@shared_task(name="risk_management.cleanup_old_incidents")
def cleanup_old_incidents():
    """
    Clean up old resolved incidents (older than 90 days).
    
    Runs daily via Celery Beat.
    """
    from django.utils import timezone
    from datetime import timedelta
    from risk_management.models import IncidentLog
    
    logger.info("Starting old incidents cleanup task...")
    
    try:
        cutoff_date = timezone.now() - timedelta(days=90)
        
        deleted_count, _ = IncidentLog.objects.filter(
            status="resolved",
            resolved_at__lt=cutoff_date,
        ).delete()
        
        logger.info(f"Cleaned up {deleted_count} old resolved incidents")
        return {"deleted_count": deleted_count}
    
    except Exception as e:
        logger.error(f"Incident cleanup failed: {e}", exc_info=True)
        raise


@shared_task(name="risk_management.generate_daily_monitoring_report")
def generate_daily_monitoring_report():
    """
    Generate daily monitoring report with all metrics.
    
    Runs daily at 8 AM via Celery Beat.
    """
    from risk_management.monitoring import run_all_monitors
    from django.core.mail import send_mail
    from django.conf import settings
    
    logger.info("Generating daily monitoring report...")
    
    try:
        results = run_all_monitors()
        
        # Format report
        report = f"""
GreenLens Daily Monitoring Report
{'-' * 50}

API HEALTH:
{format_api_health(results.get('api_health', {}))}

MODEL DRIFT:
{format_model_drift(results.get('model_drift', {}))}

DATA QUALITY:
{format_data_quality(results.get('data_quality', {}))}

Report generated at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        
        # Send email (if configured)
        if hasattr(settings, 'MONITORING_EMAIL_RECIPIENTS'):
            send_mail(
                subject=f"GreenLens Daily Monitoring Report - {timezone.now().date()}",
                message=report,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=settings.MONITORING_EMAIL_RECIPIENTS,
                fail_silently=True,
            )
            logger.info("Daily monitoring report sent via email")
        
        logger.info("Daily monitoring report generated successfully")
        return {"report": report}
    
    except Exception as e:
        logger.error(f"Daily monitoring report generation failed: {e}", exc_info=True)
        raise


def format_api_health(api_health: dict) -> str:
    """Format API health results for report."""
    if not api_health:
        return "No data available"
    
    lines = []
    for api_name, status in api_health.items():
        health_status = "✓ HEALTHY" if status.get("healthy") else "✗ DOWN"
        response_time = status.get("response_time_ms", 0)
        lines.append(f"  {api_name}: {health_status} ({response_time}ms)")
    
    return "\n".join(lines)


def format_model_drift(drift_data: dict) -> str:
    """Format model drift results for report."""
    if not drift_data:
        return "No data available"
    
    if not drift_data.get("drift_detected"):
        return "  ✓ No drift detected"
    
    return f"""  ✗ DRIFT DETECTED
  Mean shift: {drift_data.get('mean_shift', 0):.2f}
  Stddev shift: {drift_data.get('stddev_shift', 0):.2f}
  Recent mean: {drift_data.get('recent_mean', 0):.2f}
  Baseline mean: {drift_data.get('baseline_mean', 0):.2f}"""


def format_data_quality(quality_data: dict) -> str:
    """Format data quality results for report."""
    if not quality_data:
        return "No data available"
    
    return f"""  Overall Quality Score: {quality_data.get('overall_quality_score', 0):.1f}%
  Coordinate Completeness: {quality_data.get('coord_completeness_pct', 0):.1f}%
  Hazard Data Completeness: {quality_data.get('hazard_completeness_pct', 0):.1f}%
  PCRS Completeness: {quality_data.get('pcrs_completeness_pct', 0):.1f}%
  Status: {quality_data.get('status', 'unknown').upper()}"""
