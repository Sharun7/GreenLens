# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_management/monitoring.py — Automatic system monitoring and failure detection.

Implements real-time monitoring of:
1. API Health Monitor (every 30 minutes) - GEE, World Bank, Yahoo Finance
2. Model Drift Detector (weekly) - Regional variance analysis
3. Data Quality Auto-checker (daily) - Location confidence, greenwash flags, pricing gaps
"""
import logging
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from django.utils import timezone
from django.db.models import Avg, Count, StdDev, Variance, Q
from django.core.cache import cache

from risk_management.models import (
    SystemFailureScenario,
    ModelDriftAlert,
    DataQualityMetric,
    IncidentLog,
)
from data_ingestion.models import GreenBond
from risk_scoring.models import PCRScore
from greenwash_detector.models import GreenwashFlag
from pricing_analysis.models import PricingGap

logger = logging.getLogger("greenlens.monitoring")


class APIHealthMonitor:
    """
    Monitor external API health and create failure scenarios automatically.
    
    Runs every 30 minutes via Celery Beat.
    """
    
    def check_all_apis(self) -> Dict[str, dict]:
        """
        Check health of all external APIs.
        
        Returns:
            Dict with API name as key and status dict as value
        """
        results = {}
        
        # 1. Google Earth Engine
        results["google_earth_engine"] = self._check_google_earth_engine()
        
        # 2. World Bank Climate Change Knowledge Portal (CCKP)
        results["world_bank_cckp"] = self._check_world_bank_cckp()
        
        # 3. Yahoo Finance
        results["yahoo_finance"] = self._check_yahoo_finance()
        
        # Auto-create IncidentLog if any API fails
        for api_name, status in results.items():
            if not status["healthy"]:
                self._create_incident_log(api_name, status)
        
        return results
    
    def _check_google_earth_engine(self) -> dict:
        """
        Check Google Earth Engine API health.
        
        Method: Try ee.Initialize()
        """
        start_time = time.time()
        
        try:
            import ee
            
            # Try to initialize
            ee.Initialize()
            
            response_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                "healthy": True,
                "response_time_ms": response_time_ms,
                "status_code": 200,
                "error": None,
                "method": "ee.Initialize()",
            }
        
        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                "healthy": False,
                "response_time_ms": response_time_ms,
                "status_code": 0,
                "error": str(e),
                "method": "ee.Initialize()",
            }
    
    def _check_world_bank_cckp(self) -> dict:
        """
        Check World Bank Climate Change Knowledge Portal API.
        
        Method: GET request to CCKP endpoint
        """
        # World Bank CCKP API endpoint
        url = "https://climateknowledgeportal.worldbank.org/api/data/get-download-data/projection/tas/annual/2020_2039/India"
        
        start_time = time.time()
        
        try:
            response = requests.get(url, timeout=10)
            response_time_ms = int((time.time() - start_time) * 1000)
            
            healthy = response.status_code < 500
            
            return {
                "healthy": healthy,
                "response_time_ms": response_time_ms,
                "status_code": response.status_code,
                "error": None if healthy else f"HTTP {response.status_code}",
                "method": "GET request",
            }
        
        except requests.exceptions.Timeout:
            return {
                "healthy": False,
                "response_time_ms": int((time.time() - start_time) * 1000),
                "status_code": 0,
                "error": "Timeout",
                "method": "GET request",
            }
        
        except requests.exceptions.ConnectionError:
            return {
                "healthy": False,
                "response_time_ms": int((time.time() - start_time) * 1000),
                "status_code": 0,
                "error": "Connection refused",
                "method": "GET request",
            }
        
        except Exception as e:
            return {
                "healthy": False,
                "response_time_ms": int((time.time() - start_time) * 1000),
                "status_code": 0,
                "error": str(e),
                "method": "GET request",
            }
    
    def _check_yahoo_finance(self) -> dict:
        """
        Check Yahoo Finance API health.
        
        Method: yfinance.download test
        """
        start_time = time.time()
        
        try:
            import yfinance as yf
            
            # Try to download a small amount of data
            ticker = yf.Ticker("AAPL")
            data = ticker.history(period="1d")
            
            response_time_ms = int((time.time() - start_time) * 1000)
            
            healthy = len(data) > 0
            
            return {
                "healthy": healthy,
                "response_time_ms": response_time_ms,
                "status_code": 200 if healthy else 500,
                "error": None if healthy else "No data returned",
                "method": "yfinance.download test",
            }
        
        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                "healthy": False,
                "response_time_ms": response_time_ms,
                "status_code": 0,
                "error": str(e),
                "method": "yfinance.download test",
            }
    
    def _create_incident_log(self, api_name: str, status: dict):
        """
        Auto-create IncidentLog if API fails.
        """
        # Check if incident already exists for today
        today = timezone.now().date()
        existing = IncidentLog.objects.filter(
            incident_type="api_failure",
            affected_component=api_name,
            detected_at__date=today,
            status__in=["investigating", "identified"],
        ).first()
        
        if existing:
            # Update existing incident
            existing.occurrence_count += 1
            existing.save()
            logger.warning(f"API failure incident updated: {api_name} (occurrence #{existing.occurrence_count})")
        else:
            # Create new incident
            incident = IncidentLog.objects.create(
                incident_type="api_failure",
                severity="high" if api_name in ["google_earth_engine", "world_bank_cckp"] else "medium",
                title=f"{api_name.replace('_', ' ').title()} API Failure",
                description=f"API health check failed: {status['error']}. Response time: {status['response_time_ms']}ms",
                affected_component=api_name,
                status="investigating",
                occurrence_count=1,
            )
            
            logger.error(f"API failure incident created: {api_name}")
            
            # Also create failure scenario
            self._create_failure_scenario(api_name, status)
    
    def _create_failure_scenario(self, api_name: str, status: dict):
        """
        Create or update failure scenario for API outage.
        """
        scenario_name = f"{api_name.replace('_', ' ').title()} API Down"
        
        # Check if scenario already exists and is recent
        existing = SystemFailureScenario.objects.filter(
            name=scenario_name,
            mitigation_status__in=["active", "monitoring"],
            created_at__gte=timezone.now() - timedelta(hours=1),
        ).first()
        
        if existing:
            # Update existing scenario
            existing.last_occurred_at = timezone.now()
            existing.occurrence_count += 1
            existing.save()
            logger.warning(f"API failure scenario updated: {scenario_name} (occurrence #{existing.occurrence_count})")
        else:
            # Create new scenario
            fallback_map = {
                "google_earth_engine": "Use Copernicus API → Cached NDVI → Mark as unverifiable",
                "world_bank_cckp": "Use NASA Earthdata → Historical averages → Reduced confidence",
                "yahoo_finance": "Use cached yield data → Manual pricing updates",
            }
            
            affected_modules_map = {
                "google_earth_engine": ["greenwash_detector", "risk_scoring"],
                "world_bank_cckp": ["data_ingestion", "risk_scoring"],
                "yahoo_finance": ["pricing_analysis"],
            }
            
            scenario = SystemFailureScenario.objects.create(
                name=scenario_name,
                description=f"{api_name} API is unavailable. Status: {status['error']}",
                scenario_type="api_failure",
                probability="high",
                severity="high" if api_name in ["google_earth_engine", "world_bank_cckp"] else "medium",
                impact_description=f"Cannot fetch data from {api_name}. Affected features will use fallback mechanisms.",
                affected_modules=affected_modules_map.get(api_name, []),
                mitigation_strategy=fallback_map.get(api_name, "Use cached data"),
                mitigation_status="active",
                has_fallback=True,
                fallback_description=fallback_map.get(api_name, "Cached data"),
                recovery_time_minutes=30,
                last_occurred_at=timezone.now(),
                occurrence_count=1,
            )
            
            logger.error(f"API failure scenario created: {scenario_name}")


class ModelDriftMonitor:
    """
    Monitor PCRS model drift over time with regional variance analysis.
    
    Runs weekly via Celery Beat.
    
    Detects when model accuracy degrades by region, indicating need for retraining.
    """
    
    def check_model_drift(self) -> Optional[dict]:
        """
        Check for model drift by analyzing regional prediction variance.
        
        Method:
        - Get last 30 days of PCRScore records
        - Calculate prediction variance by region
        - If European bonds variance > 15%: create ModelDriftAlert
        - If emerging market variance > 25%: create ModelDriftAlert severity=critical
        
        Returns:
            Drift metrics dict or None if insufficient data
        """
        # Get PCRS scores from last 30 days
        cutoff_date = timezone.now() - timedelta(days=30)
        recent_scores = PCRScore.objects.filter(scored_at__gte=cutoff_date).select_related("bond")
        
        if recent_scores.count() < 10:
            logger.info("Insufficient data for model drift detection (need 10+ scores)")
            return None
        
        # Group by region
        regional_variance = self._calculate_regional_variance(recent_scores)
        
        if not regional_variance:
            logger.info("No regional data available for drift detection")
            return None
        
        # Check for drift
        drift_detected = False
        critical_regions = []
        warning_regions = []
        
        for region, metrics in regional_variance.items():
            variance_pct = metrics["variance_pct"]
            
            # European bonds: variance > 15%
            if region in ["Europe", "European Union"] and variance_pct > 15:
                drift_detected = True
                warning_regions.append(region)
                self._create_drift_alert(region, metrics, severity="medium")
            
            # Emerging markets: variance > 25%
            elif region in ["Asia", "Africa", "Americas"] and variance_pct > 25:
                drift_detected = True
                critical_regions.append(region)
                self._create_drift_alert(region, metrics, severity="critical")
        
        drift_metrics = {
            "drift_detected": drift_detected,
            "regional_variance": regional_variance,
            "critical_regions": critical_regions,
            "warning_regions": warning_regions,
            "total_scores_analyzed": recent_scores.count(),
            "analysis_period_days": 30,
        }
        
        if drift_detected:
            logger.warning(f"Model drift detected: {len(critical_regions)} critical, {len(warning_regions)} warning regions")
        
        return drift_metrics
    
    def _calculate_regional_variance(self, scores) -> Dict[str, dict]:
        """
        Calculate prediction variance by region.
        
        Returns:
            {
                "Europe": {
                    "count": 50,
                    "mean_score": 45.2,
                    "variance": 12.3,
                    "variance_pct": 27.2,
                    "stddev": 3.5,
                },
                ...
            }
        """
        from risk_scoring.bias_detection import get_region
        
        regional_data = {}
        
        for score in scores:
            region = get_region(score.bond.country)
            
            if region not in regional_data:
                regional_data[region] = []
            
            regional_data[region].append(score.score)
        
        # Calculate statistics
        regional_variance = {}
        
        for region, score_list in regional_data.items():
            if len(score_list) < 3:  # Need at least 3 samples
                continue
            
            import numpy as np
            scores_array = np.array(score_list)
            
            mean_score = float(np.mean(scores_array))
            variance = float(np.var(scores_array))
            stddev = float(np.std(scores_array))
            variance_pct = (stddev / mean_score * 100) if mean_score > 0 else 0
            
            regional_variance[region] = {
                "count": len(score_list),
                "mean_score": round(mean_score, 2),
                "variance": round(variance, 2),
                "variance_pct": round(variance_pct, 2),
                "stddev": round(stddev, 2),
            }
        
        return regional_variance
    
    def _create_drift_alert(self, region: str, metrics: dict, severity: str = "medium"):
        """
        Create model drift alert for a region.
        """
        # Check if alert already exists for this week
        week_ago = timezone.now() - timedelta(days=7)
        existing = ModelDriftAlert.objects.filter(
            model_name="PCRS XGBoost",
            detected_at__gte=week_ago,
            status__in=["investigating", "identified"],
        ).filter(
            Q(metric_name__icontains=region) | Q(recommendation__icontains=region)
        ).first()
        
        if existing:
            logger.info(f"Model drift alert already exists for {region}")
            return
        
        alert = ModelDriftAlert.objects.create(
            model_name="PCRS XGBoost",
            metric_name=f"{region}_prediction_variance",
            baseline_value=15.0 if region in ["Europe", "European Union"] else 25.0,
            current_value=metrics["variance_pct"],
            drift_magnitude=metrics["variance_pct"],
            threshold=15.0 if region in ["Europe", "European Union"] else 25.0,
            severity=severity,
            status="investigating",
            recommendation=f"High prediction variance detected in {region} ({metrics['variance_pct']:.1f}%). "
                          f"Model shows inconsistent predictions for this region. "
                          f"Recommend: (1) Collect more training data from {region}, "
                          f"(2) Fine-tune model on {region}-specific samples, "
                          f"(3) Consider region-specific sub-models.",
        )
        
        logger.warning(f"Model drift alert created: {region} - variance {metrics['variance_pct']:.1f}%")
        
        # Create incident log
        IncidentLog.objects.create(
            incident_type="model_drift",
            severity=severity,
            title=f"Model Drift Detected: {region}",
            description=f"Prediction variance in {region} exceeds threshold: {metrics['variance_pct']:.1f}%. "
                       f"Mean score: {metrics['mean_score']:.1f}, StdDev: {metrics['stddev']:.1f}. "
                       f"Based on {metrics['count']} samples from last 30 days.",
            affected_component="risk_scoring",
            status="investigating",
        )


class DataQualityMonitor:
    """
    Monitor data quality metrics across all data sources.
    
    Runs daily via Celery Beat.
    
    Auto-checks:
    - Count bonds with location_confidence='country'
    - Count bonds with no GreenwashFlag
    - Count PricingGap records older than 7 days
    - Update DataQualityMetric records automatically
    """
    
    def check_data_quality(self) -> dict:
        """
        Check data quality for all bonds and auto-update metrics.
        
        Returns:
            Quality metrics dict
        """
        total_bonds = GreenBond.objects.count()
        
        if total_bonds == 0:
            logger.warning("No bonds in database for quality check")
            return {
                "total_bonds": 0,
                "overall_quality_score": 0,
                "status": "no_data",
            }
        
        # 1. Count bonds with location_confidence='country' (LOW QUALITY)
        country_level_bonds = GreenBond.objects.filter(location_confidence="country").count()
        precise_location_pct = ((total_bonds - country_level_bonds) / total_bonds * 100)
        
        # 2. Count bonds with no GreenwashFlag (MISSING VERIFICATION)
        bonds_with_greenwash_check = GreenBond.objects.filter(
            greenwash_flags__isnull=False
        ).distinct().count()
        greenwash_coverage_pct = (bonds_with_greenwash_check / total_bonds * 100)
        
        # 3. Count PricingGap records older than 7 days (STALE DATA)
        seven_days_ago = timezone.now() - timedelta(days=7)
        stale_pricing_gaps = PricingGap.objects.filter(checked_at__lt=seven_days_ago).count()
        total_pricing_gaps = PricingGap.objects.count()
        fresh_pricing_pct = ((total_pricing_gaps - stale_pricing_gaps) / total_pricing_gaps * 100) if total_pricing_gaps > 0 else 0
        
        # Additional completeness metrics
        bonds_with_coords = GreenBond.objects.filter(
            lat__isnull=False,
            lon__isnull=False,
        ).count()
        coord_completeness_pct = (bonds_with_coords / total_bonds * 100)
        
        bonds_with_hazards = GreenBond.objects.filter(
            hazard_data__isnull=False,
        ).distinct().count()
        hazard_completeness_pct = (bonds_with_hazards / total_bonds * 100)
        
        bonds_with_pcrs = GreenBond.objects.filter(
            pcr_scores__isnull=False,
        ).distinct().count()
        pcrs_completeness_pct = (bonds_with_pcrs / total_bonds * 100)
        
        # Calculate overall quality score (weighted average)
        overall_quality = (
            precise_location_pct * 0.15 +
            greenwash_coverage_pct * 0.20 +
            fresh_pricing_pct * 0.15 +
            coord_completeness_pct * 0.15 +
            hazard_completeness_pct * 0.20 +
            pcrs_completeness_pct * 0.15
        )
        
        metrics = {
            "total_bonds": total_bonds,
            "country_level_bonds": country_level_bonds,
            "precise_location_pct": round(precise_location_pct, 1),
            "greenwash_coverage_pct": round(greenwash_coverage_pct, 1),
            "stale_pricing_gaps": stale_pricing_gaps,
            "fresh_pricing_pct": round(fresh_pricing_pct, 1),
            "coord_completeness_pct": round(coord_completeness_pct, 1),
            "hazard_completeness_pct": round(hazard_completeness_pct, 1),
            "pcrs_completeness_pct": round(pcrs_completeness_pct, 1),
            "overall_quality_score": round(overall_quality, 1),
            "status": self._get_quality_status(overall_quality),
        }
        
        # Auto-update DataQualityMetric records
        self._update_quality_metrics(metrics)
        
        return metrics
    
    def _update_quality_metrics(self, metrics: dict):
        """
        Auto-update DataQualityMetric records in database.
        """
        # 1. Location Quality Metric
        DataQualityMetric.objects.create(
            metric_name="location_precision",
            metric_type="accuracy",
            value=metrics["precise_location_pct"],
            threshold_warning=80.0,
            threshold_critical=60.0,
            status="healthy" if metrics["precise_location_pct"] >= 80 else (
                "warning" if metrics["precise_location_pct"] >= 60 else "critical"
            ),
            description=f"{metrics['country_level_bonds']} bonds have only country-level location (low precision)",
            affected_records=metrics["country_level_bonds"],
        )
        
        # 2. Greenwash Coverage Metric
        DataQualityMetric.objects.create(
            metric_name="greenwash_verification_coverage",
            metric_type="completeness",
            value=metrics["greenwash_coverage_pct"],
            threshold_warning=80.0,
            threshold_critical=60.0,
            status="healthy" if metrics["greenwash_coverage_pct"] >= 80 else (
                "warning" if metrics["greenwash_coverage_pct"] >= 60 else "critical"
            ),
            description=f"{metrics['greenwash_coverage_pct']:.1f}% of bonds have greenwash verification",
            affected_records=metrics["total_bonds"] - int(metrics["total_bonds"] * metrics["greenwash_coverage_pct"] / 100),
        )
        
        # 3. Pricing Freshness Metric
        DataQualityMetric.objects.create(
            metric_name="pricing_data_freshness",
            metric_type="timeliness",
            value=metrics["fresh_pricing_pct"],
            threshold_warning=80.0,
            threshold_critical=60.0,
            status="healthy" if metrics["fresh_pricing_pct"] >= 80 else (
                "warning" if metrics["fresh_pricing_pct"] >= 60 else "critical"
            ),
            description=f"{metrics['stale_pricing_gaps']} pricing gap records are older than 7 days",
            affected_records=metrics["stale_pricing_gaps"],
        )
        
        # 4. Overall Quality Metric
        DataQualityMetric.objects.create(
            metric_name="overall_data_quality",
            metric_type="completeness",
            value=metrics["overall_quality_score"],
            threshold_warning=70.0,
            threshold_critical=50.0,
            status="healthy" if metrics["overall_quality_score"] >= 80 else (
                "warning" if metrics["overall_quality_score"] >= 70 else "critical"
            ),
            description=f"Overall data quality score: {metrics['overall_quality_score']:.1f}%",
            affected_records=metrics["total_bonds"],
        )
        
        logger.info(f"Data quality metrics updated: overall score {metrics['overall_quality_score']:.1f}%")
    
    def _get_quality_status(self, quality_score: float) -> str:
        """Get quality status based on score."""
        if quality_score >= 90:
            return "excellent"
        elif quality_score >= 80:
            return "good"
        elif quality_score >= 70:
            return "fair"
        else:
            return "poor"


def run_all_monitors():
    """
    Run all monitoring checks.
    
    This function should be called by a Celery periodic task.
    """
    logger.info("Starting system monitoring checks...")
    
    # 1. API Health
    api_monitor = APIHealthMonitor()
    api_results = api_monitor.check_all_apis()
    logger.info(f"API health check complete: {api_results}")
    
    # 2. Model Drift
    drift_monitor = ModelDriftMonitor()
    drift_results = drift_monitor.check_model_drift()
    if drift_results:
        logger.info(f"Model drift check complete: {drift_results}")
    
    # 3. Data Quality
    quality_monitor = DataQualityMonitor()
    quality_results = quality_monitor.check_data_quality()
    logger.info(f"Data quality check complete: {quality_results}")
    
    # Cache results for dashboard
    cache.set("monitoring_api_health", api_results, timeout=300)  # 5 minutes
    cache.set("monitoring_model_drift", drift_results, timeout=300)
    cache.set("monitoring_data_quality", quality_results, timeout=300)
    
    logger.info("System monitoring checks complete.")
    
    return {
        "api_health": api_results,
        "model_drift": drift_results,
        "data_quality": quality_results,
    }
