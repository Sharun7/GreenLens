# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_scoring/drift_detection.py — Model Drift Detection System.

Automated monitoring system to detect when PCRS model predictions become
unreliable due to changing climate patterns or data distribution shifts.

Key Features:
- Monthly model performance checks against actual climate events
- Automated alerts when accuracy drops below threshold
- Dashboard flagging when model needs retraining
- Historical performance tracking
"""
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger("greenlens.drift_detection")

# Performance thresholds
ACCURACY_THRESHOLD = 0.75  # Alert if accuracy drops below 75%
PREDICTION_CONFIDENCE_THRESHOLD = 0.60  # Flag low confidence predictions
MIN_EVENTS_FOR_VALIDATION = 10  # Minimum climate events needed for validation


@dataclass
class ClimateEvent:
    """Represents an actual climate event for validation."""
    location: Tuple[float, float]  # (lat, lon)
    event_type: str  # "flood", "drought", "heat_wave", "wildfire"
    severity: float  # 0-1 scale
    date: datetime
    source: str  # "NOAA", "ECMWF", "local_reports"
    verified: bool = True


@dataclass
class DriftMetrics:
    """Model drift detection metrics."""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    prediction_confidence_avg: float
    events_analyzed: int
    drift_detected: bool
    alert_level: str  # "green", "yellow", "red"


class ModelDriftDetector:
    """
    Detects model drift by comparing PCRS predictions against actual climate events.
    
    Methodology:
    1. Fetch recent climate events from external APIs
    2. Find bonds in affected areas
    3. Compare PCRS predictions vs actual event severity
    4. Calculate accuracy metrics
    5. Alert if performance degrades
    """
    
    def __init__(self):
        self.climate_apis = {
            "noaa": self._fetch_noaa_events,
            "ecmwf": self._fetch_ecmwf_events,
            "local": self._fetch_local_reports,
        }
    
    def check_model_drift(self, days_back: int = 30) -> DriftMetrics:
        """
        Main drift detection method.
        
        Args:
            days_back: Number of days to look back for climate events
            
        Returns:
            DriftMetrics with accuracy assessment and drift status
        """
        logger.info("Starting model drift detection for last %d days", days_back)
        
        # Step 1: Fetch recent climate events
        events = self._fetch_recent_climate_events(days_back)
        if len(events) < MIN_EVENTS_FOR_VALIDATION:
            logger.warning(
                "Insufficient climate events (%d) for drift validation. Need at least %d.",
                len(events), MIN_EVENTS_FOR_VALIDATION
            )
            return self._create_insufficient_data_metrics(len(events))
        
        # Step 2: Find bonds in affected areas and get their PCRS predictions
        predictions_vs_actual = []
        for event in events:
            affected_bonds = self._find_bonds_near_event(event)
            for bond in affected_bonds:
                pcrs_prediction = self._get_latest_pcrs_prediction(bond, event.date)
                if pcrs_prediction:
                    predictions_vs_actual.append({
                        'bond_id': bond.bond_id,
                        'predicted_risk': pcrs_prediction.score,
                        'actual_severity': event.severity * 100,  # Convert to 0-100 scale
                        'event_type': event.event_type,
                        'confidence': pcrs_prediction.confidence_interval['margin'],
                        'location_confidence': bond.location_confidence,
                    })
        
        # Step 3: Calculate performance metrics
        metrics = self._calculate_drift_metrics(predictions_vs_actual)
        
        # Step 4: Determine if drift detected and alert level
        metrics.drift_detected = metrics.accuracy < ACCURACY_THRESHOLD
        metrics.alert_level = self._determine_alert_level(metrics)
        
        # Step 5: Log and potentially alert
        self._log_drift_results(metrics)
        if metrics.drift_detected:
            self._send_drift_alert(metrics)
        
        # Step 6: Save results to database
        self._save_drift_check_result(metrics, predictions_vs_actual)
        
        return metrics
    
    def _fetch_recent_climate_events(self, days_back: int) -> List[ClimateEvent]:
        """Fetch climate events from multiple sources."""
        all_events = []
        start_date = datetime.now() - timedelta(days=days_back)
        
        for source_name, fetch_func in self.climate_apis.items():
            try:
                events = fetch_func(start_date)
                all_events.extend(events)
                logger.info("Fetched %d events from %s", len(events), source_name)
            except Exception as exc:
                logger.warning("Failed to fetch events from %s: %s", source_name, exc)
        
        # Remove duplicates and sort by date
        unique_events = self._deduplicate_events(all_events)
        return sorted(unique_events, key=lambda e: e.date, reverse=True)
    
    def _fetch_noaa_events(self, start_date: datetime) -> List[ClimateEvent]:
        """Fetch climate events from NOAA API."""
        # Placeholder implementation - would integrate with NOAA Storm Events API
        # https://www.ncdc.noaa.gov/stormevents/
        logger.debug("Fetching NOAA events since %s", start_date)
        
        # Synthetic events for demonstration
        synthetic_events = [
            ClimateEvent(
                location=(25.7617, -80.1918),  # Miami
                event_type="flood",
                severity=0.8,
                date=datetime.now() - timedelta(days=5),
                source="NOAA",
            ),
            ClimateEvent(
                location=(34.0522, -118.2437),  # Los Angeles
                event_type="heat_wave",
                severity=0.7,
                date=datetime.now() - timedelta(days=12),
                source="NOAA",
            ),
        ]
        return synthetic_events
    
    def _fetch_ecmwf_events(self, start_date: datetime) -> List[ClimateEvent]:
        """Fetch climate events from ECMWF API."""
        # Placeholder implementation - would integrate with ECMWF API
        logger.debug("Fetching ECMWF events since %s", start_date)
        return []
    
    def _fetch_local_reports(self, start_date: datetime) -> List[ClimateEvent]:
        """Fetch climate events from local weather services."""
        # Placeholder implementation - would integrate with local APIs
        logger.debug("Fetching local weather reports since %s", start_date)
        return []
    
    def _deduplicate_events(self, events: List[ClimateEvent]) -> List[ClimateEvent]:
        """Remove duplicate events based on location, type, and date proximity."""
        unique_events = []
        for event in events:
            is_duplicate = False
            for existing in unique_events:
                # Check if events are similar (same type, close location, close time)
                if (event.event_type == existing.event_type and
                    self._calculate_distance(event.location, existing.location) < 50 and  # 50km
                    abs((event.date - existing.date).total_seconds()) < 86400):  # 24 hours
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_events.append(event)
        return unique_events
    
    def _calculate_distance(self, loc1: Tuple[float, float], loc2: Tuple[float, float]) -> float:
        """Calculate distance between two coordinates in km."""
        import math
        lat1, lon1 = math.radians(loc1[0]), math.radians(loc1[1])
        lat2, lon2 = math.radians(loc2[0]), math.radians(loc2[1])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return 6371 * c  # Earth radius in km
    
    def _find_bonds_near_event(self, event: ClimateEvent, radius_km: float = 100) -> List:
        """Find bonds within radius of climate event."""
        from data_ingestion.models import GreenBond
        
        # Simple bounding box search (would use PostGIS in production)
        lat, lon = event.location
        lat_delta = radius_km / 111.0  # Rough conversion
        lon_delta = radius_km / (111.0 * abs(math.cos(math.radians(lat))))
        
        bonds = GreenBond.objects.filter(
            lat__gte=lat - lat_delta,
            lat__lte=lat + lat_delta,
            lon__gte=lon - lon_delta,
            lon__lte=lon + lon_delta,
        )
        
        # Filter by actual distance
        nearby_bonds = []
        for bond in bonds:
            distance = self._calculate_distance((bond.lat, bond.lon), event.location)
            if distance <= radius_km:
                nearby_bonds.append(bond)
        
        return nearby_bonds
    
    def _get_latest_pcrs_prediction(self, bond, event_date: datetime):
        """Get the most recent PCRS prediction for a bond before the event."""
        from risk_scoring.models import PCRScore
        
        return PCRScore.objects.filter(
            bond=bond,
            scored_at__lte=event_date
        ).order_by('-scored_at').first()
    
    def _calculate_drift_metrics(self, predictions_vs_actual: List[Dict]) -> DriftMetrics:
        """Calculate accuracy metrics from predictions vs actual events."""
        if not predictions_vs_actual:
            return DriftMetrics(
                accuracy=0.0, precision=0.0, recall=0.0, f1_score=0.0,
                prediction_confidence_avg=0.0, events_analyzed=0,
                drift_detected=True, alert_level="red"
            )
        
        # Convert to binary classification: high risk (>60) vs low risk (<=60)
        correct_predictions = 0
        high_risk_predicted = 0
        high_risk_actual = 0
        true_positives = 0
        confidence_sum = 0
        
        for item in predictions_vs_actual:
            predicted_high = item['predicted_risk'] > 60
            actual_high = item['actual_severity'] > 60
            
            if predicted_high == actual_high:
                correct_predictions += 1
            
            if predicted_high:
                high_risk_predicted += 1
            if actual_high:
                high_risk_actual += 1
            if predicted_high and actual_high:
                true_positives += 1
            
            confidence_sum += (100 - item['confidence'])  # Higher confidence = lower margin
        
        total = len(predictions_vs_actual)
        accuracy = correct_predictions / total
        precision = true_positives / high_risk_predicted if high_risk_predicted > 0 else 0
        recall = true_positives / high_risk_actual if high_risk_actual > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        avg_confidence = confidence_sum / total
        
        return DriftMetrics(
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            prediction_confidence_avg=avg_confidence,
            events_analyzed=total,
            drift_detected=False,  # Will be set by caller
            alert_level="green"    # Will be set by caller
        )
    
    def _determine_alert_level(self, metrics: DriftMetrics) -> str:
        """Determine alert level based on metrics."""
        if metrics.accuracy < 0.60 or metrics.prediction_confidence_avg < 50:
            return "red"
        elif metrics.accuracy < ACCURACY_THRESHOLD or metrics.prediction_confidence_avg < 70:
            return "yellow"
        else:
            return "green"
    
    def _create_insufficient_data_metrics(self, events_count: int) -> DriftMetrics:
        """Create metrics object when insufficient data available."""
        return DriftMetrics(
            accuracy=0.0, precision=0.0, recall=0.0, f1_score=0.0,
            prediction_confidence_avg=0.0, events_analyzed=events_count,
            drift_detected=False, alert_level="yellow"
        )
    
    def _log_drift_results(self, metrics: DriftMetrics):
        """Log drift detection results."""
        logger.info(
            "Model drift check complete: accuracy=%.2f%% events=%d drift=%s alert=%s",
            metrics.accuracy * 100, metrics.events_analyzed,
            metrics.drift_detected, metrics.alert_level
        )
    
    def _send_drift_alert(self, metrics: DriftMetrics):
        """Send alert email when drift detected."""
        if not hasattr(settings, 'DRIFT_ALERT_EMAIL'):
            logger.warning("DRIFT_ALERT_EMAIL not configured - skipping email alert")
            return
        
        subject = f"🚨 GreenLens Model Drift Alert - {metrics.alert_level.upper()}"
        message = f"""
Model drift detected in GreenLens PCRS system:

Accuracy: {metrics.accuracy:.1%} (threshold: {ACCURACY_THRESHOLD:.1%})
Events analyzed: {metrics.events_analyzed}
Average confidence: {metrics.prediction_confidence_avg:.1f}%
Alert level: {metrics.alert_level.upper()}

Recommended actions:
- Review recent climate events and model predictions
- Consider model retraining if accuracy remains low
- Check for data quality issues in recent bond locations

Dashboard: {settings.BASE_URL}/model-bias/
        """
        
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.DRIFT_ALERT_EMAIL],
                fail_silently=False,
            )
            logger.info("Drift alert email sent successfully")
        except Exception as exc:
            logger.error("Failed to send drift alert email: %s", exc)
    
    def _save_drift_check_result(self, metrics: DriftMetrics, predictions_data: List[Dict]):
        """Save drift check results to database."""
        from risk_scoring.models import ModelDriftCheck
        
        ModelDriftCheck.objects.create(
            check_date=timezone.now(),
            accuracy=metrics.accuracy,
            precision=metrics.precision,
            recall=metrics.recall,
            f1_score=metrics.f1_score,
            events_analyzed=metrics.events_analyzed,
            drift_detected=metrics.drift_detected,
            alert_level=metrics.alert_level,
            raw_data=predictions_data,
        )


# Django model to store drift check results
class ModelDriftCheck(models.Model):
    """Store model drift detection results."""
    
    ALERT_LEVELS = [
        ('green', 'Green - Normal'),
        ('yellow', 'Yellow - Warning'),
        ('red', 'Red - Critical'),
    ]
    
    check_date = models.DateTimeField(auto_now_add=True, db_index=True)
    accuracy = models.FloatField(help_text="Model accuracy (0-1)")
    precision = models.FloatField(help_text="Model precision (0-1)")
    recall = models.FloatField(help_text="Model recall (0-1)")
    f1_score = models.FloatField(help_text="F1 score (0-1)")
    events_analyzed = models.IntegerField(help_text="Number of climate events analyzed")
    drift_detected = models.BooleanField(default=False, db_index=True)
    alert_level = models.CharField(max_length=10, choices=ALERT_LEVELS, db_index=True)
    raw_data = models.JSONField(default=list, help_text="Raw predictions vs actual data")
    
    class Meta:
        ordering = ['-check_date']
        indexes = [
            models.Index(fields=['check_date', 'alert_level']),
            models.Index(fields=['drift_detected']),
        ]
    
    def __str__(self):
        return f"DriftCheck({self.check_date.date()}) acc={self.accuracy:.1%} alert={self.alert_level}"


# Management command to run drift detection
class Command(BaseCommand):
    """Django management command to run model drift detection."""
    
    help = "Run model drift detection check"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days-back',
            type=int,
            default=30,
            help='Number of days to look back for climate events (default: 30)'
        )
        parser.add_argument(
            '--alert-only',
            action='store_true',
            help='Only run if previous check showed drift'
        )
    
    def handle(self, *args, **options):
        detector = ModelDriftDetector()
        
        if options['alert_only']:
            # Check if previous run detected drift
            last_check = ModelDriftCheck.objects.first()
            if not last_check or not last_check.drift_detected:
                self.stdout.write("No previous drift detected - skipping check")
                return
        
        self.stdout.write(f"Running drift detection for last {options['days_back']} days...")
        
        metrics = detector.check_model_drift(options['days_back'])
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Drift check complete: {metrics.accuracy:.1%} accuracy, "
                f"{metrics.events_analyzed} events, alert level: {metrics.alert_level}"
            )
        )
        
        if metrics.drift_detected:
            self.stdout.write(
                self.style.WARNING("⚠️  Model drift detected - consider retraining")
            )