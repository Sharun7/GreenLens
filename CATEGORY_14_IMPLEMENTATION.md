# Category 14 — Risk & Failure Management Implementation

## Overview

Comprehensive risk tracking, failure scenario management, model drift detection, classification error logging, and legal risk tracking for GreenLens.

**Status:** ✅ COMPLETE — All models created, migrated, and admin interface implemented

---

## What Was Implemented

### 1. System Failure Scenarios (5 Critical Scenarios)

**Scenario 1: Google Earth Engine API Down**
- Probability: Medium
- Impact: Greenwash detection stops, new bonds can't be verified
- Fallback hierarchy:
  1. Try GEE
  2. Fallback to Copernicus API
  3. Fallback to cached NDVI values
  4. Flag as "unverifiable"

**Scenario 2: Yahoo Finance API Rate Limit**
- Probability: High
- Impact: Pricing gap analysis fails, live data becomes stale
- Mitigation: Use paid financial data API (Alpha Vantage, Quandl), multiple provider fallback

**Scenario 3: Model Drift**
- Probability: High over time
- Impact: Climate patterns change, model predictions become increasingly wrong
- Example: Kerala 2018 floods were unprecedented; pre-2018 trained models would underestimate flood risk
- Mitigation: Monthly automated drift detection, accuracy checks, retraining alerts

**Scenario 4: Data Poisoning**
- Probability: Low but serious
- Impact: Bond issuer provides fake project location, investor misled
- Mitigation: Cross-check multiple location sources, NLP analysis of prospectus, third-party registry verification

**Scenario 5: Cloud Infrastructure Failure**
- Probability: Low (99.9% uptime)
- Impact: Complete system down
- Mitigation: Multi-region deployment, daily database snapshots, 4-hour RTO

### 2. Classification Errors (3 Types)

**Type 1: PCRS Score Wrong**
- Example: Bond assigned PCRS=35 (Medium-Low) but actual project in severe flood zone
- Mitigation: Show location confidence level, tag as "Country-level estimate", prominent disclaimer

**Type 2: Greenwash Flag Wrong (False Positive)**
- Example: Legitimate reforestation bond flagged as "Inconsistent" due to cloud cover
- Mitigation: 4-tier flag system (Green/Yellow/Red/Grey), never "Confirmed Greenwash", always "Potential inconsistency"

**Type 3: Pricing Gap Wrong (False Mispriced)**
- Example: Bond flagged as "Mispriced", trader takes short position, actually fairly priced
- Mitigation: "Research indicator only" disclaimer, confidence intervals, "Not financial advice" on every page

### 3. Legal Risks (3 Types)

**Legal Risk 1: Investment Advice Liability**
- Problem: User makes investment decision based on GreenLens score, loses money, sues
- Mitigation: Prominent disclaimer on every page: "GreenLens provides research analytics only. This is NOT financial advice, investment recommendation, or certified ESG rating."

**Legal Risk 2: Defamation / False Greenwash Flag**
- Problem: Company X has genuine green project, GreenLens flags as "Greenwash", reputation damaged
- Mitigation: "Potential inconsistency" (not "Confirmed fraud"), confidence score always shown, "Independent verification recommended", appeal process for issuers

**Legal Risk 3: GDPR / Data Privacy**
- Problem: European users' data collected without GDPR compliance
- Mitigation: Anonymous usage (no user data collection), if user accounts added later, GDPR compliance mandatory

---

## Database Models Created

### 1. SystemFailureScenario
Tracks potential system failure scenarios and their mitigation.

**Fields:**
- `name` (CharField): Scenario name
- `description` (TextField): Detailed description
- `scenario_type` (CharField): api_failure, model_drift, data_poisoning, infrastructure, classification_error
- `probability` (CharField): low, medium, high, critical
- `severity` (CharField): low, medium, high, critical
- `impact_description` (TextField): What happens when this fails
- `affected_modules` (JSONField): List of affected modules
- `mitigation_strategy` (TextField): How to mitigate
- `mitigation_status` (CharField): identified, mitigating, mitigated, monitoring
- `has_fallback` (BooleanField): Whether fallback exists
- `fallback_description` (TextField): Fallback strategy
- `recovery_time_minutes` (IntegerField): Estimated recovery time
- `created_at`, `updated_at`, `last_reviewed_at` (DateTimeField)

**Properties:**
- `risk_score` (property): Calculated risk score (1-100) based on probability × severity

### 2. ModelDriftAlert
Tracks model performance degradation and drift detection.

**Fields:**
- `model_name` (CharField): Name of the model
- `drift_type` (CharField): accuracy_drop, prediction_shift, feature_change, distribution_shift
- `previous_accuracy` (FloatField): Previous accuracy score
- `current_accuracy` (FloatField): Current accuracy score
- `accuracy_drop_percentage` (FloatField): Percentage drop
- `description` (TextField): Drift details
- `affected_predictions` (IntegerField): Number of predictions affected
- `alert_severity` (CharField): warning, alert, critical
- `action_taken` (TextField): Actions taken
- `retraining_scheduled` (BooleanField): Whether retraining is scheduled
- `retraining_date` (DateTimeField): When retraining is scheduled
- `detected_at`, `resolved_at` (DateTimeField)

### 3. ClassificationError
Tracks classification errors (wrong PCRS, false greenwash flags, etc.)

**Fields:**
- `bond_id` (CharField): Bond identifier
- `error_type` (CharField): pcrs_wrong, gw_false_pos, gw_false_neg, pricing_wrong
- `predicted_value` (CharField): What the model predicted
- `actual_value` (CharField): What the actual value was
- `error_description` (TextField): Error details
- `severity` (CharField): low, medium, high, critical
- `potential_user_impact` (TextField): How this affects users
- `root_cause` (TextField): Root cause analysis
- `root_cause_category` (CharField): data_quality, model_limitation, api_error, edge_case, unknown
- `is_resolved` (BooleanField): Whether error is resolved
- `resolution_action` (TextField): How it was resolved
- `resolved_at` (DateTimeField): When it was resolved
- `reported_at`, `reported_by` (DateTimeField, CharField)

### 4. DataQualityMetric
Tracks data quality metrics and anomalies.

**Fields:**
- `metric_name` (CharField): Name of the metric
- `metric_type` (CharField): completeness, accuracy, consistency, timeliness
- `value` (FloatField): Current metric value
- `threshold_warning` (FloatField): Warning threshold
- `threshold_critical` (FloatField): Critical threshold
- `status` (CharField): healthy, warning, critical
- `description` (TextField): Metric details
- `affected_records` (IntegerField): Number of affected records
- `measured_at` (DateTimeField): When measured

### 5. LegalRiskLog
Tracks legal risks and compliance issues.

**Fields:**
- `risk_type` (CharField): investment_advice, defamation, gdpr, regulatory, ip
- `description` (TextField): Risk description
- `severity` (CharField): low, medium, high, critical
- `mitigation_action` (TextField): How to mitigate
- `mitigation_status` (CharField): identified, mitigating, resolved, escalated
- `compliance_requirement` (CharField): Compliance requirement
- `compliance_deadline` (DateField): Deadline for compliance
- `identified_at`, `resolved_at` (DateTimeField)
- `legal_review_required` (BooleanField): Whether legal review is needed

### 6. IncidentLog
Logs all system incidents, errors, and recovery actions.

**Fields:**
- `incident_type` (CharField): api_failure, db_error, model_error, data_error, infrastructure, security
- `title` (CharField): Incident title
- `description` (TextField): Incident details
- `status` (CharField): open, investigating, resolved, closed
- `affected_users` (IntegerField): Number of affected users
- `affected_bonds` (IntegerField): Number of affected bonds
- `downtime_minutes` (IntegerField): Total downtime
- `root_cause` (TextField): Root cause analysis
- `resolution_action` (TextField): How it was resolved
- `detected_at`, `resolved_at` (DateTimeField)

**Properties:**
- `time_to_resolution` (property): Time from detection to resolution

---

## Admin Interface Features

All models have comprehensive Django admin interfaces with:

### Color-Coded Badges
- **Scenario Type**: api_failure (red), model_drift (orange), data_poisoning (crimson), infrastructure (blue), classification_error (purple)
- **Probability**: low (green), medium (gold), high (orange), critical (red-orange)
- **Severity**: low (green), medium (gold), high (orange), critical (red-orange)
- **Status**: identified (red), mitigating (orange), mitigated (green), monitoring (blue)
- **Risk Score**: 1-100 with color coding (green < 40, orange 40-70, red > 70)

### Search & Filtering
- Search by name, description, bond_id, title
- Filter by type, severity, status, date ranges
- Filter by model name, drift type, alert severity
- Filter by error type, root cause category, resolution status

### Collapsible Fieldsets
- Optional/advanced fields grouped in collapsible sections
- Metadata fields (created_at, updated_at) in collapse sections
- Fallback/recovery details in collapse sections

### Read-Only Fields
- Auto-generated fields (created_at, updated_at, detected_at)
- Calculated fields (risk_score, accuracy_drop_percentage, time_to_resolution)

---

## Monitoring Utilities (risk_management/monitoring.py)

### ModelDriftDetector
Detects model performance degradation.

```python
detector = ModelDriftDetector()
drift_alerts = detector.check_pcrs_drift()  # Check PCRS model drift
drift_alerts = detector.check_greenwash_drift()  # Check greenwash model drift
```

### DataQualityMonitor
Monitors data quality metrics.

```python
monitor = DataQualityMonitor()
quality_report = monitor.check_completeness()  # Check data completeness
quality_report = monitor.check_timeliness()  # Check data timeliness
```

### APIFailureHandler
Handles API failures with fallback strategies.

```python
handler = APIFailureHandler()
result = handler.fetch_ndvi_with_fallback(lat, lon)  # GEE → Copernicus → Cache → Unverifiable
result = handler.fetch_price_with_fallback(ticker)  # Yahoo Finance → Cache → Stale
```

### RiskAlertSystem
Comprehensive risk checking and alerting.

```python
alert_system = RiskAlertSystem()
alerts = alert_system.check_all_risks()  # Check all risk types
alerts = alert_system.check_legal_risks()  # Check legal risks
```

---

## Setup Instructions

### Step 1: Verify App Configuration
```bash
# Check that risk_management is in INSTALLED_APPS
grep "risk_management" greenlens/settings.py
```

### Step 2: Create Migrations
```bash
python manage.py makemigrations risk_management
```

### Step 3: Apply Migrations
```bash
python manage.py migrate
```

### Step 4: Create Superuser (if not already created)
```bash
python manage.py createsuperuser
```

### Step 5: Start Development Server
```bash
python manage.py runserver
```

### Step 6: Access Admin Panel
- Open browser: http://127.0.0.1:8000/admin/
- Login with superuser credentials
- Verify all 6 models are visible:
  - System Failure Scenarios
  - Model Drift Alerts
  - Classification Errors
  - Data Quality Metrics
  - Legal Risk Logs
  - Incident Logs

---

## Next Steps (Not Yet Implemented)

### 1. Celery Beat Integration
Create management command to run drift detection daily:
```python
# risk_management/management/commands/check_model_drift.py
python manage.py check_model_drift
```

### 2. Alert Notifications
Implement email/Slack notifications for:
- Critical model drift detected
- Legal risk escalation
- System incidents
- Data quality issues

### 3. Risk Dashboard Page
Create `/risk-dashboard/` page with:
- System failure scenario status
- Model drift trends
- Classification error rate
- Data quality metrics
- Legal risk summary
- Incident timeline

### 4. Fallback Strategy Implementation
Integrate fallback strategies into actual API calls:
- GEE → Copernicus → Cache → Unverifiable
- Yahoo Finance → Alpha Vantage → Cache → Stale
- Implement circuit breaker pattern

### 5. Legal Disclaimer Templates
Create reusable disclaimer templates:
- Investment advice disclaimer
- Greenwash flag disclaimer
- Data privacy disclaimer
- Methodology transparency

### 6. 4-Tier Greenwash Flag System
Implement in greenwash_detector:
- Green: Verified Consistent (confidence > 85%)
- Yellow: Needs Review (confidence 50-85%)
- Red: High Inconsistency (confidence > 85%)
- Grey: Insufficient Data (pre-2015 or cloud cover)

---

## Files Created/Modified

### Created:
- `risk_management/apps.py` — App configuration
- `risk_management/admin.py` — Django admin interface (6 models with color-coded badges)
- `risk_management/__init__.py` — Package initialization
- `risk_management/migrations/__init__.py` — Migrations package
- `risk_management/migrations/0001_initial.py` — Initial migration (auto-generated)
- `CATEGORY_14_IMPLEMENTATION.md` — This file

### Modified:
- `risk_management/models.py` — 6 risk models (already existed)
- `risk_management/monitoring.py` — Monitoring utilities (already existed)
- `greenlens/settings.py` — Added risk_management to INSTALLED_APPS
- `data_ingestion/migrations/0010_add_spatial_indexes.py` — Fixed dependency
- `data_ingestion/views.py` — Added missing api_view import

---

## Database Schema

```sql
-- System Failure Scenarios
CREATE TABLE risk_management_systemfailurescenario (
    id BIGINT PRIMARY KEY,
    name VARCHAR(255),
    description TEXT,
    scenario_type VARCHAR(50),
    probability VARCHAR(20),
    severity VARCHAR(20),
    impact_description TEXT,
    affected_modules JSONB,
    mitigation_strategy TEXT,
    mitigation_status VARCHAR(20),
    has_fallback BOOLEAN,
    fallback_description TEXT,
    recovery_time_minutes INT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    last_reviewed_at TIMESTAMP
);

-- Model Drift Alerts
CREATE TABLE risk_management_modeldriftalert (
    id BIGINT PRIMARY KEY,
    model_name VARCHAR(100),
    drift_type VARCHAR(30),
    previous_accuracy FLOAT,
    current_accuracy FLOAT,
    accuracy_drop_percentage FLOAT,
    description TEXT,
    affected_predictions INT,
    alert_severity VARCHAR(20),
    action_taken TEXT,
    retraining_scheduled BOOLEAN,
    retraining_date TIMESTAMP,
    detected_at TIMESTAMP,
    resolved_at TIMESTAMP
);

-- Classification Errors
CREATE TABLE risk_management_classificationerror (
    id BIGINT PRIMARY KEY,
    bond_id VARCHAR(100),
    error_type VARCHAR(30),
    predicted_value VARCHAR(255),
    actual_value VARCHAR(255),
    error_description TEXT,
    severity VARCHAR(20),
    potential_user_impact TEXT,
    root_cause TEXT,
    root_cause_category VARCHAR(50),
    is_resolved BOOLEAN,
    resolution_action TEXT,
    resolved_at TIMESTAMP,
    reported_at TIMESTAMP,
    reported_by VARCHAR(255)
);

-- Data Quality Metrics
CREATE TABLE risk_management_dataqualitymetric (
    id BIGINT PRIMARY KEY,
    metric_name VARCHAR(100),
    metric_type VARCHAR(50),
    value FLOAT,
    threshold_warning FLOAT,
    threshold_critical FLOAT,
    status VARCHAR(20),
    description TEXT,
    affected_records INT,
    measured_at TIMESTAMP
);

-- Legal Risk Logs
CREATE TABLE risk_management_legalrisklog (
    id BIGINT PRIMARY KEY,
    risk_type VARCHAR(30),
    description TEXT,
    severity VARCHAR(20),
    mitigation_action TEXT,
    mitigation_status VARCHAR(20),
    compliance_requirement VARCHAR(255),
    compliance_deadline DATE,
    identified_at TIMESTAMP,
    resolved_at TIMESTAMP,
    legal_review_required BOOLEAN
);

-- Incident Logs
CREATE TABLE risk_management_incidentlog (
    id BIGINT PRIMARY KEY,
    incident_type VARCHAR(30),
    title VARCHAR(255),
    description TEXT,
    status VARCHAR(20),
    affected_users INT,
    affected_bonds INT,
    downtime_minutes INT,
    root_cause TEXT,
    resolution_action TEXT,
    detected_at TIMESTAMP,
    resolved_at TIMESTAMP
);
```

---

## Testing the Implementation

### 1. Create Test Data via Admin Panel
- Go to http://127.0.0.1:8000/admin/
- Add a System Failure Scenario
- Add a Model Drift Alert
- Add a Classification Error
- Add a Data Quality Metric
- Add a Legal Risk Log
- Add an Incident Log

### 2. Verify Color-Coded Badges
- Check that badges display with correct colors
- Verify risk scores are calculated correctly
- Check that filters work properly

### 3. Test Search Functionality
- Search by name, description, bond_id
- Verify results are accurate

### 4. Test Collapsible Fieldsets
- Click on "Fallback & Recovery" section
- Click on "Metadata" section
- Verify sections expand/collapse correctly

---

## Risk Mitigation Framework Summary

```
┌─────────────────────────────────────┐
│    GREENLENS RISK SHIELD            │
├─────────────────────────────────────┤
│                                     │
│  Technical Risks:                   │
│  ✓ Multi-API fallback               │
│  ✓ Drift detection alerts           │
│  ✓ Confidence intervals             │
│  ✓ Data source transparency         │
│                                     │
│  Classification Risks:              │
│  ✓ 4-tier flag system               │
│  ✓ Never "confirmed" — always       │
│    "potential inconsistency"         │
│  ✓ Human review recommended         │
│  ✓ Appeal process for issuers       │
│                                     │
│  Legal Risks:                       │
│  ✓ Investment disclaimer            │
│  ✓ Research tool positioning        │
│  ✓ Methodology transparency         │
│  ✓ GDPR anonymous usage            │
│                                     │
└─────────────────────────────────────┘
```

---

## Compliance Checklist

- [x] System failure scenarios documented
- [x] Classification errors tracked
- [x] Legal risks identified
- [x] Database models created
- [x] Admin interface implemented
- [x] Migrations created and applied
- [ ] Celery beat integration (TODO)
- [ ] Alert notifications (TODO)
- [ ] Risk dashboard page (TODO)
- [ ] Fallback strategy implementation (TODO)
- [ ] Legal disclaimer templates (TODO)
- [ ] 4-tier greenwash flag system (TODO)

---

## Questions & Answers

**Q: What if Google Earth Engine API is down?**
A: Fallback to Copernicus API → cached NDVI values → flag as "unverifiable"

**Q: What if the model drifts?**
A: Monthly automated drift detection alerts team, flags dashboard as "Scores under review", schedules retraining

**Q: What if we flag a legitimate green project as greenwash?**
A: Never say "Confirmed Greenwash" — always "Potential inconsistency", show confidence score, recommend independent verification, provide appeal process

**Q: What about GDPR compliance?**
A: Currently anonymous usage (no user data collection). If user accounts added, GDPR compliance becomes mandatory.

**Q: Can users sue GreenLens for investment losses?**
A: Prominent disclaimer on every page: "This is NOT financial advice, investment recommendation, or certified ESG rating."

---

## Support & Maintenance

For questions or issues:
1. Check the admin panel for existing risk logs
2. Review the monitoring utilities in `risk_management/monitoring.py`
3. Check the models in `risk_management/models.py`
4. Refer to the CATEGORY_14_IMPLEMENTATION.md documentation

---

**Last Updated:** April 27, 2026
**Status:** ✅ Complete — Ready for Celery integration and alert notifications
