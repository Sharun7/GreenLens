# GreenLens Automatic Monitoring Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CELERY BEAT SCHEDULER                            │
│                     (Triggers tasks on schedule)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│  API Health       │   │  Model Drift      │   │  Data Quality     │
│  Monitor          │   │  Detector         │   │  Checker          │
│                   │   │                   │   │                   │
│  Every 30 min     │   │  Weekly (Sun)     │   │  Daily (05:00)    │
└───────────────────┘   └───────────────────┘   └───────────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│ Check 3 APIs:     │   │ Analyze PCRS:     │   │ Check Quality:    │
│ • GEE             │   │ • Last 30 days    │   │ • Location        │
│ • World Bank      │   │ • By region       │   │ • Greenwash       │
│ • Yahoo Finance   │   │ • Variance calc   │   │ • Pricing         │
└───────────────────┘   └───────────────────┘   └───────────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│ If API fails:     │   │ If drift > 15%:   │   │ Auto-update:      │
│ • IncidentLog     │   │ • ModelDriftAlert │   │ • 4 Metrics       │
│ • FailureScenario │   │ • IncidentLog     │   │ • Status          │
│ • Fallback plan   │   │ • Recommendations │   │ • Thresholds      │
└───────────────────┘   └───────────────────┘   └───────────────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    ▼
                        ┌───────────────────┐
                        │   REDIS CACHE     │
                        │   (5 min TTL)     │
                        └───────────────────┘
                                    │
                                    ▼
                        ┌───────────────────┐
                        │  RISK DASHBOARD   │
                        │  /risk/           │
                        └───────────────────┘
```

---

## Component Details

### 1. API Health Monitor

**Celery Task**: `risk_management.monitor_api_health`  
**Schedule**: Every 30 minutes (1800 seconds)  
**Class**: `APIHealthMonitor` in `risk_management/monitoring.py`

```python
class APIHealthMonitor:
    def check_all_apis(self) -> Dict[str, dict]:
        """Check health of all external APIs."""
        results = {}
        results["google_earth_engine"] = self._check_google_earth_engine()
        results["world_bank_cckp"] = self._check_world_bank_cckp()
        results["yahoo_finance"] = self._check_yahoo_finance()
        
        # Auto-create IncidentLog if any API fails
        for api_name, status in results.items():
            if not status["healthy"]:
                self._create_incident_log(api_name, status)
        
        return results
```

**Checks**:
1. **Google Earth Engine**: `ee.Initialize()` test
2. **World Bank CCKP**: GET request to climate endpoint
3. **Yahoo Finance**: `yfinance.download()` test

**Auto-Actions**:
- Creates `IncidentLog` (severity: high/medium)
- Creates `SystemFailureScenario` with fallback
- Updates existing incidents (increments occurrence count)

---

### 2. Model Drift Detector

**Celery Task**: `risk_management.detect_model_drift`  
**Schedule**: Weekly (Sundays at 03:00 UTC)  
**Class**: `ModelDriftMonitor` in `risk_management/monitoring.py`

```python
class ModelDriftMonitor:
    def check_model_drift(self) -> Optional[dict]:
        """Check for model drift by analyzing regional variance."""
        # Get last 30 days of PCRScore records
        recent_scores = PCRScore.objects.filter(scored_at__gte=cutoff_date)
        
        # Calculate variance by region
        regional_variance = self._calculate_regional_variance(recent_scores)
        
        # Check thresholds
        for region, metrics in regional_variance.items():
            if region in ["Europe", "European Union"] and variance_pct > 15:
                self._create_drift_alert(region, metrics, severity="medium")
            elif region in ["Asia", "Africa", "Americas"] and variance_pct > 25:
                self._create_drift_alert(region, metrics, severity="critical")
```

**Analysis**:
- Gets last 30 days of PCRScore records
- Groups by region (Europe, Asia, Africa, Americas)
- Calculates variance percentage: `(stddev / mean) * 100`

**Thresholds**:
- Europe: variance > 15% → Medium alert
- Emerging markets: variance > 25% → Critical alert

**Auto-Actions**:
- Creates `ModelDriftAlert` with variance metrics
- Creates `IncidentLog` with drift details
- Provides retraining recommendations

---

### 3. Data Quality Checker

**Celery Task**: `risk_management.check_data_quality`  
**Schedule**: Daily (05:00 UTC)  
**Class**: `DataQualityMonitor` in `risk_management/monitoring.py`

```python
class DataQualityMonitor:
    def check_data_quality(self) -> dict:
        """Check data quality for all bonds."""
        # 1. Location precision
        country_level_bonds = GreenBond.objects.filter(
            location_confidence="country"
        ).count()
        
        # 2. Greenwash coverage
        bonds_with_greenwash_check = GreenBond.objects.filter(
            greenwash_flags__isnull=False
        ).distinct().count()
        
        # 3. Pricing freshness
        stale_pricing_gaps = PricingGap.objects.filter(
            checked_at__lt=seven_days_ago
        ).count()
        
        # Calculate overall quality score (weighted average)
        overall_quality = (
            precise_location_pct * 0.15 +
            greenwash_coverage_pct * 0.20 +
            fresh_pricing_pct * 0.15 +
            coord_completeness_pct * 0.15 +
            hazard_completeness_pct * 0.20 +
            pcrs_completeness_pct * 0.15
        )
        
        # Auto-update DataQualityMetric records
        self._update_quality_metrics(metrics)
```

**Metrics**:
1. **Location Precision** (15% weight) - Country-level vs precise
2. **Greenwash Coverage** (20% weight) - Bonds with verification
3. **Pricing Freshness** (15% weight) - Data older than 7 days
4. **Coordinate Completeness** (15% weight) - Bonds with lat/lon
5. **Hazard Completeness** (20% weight) - Bonds with hazard data
6. **PCRS Completeness** (15% weight) - Bonds with PCRS scores

**Auto-Actions**:
- Creates 4 `DataQualityMetric` records:
  1. Location precision metric
  2. Greenwash coverage metric
  3. Pricing freshness metric
  4. Overall quality metric

---

## Data Flow

### API Health Monitor Flow

```
Celery Beat (every 30 min)
    ↓
monitor_api_health() task
    ↓
APIHealthMonitor.check_all_apis()
    ↓
┌─────────────────────────────────────┐
│ Check Google Earth Engine           │
│ Check World Bank CCKP                │
│ Check Yahoo Finance                  │
└─────────────────────────────────────┘
    ↓
If any API fails:
    ↓
┌─────────────────────────────────────┐
│ Create IncidentLog                   │
│ Create SystemFailureScenario         │
│ Log error details                    │
└─────────────────────────────────────┘
    ↓
Cache results in Redis (5 min TTL)
    ↓
Display in Risk Dashboard
```

### Model Drift Detector Flow

```
Celery Beat (weekly, Sunday 03:00)
    ↓
detect_model_drift() task
    ↓
ModelDriftMonitor.check_model_drift()
    ↓
┌─────────────────────────────────────┐
│ Query PCRScore (last 30 days)       │
│ Group by region                      │
│ Calculate variance per region        │
└─────────────────────────────────────┘
    ↓
If variance > threshold:
    ↓
┌─────────────────────────────────────┐
│ Create ModelDriftAlert               │
│ Create IncidentLog                   │
│ Generate recommendations             │
└─────────────────────────────────────┘
    ↓
Cache results in Redis (5 min TTL)
    ↓
Display in Risk Dashboard
```

### Data Quality Checker Flow

```
Celery Beat (daily, 05:00)
    ↓
check_data_quality() task
    ↓
DataQualityMonitor.check_data_quality()
    ↓
┌─────────────────────────────────────┐
│ Count country-level bonds            │
│ Count bonds without greenwash check  │
│ Count stale pricing gaps             │
│ Calculate completeness metrics       │
└─────────────────────────────────────┘
    ↓
Calculate overall quality score
    ↓
┌─────────────────────────────────────┐
│ Create/Update 4 DataQualityMetrics:  │
│ 1. Location precision                │
│ 2. Greenwash coverage                │
│ 3. Pricing freshness                 │
│ 4. Overall quality                   │
└─────────────────────────────────────┘
    ↓
Cache results in Redis (5 min TTL)
    ↓
Display in Risk Dashboard
```

---

## Database Models

### IncidentLog
```python
class IncidentLog(models.Model):
    incident_type = models.CharField(max_length=50)  # "api_failure", "model_drift"
    severity = models.CharField(max_length=20)       # "low", "medium", "high", "critical"
    title = models.CharField(max_length=200)
    description = models.TextField()
    affected_component = models.CharField(max_length=100)
    status = models.CharField(max_length=20)         # "investigating", "identified", "resolved"
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    occurrence_count = models.IntegerField(default=1)
```

### ModelDriftAlert
```python
class ModelDriftAlert(models.Model):
    model_name = models.CharField(max_length=100)    # "PCRS XGBoost"
    metric_name = models.CharField(max_length=100)   # "{region}_prediction_variance"
    baseline_value = models.FloatField()
    current_value = models.FloatField()
    drift_magnitude = models.FloatField()
    threshold = models.FloatField()
    severity = models.CharField(max_length=20)       # "medium", "critical"
    status = models.CharField(max_length=20)         # "investigating", "identified", "resolved"
    recommendation = models.TextField()
    detected_at = models.DateTimeField(auto_now_add=True)
```

### DataQualityMetric
```python
class DataQualityMetric(models.Model):
    metric_name = models.CharField(max_length=100)
    metric_type = models.CharField(max_length=50)    # "accuracy", "completeness", "timeliness"
    value = models.FloatField()
    threshold_warning = models.FloatField()
    threshold_critical = models.FloatField()
    status = models.CharField(max_length=20)         # "healthy", "warning", "critical"
    description = models.TextField()
    affected_records = models.IntegerField()
    checked_at = models.DateTimeField(auto_now_add=True)
```

### SystemFailureScenario
```python
class SystemFailureScenario(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    scenario_type = models.CharField(max_length=50)  # "api_failure", "data_quality", etc.
    probability = models.CharField(max_length=20)    # "low", "medium", "high"
    severity = models.CharField(max_length=20)       # "low", "medium", "high", "critical"
    impact_description = models.TextField()
    affected_modules = models.JSONField()
    mitigation_strategy = models.TextField()
    mitigation_status = models.CharField(max_length=20)
    has_fallback = models.BooleanField(default=False)
    fallback_description = models.TextField()
    recovery_time_minutes = models.IntegerField()
    last_occurred_at = models.DateTimeField()
    occurrence_count = models.IntegerField(default=0)
```

---

## Logging

All monitors log to `greenlens.monitoring`:

```python
import logging
logger = logging.getLogger("greenlens.monitoring")

# API Health
logger.error(f"API failure incident created: {api_name}")
logger.warning(f"API failure incident updated: {api_name} (occurrence #{count})")
logger.info("All APIs are healthy")

# Model Drift
logger.warning(f"Model drift detected: {len(critical_regions)} critical regions")
logger.info("No model drift detected")

# Data Quality
logger.info(f"Data quality check complete: {quality_score:.1f}%")
logger.warning(f"Data quality below threshold: {quality_score:.1f}%")
```

---

## Redis Caching

All monitoring results are cached for dashboard display:

```python
from django.core.cache import cache

# Cache monitoring results (5 minute TTL)
cache.set("monitoring_api_health", api_results, timeout=300)
cache.set("monitoring_model_drift", drift_results, timeout=300)
cache.set("monitoring_data_quality", quality_results, timeout=300)

# Retrieve in dashboard view
api_health = cache.get("monitoring_api_health", {})
model_drift = cache.get("monitoring_model_drift", {})
data_quality = cache.get("monitoring_data_quality", {})
```

---

## Fallback Strategies

### API Failures

| API | Fallback Mechanism |
|-----|-------------------|
| Google Earth Engine | Use Copernicus API → Cached NDVI → Mark as unverifiable |
| World Bank CCKP | Use NASA Earthdata → Historical averages → Reduced confidence |
| Yahoo Finance | Use cached yield data → Manual pricing updates |

### Model Drift

When drift is detected:
1. Collect more training data from affected region
2. Fine-tune model on region-specific samples
3. Consider region-specific sub-models

### Data Quality Issues

| Issue | Action |
|-------|--------|
| Low location precision | Request precise coordinates from issuer |
| Missing greenwash checks | Schedule verification for unchecked bonds |
| Stale pricing data | Trigger manual pricing refresh |

---

## Summary

**3 Automatic Monitors**:
1. ✅ API Health Monitor (every 30 min)
2. ✅ Model Drift Detector (weekly)
3. ✅ Data Quality Checker (daily)

**All using REAL data**:
- Live API calls
- Database queries
- No placeholders

**Fully automated**:
- Auto-creates incidents/alerts
- Auto-updates metrics
- Zero manual intervention required
