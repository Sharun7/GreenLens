# Automatic Monitoring - Quick Start Guide

## Overview

Your Risk Management Dashboard now has **3 automatic monitors** running continuously:

1. **API Health Monitor** - Every 30 minutes
2. **Model Drift Detector** - Weekly (Sundays)
3. **Data Quality Checker** - Daily

All monitors use **REAL data** and auto-create incidents/alerts when issues are detected.

---

## Quick Start

### 1. Start Celery Worker

```bash
celery -A greenlens worker --loglevel=info --pool=solo
```

### 2. Start Celery Beat (Scheduler)

```bash
celery -A greenlens beat --loglevel=info
```

You should see the 3 monitors scheduled:

```
- api-health-monitor: every 30 minutes
- weekly-model-drift-detector: Sundays 03:00 UTC
- daily-data-quality-checker: daily 05:00 UTC
```

### 3. View Results

Visit the Risk Management Dashboard:
```
http://127.0.0.1:8000/risk/
```

---

## Manual Testing

### Test API Health Monitor

```bash
python manage.py shell
```

```python
from risk_management.monitoring import APIHealthMonitor

monitor = APIHealthMonitor()
results = monitor.check_all_apis()

print(f"Google Earth Engine: {'✓' if results['google_earth_engine']['healthy'] else '✗'}")
print(f"World Bank CCKP: {'✓' if results['world_bank_cckp']['healthy'] else '✗'}")
print(f"Yahoo Finance: {'✓' if results['yahoo_finance']['healthy'] else '✗'}")
```

### Test Model Drift Detector

```python
from risk_management.monitoring import ModelDriftMonitor

monitor = ModelDriftMonitor()
results = monitor.check_model_drift()

if results:
    print(f"Drift detected: {results['drift_detected']}")
    print(f"Regions analyzed: {list(results['regional_variance'].keys())}")
else:
    print("Insufficient data for drift detection")
```

### Test Data Quality Checker

```python
from risk_management.monitoring import DataQualityMonitor

monitor = DataQualityMonitor()
results = monitor.check_data_quality()

print(f"Overall quality score: {results['overall_quality_score']:.1f}%")
print(f"Status: {results['status']}")
print(f"Total bonds: {results['total_bonds']}")
```

---

## Trigger Celery Tasks Manually

```bash
# Test API health task
celery -A greenlens call risk_management.monitor_api_health

# Test model drift task
celery -A greenlens call risk_management.detect_model_drift

# Test data quality task
celery -A greenlens call risk_management.check_data_quality
```

---

## View Auto-Created Incidents

```bash
python manage.py shell
```

```python
from risk_management.models import IncidentLog, ModelDriftAlert, DataQualityMetric

# View API failure incidents
api_incidents = IncidentLog.objects.filter(incident_type="api_failure")
for incident in api_incidents:
    print(f"{incident.title} - {incident.severity} - {incident.status}")

# View model drift alerts
drift_alerts = ModelDriftAlert.objects.all()
for alert in drift_alerts:
    print(f"{alert.model_name} - {alert.metric_name}: {alert.current_value:.1f}%")

# View data quality metrics
quality_metrics = DataQualityMetric.objects.order_by("-checked_at")[:10]
for metric in quality_metrics:
    print(f"{metric.metric_name}: {metric.value:.1f}% - {metric.status}")
```

---

## Monitoring Schedules

| Monitor | Schedule | Celery Task |
|---------|----------|-------------|
| API Health | Every 30 minutes | `risk_management.monitor_api_health` |
| Model Drift | Weekly (Sun 03:00 UTC) | `risk_management.detect_model_drift` |
| Data Quality | Daily (05:00 UTC) | `risk_management.check_data_quality` |

---

## What Gets Auto-Created

### API Health Monitor
- ✅ `IncidentLog` when API fails
- ✅ `SystemFailureScenario` with fallback strategy
- ✅ Updates existing incidents if already reported

### Model Drift Detector
- ✅ `ModelDriftAlert` when variance exceeds threshold
- ✅ `IncidentLog` with drift details
- ✅ Recommendations for retraining

### Data Quality Checker
- ✅ 4 `DataQualityMetric` records:
  - Location precision
  - Greenwash coverage
  - Pricing freshness
  - Overall quality score

---

## Troubleshooting

### Celery Beat not scheduling tasks

```bash
# Check if tasks are registered
python manage.py shell
>>> from django_celery_beat.models import PeriodicTask
>>> PeriodicTask.objects.all()
```

### Tasks not running

```bash
# Check Celery worker logs
celery -A greenlens worker --loglevel=debug

# Check Celery Beat logs
celery -A greenlens beat --loglevel=debug
```

### No incidents being created

```bash
# Check if monitors are detecting issues
python manage.py shell
>>> from risk_management.monitoring import run_all_monitors
>>> results = run_all_monitors()
>>> print(results)
```

---

## Next Steps

1. ✅ Start Celery worker and beat
2. ✅ Wait for monitors to run (or trigger manually)
3. ✅ Check Risk Management Dashboard
4. ✅ View auto-created incidents/alerts
5. ✅ Monitor logs for any issues

---

## Full Documentation

See **AUTOMATIC_MONITORING_IMPLEMENTATION.md** for complete technical details.
