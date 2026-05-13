# Automatic Risk Management Monitoring - Complete Implementation

## Overview

GreenLens now has **3 automatic monitoring systems** that run continuously via Celery Beat to detect failures, model drift, and data quality issues **without manual intervention**.

All monitors use **REAL data** from the database and external APIs. No placeholders, no demo data.

---

## 1. API Health Monitor

**Purpose**: Monitor external API availability and auto-create incident logs when APIs fail.

**Schedule**: Every 30 minutes

**Monitored APIs**:
1. **Google Earth Engine** - `ee.Initialize()` test
2. **World Bank CCKP** - GET request to climate data endpoint
3. **Yahoo Finance** - `yfinance.download()` test

### How It Works

```python
from risk_management.monitoring import APIHealthMonitor

monitor = APIHealthMonitor()
results = monitor.check_all_apis()

# Returns:
{
    "google_earth_engine": {
        "healthy": True,
        "response_time_ms": 234,
        "status_code": 200,
        "error": None,
        "method": "ee.Initialize()"
    },
    "world_bank_cckp": {
        "healthy": True,
        "response_time_ms": 456,
        "status_code": 200,
        "error": None,
        "method": "GET request"
    },
    "yahoo_finance": {
        "healthy": False,
        "response_time_ms": 5000,
        "status_code": 0,
        "error": "Timeout",
        "method": "yfinance.download test"
    }
}
```

### Auto-Actions on Failure

When an API fails, the monitor automatically:

1. **Creates IncidentLog**:
   - `incident_type="api_failure"`
   - `severity="high"` for GEE/World Bank, `"medium"` for Yahoo Finance
   - `affected_component=api_name`
   - `status="investigating"`

2. **Creates SystemFailureScenario**:
   - Documents the failure
   - Lists affected modules
   - Provides fallback strategy
   - Tracks occurrence count

3. **Updates existing incidents** if already reported today (increments `occurrence_count`)

### Fallback Strategies

| API | Fallback Mechanism |
|-----|-------------------|
| Google Earth Engine | Use Copernicus API → Cached NDVI → Mark as unverifiable |
| World Bank CCKP | Use NASA Earthdata → Historical averages → Reduced confidence |
| Yahoo Finance | Use cached yield data → Manual pricing updates |

### Celery Task

```python
# risk_management/tasks.py
@shared_task(name="risk_management.monitor_api_health")
def monitor_api_health():
    """Runs every 30 minutes via Celery Beat."""
    monitor = APIHealthMonitor()
    results = monitor.check_all_apis()
    return results
```

### Celery Beat Schedule

```python
# greenlens/settings.py
CELERY_BEAT_SCHEDULE = {
    "api-health-monitor": {
        "task": "risk_management.monitor_api_health",
        "schedule": 1800.0,  # Every 30 minutes (in seconds)
        "options": {"expires": 3600},
    },
}
```

---

## 2. Model Drift Detector

**Purpose**: Detect when PCRS model predictions become inconsistent by region, indicating need for retraining.

**Schedule**: Weekly (Sundays at 03:00 UTC)

**Detection Method**: Regional variance analysis

### How It Works

```python
from risk_management.monitoring import ModelDriftMonitor

monitor = ModelDriftMonitor()
results = monitor.check_model_drift()

# Returns:
{
    "drift_detected": True,
    "regional_variance": {
        "Europe": {
            "count": 50,
            "mean_score": 45.2,
            "variance": 12.3,
            "variance_pct": 27.2,  # > 15% threshold!
            "stddev": 3.5
        },
        "Asia": {
            "count": 30,
            "mean_score": 38.1,
            "variance": 8.5,
            "variance_pct": 22.3,
            "stddev": 2.9
        }
    },
    "critical_regions": [],
    "warning_regions": ["Europe"],
    "total_scores_analyzed": 80,
    "analysis_period_days": 30
}
```

### Drift Thresholds

| Region | Variance Threshold | Alert Severity |
|--------|-------------------|----------------|
| Europe / European Union | > 15% | Medium |
| Asia / Africa / Americas | > 25% | Critical |

### Auto-Actions on Drift Detection

When drift is detected, the monitor automatically:

1. **Creates ModelDriftAlert**:
   - `model_name="PCRS XGBoost"`
   - `metric_name="{region}_prediction_variance"`
   - `current_value=variance_pct`
   - `severity="medium"` or `"critical"`
   - `recommendation` with specific retraining steps

2. **Creates IncidentLog**:
   - `incident_type="model_drift"`
   - Includes variance metrics and sample count
   - `affected_component="risk_scoring"`

### Recommendations

When drift is detected, the system recommends:

1. Collect more training data from affected region
2. Fine-tune model on region-specific samples
3. Consider region-specific sub-models

### Celery Task

```python
# risk_management/tasks.py
@shared_task(name="risk_management.detect_model_drift")
def detect_model_drift():
    """Runs weekly via Celery Beat."""
    monitor = ModelDriftMonitor()
    results = monitor.check_model_drift()
    return results
```

### Celery Beat Schedule

```python
# greenlens/settings.py
CELERY_BEAT_SCHEDULE = {
    "weekly-model-drift-detector": {
        "task": "risk_management.detect_model_drift",
        "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
        "options": {"expires": 82800},
    },
}
```

---

## 3. Data Quality Auto-Checker

**Purpose**: Monitor data completeness and freshness across all data sources.

**Schedule**: Daily (05:00 UTC)

**Metrics Tracked**:
1. Location precision (country-level vs precise coordinates)
2. Greenwash verification coverage
3. Pricing data freshness (older than 7 days)
4. Coordinate completeness
5. Hazard data completeness
6. PCRS completeness

### How It Works

```python
from risk_management.monitoring import DataQualityMonitor

monitor = DataQualityMonitor()
results = monitor.check_data_quality()

# Returns:
{
    "total_bonds": 150,
    "country_level_bonds": 20,
    "precise_location_pct": 86.7,
    "greenwash_coverage_pct": 92.0,
    "stale_pricing_gaps": 5,
    "fresh_pricing_pct": 95.0,
    "coord_completeness_pct": 98.0,
    "hazard_completeness_pct": 88.0,
    "pcrs_completeness_pct": 94.0,
    "overall_quality_score": 91.8,
    "status": "excellent"
}
```

### Quality Score Calculation

Weighted average of all metrics:
- Precise location: 15%
- Greenwash coverage: 20%
- Fresh pricing: 15%
- Coordinate completeness: 15%
- Hazard completeness: 20%
- PCRS completeness: 15%

### Quality Status Levels

| Score | Status |
|-------|--------|
| ≥ 90% | Excellent |
| ≥ 80% | Good |
| ≥ 70% | Fair |
| < 70% | Poor |

### Auto-Actions

The monitor automatically creates/updates **4 DataQualityMetric records**:

1. **Location Precision**:
   - `metric_type="accuracy"`
   - Counts bonds with only country-level location
   - Thresholds: warning=80%, critical=60%

2. **Greenwash Verification Coverage**:
   - `metric_type="completeness"`
   - Percentage of bonds with greenwash checks
   - Thresholds: warning=80%, critical=60%

3. **Pricing Data Freshness**:
   - `metric_type="timeliness"`
   - Counts pricing gaps older than 7 days
   - Thresholds: warning=80%, critical=60%

4. **Overall Data Quality**:
   - `metric_type="completeness"`
   - Weighted average of all metrics
   - Thresholds: warning=70%, critical=50%

### Celery Task

```python
# risk_management/tasks.py
@shared_task(name="risk_management.check_data_quality")
def check_data_quality():
    """Runs daily via Celery Beat."""
    monitor = DataQualityMonitor()
    results = monitor.check_data_quality()
    return results
```

### Celery Beat Schedule

```python
# greenlens/settings.py
CELERY_BEAT_SCHEDULE = {
    "daily-data-quality-checker": {
        "task": "risk_management.check_data_quality",
        "schedule": crontab(hour=5, minute=0),
        "options": {"expires": 82800},
    },
}
```

---

## File Structure

```
risk_management/
├── monitoring.py              # All 3 monitors (APIHealthMonitor, ModelDriftMonitor, DataQualityMonitor)
├── tasks.py                   # Celery tasks for each monitor
├── models.py                  # IncidentLog, ModelDriftAlert, DataQualityMetric, SystemFailureScenario
└── views.py                   # Dashboard views

greenlens/
└── settings.py                # Celery Beat schedules
```

---

## Testing

### Manual Testing

```bash
# Test API health monitor
python manage.py shell
>>> from risk_management.monitoring import APIHealthMonitor
>>> monitor = APIHealthMonitor()
>>> results = monitor.check_all_apis()
>>> print(results)

# Test model drift detector
>>> from risk_management.monitoring import ModelDriftMonitor
>>> monitor = ModelDriftMonitor()
>>> results = monitor.check_model_drift()
>>> print(results)

# Test data quality checker
>>> from risk_management.monitoring import DataQualityMonitor
>>> monitor = DataQualityMonitor()
>>> results = monitor.check_data_quality()
>>> print(results)
```

### Celery Task Testing

```bash
# Test API health task
celery -A greenlens call risk_management.monitor_api_health

# Test model drift task
celery -A greenlens call risk_management.detect_model_drift

# Test data quality task
celery -A greenlens call risk_management.check_data_quality
```

### Verify Celery Beat Schedule

```bash
# Start Celery Beat
celery -A greenlens beat --loglevel=info

# Check scheduled tasks
python manage.py shell
>>> from django_celery_beat.models import PeriodicTask
>>> for task in PeriodicTask.objects.all():
...     print(f"{task.name}: {task.task} - {task.enabled}")
```

---

## Dashboard Integration

All monitoring results are cached in Redis and displayed in the Risk Management Dashboard:

```python
# risk_management/views.py
from django.core.cache import cache

def risk_dashboard(request):
    # Get cached monitoring results
    api_health = cache.get("monitoring_api_health", {})
    model_drift = cache.get("monitoring_model_drift", {})
    data_quality = cache.get("monitoring_data_quality", {})
    
    context = {
        "api_health": api_health,
        "model_drift": model_drift,
        "data_quality": data_quality,
    }
    
    return render(request, "risk_management/dashboard.html", context)
```

---

## Logging

All monitors log to `greenlens.monitoring` logger:

```python
import logging
logger = logging.getLogger("greenlens.monitoring")

# API failure
logger.error(f"API failure incident created: {api_name}")

# Model drift
logger.warning(f"Model drift detected: {len(critical_regions)} critical regions")

# Data quality
logger.info(f"Data quality check complete: {quality_score:.1f}%")
```

---

## Requirements Met

### 1. API Health Monitor ✅
- ✅ Checks Google Earth Engine: `ee.Initialize()` → log success/fail
- ✅ Checks World Bank CCKP: GET request → log status
- ✅ Checks Yahoo Finance: `yfinance.download` test → log status
- ✅ Auto-creates IncidentLog if any API fails
- ✅ Runs every 30 minutes via Celery Beat

### 2. Model Drift Detector ✅
- ✅ Gets last 30 days of PCRScore records
- ✅ Calculates prediction variance by region
- ✅ If European bonds variance > 15%: creates ModelDriftAlert
- ✅ If emerging market variance > 25%: creates ModelDriftAlert severity=critical
- ✅ Runs weekly via Celery Beat

### 3. Data Quality Auto-Checker ✅
- ✅ Counts bonds with location_confidence='country'
- ✅ Counts bonds with no GreenwashFlag
- ✅ Counts PricingGap records older than 7 days
- ✅ Updates DataQualityMetric records automatically
- ✅ Runs daily via Celery Beat

### 4. Celery Beat Configuration ✅
- ✅ `api-health-monitor`: every 30 minutes (1800 seconds)
- ✅ `weekly-model-drift-detector`: weekly (Sunday 03:00 UTC)
- ✅ `daily-data-quality-checker`: daily (05:00 UTC)

---

## Summary

**STATUS**: ✅ COMPLETE

All 3 automatic monitors are fully implemented with:
- Real data from database and external APIs
- Automatic incident/alert creation
- Celery Beat schedules configured
- Comprehensive logging
- Dashboard integration
- No placeholders, no demo data

The Risk Management Dashboard now operates **completely automatically** with zero manual intervention required.
