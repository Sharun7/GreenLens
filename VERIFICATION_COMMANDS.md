# GreenLens Verification Commands

## Quick Verification (5 minutes)

### 1. Verify Django Setup
```bash
python manage.py check
```

**Expected Output:**
```
System check identified no issues (0 silenced).
```

### 2. Verify Database Migrations
```bash
python manage.py showmigrations
```

**Expected Output:**
```
[X] 0001_initial
[X] 0002_...
[X] 0003_...
... (all migrations marked with [X])
```

### 3. Verify Admin Panel
```bash
python manage.py runserver
```

**Then open:** http://127.0.0.1:8000/admin/

**Expected:** Login page with superuser credentials

### 4. Verify Models in Admin
After logging in, you should see:

**Business App:**
- Organizations
- User Profiles
- Usage Logs
- Invoices
- Features

**Risk Management App:**
- System Failure Scenarios
- Model Drift Alerts
- Classification Errors
- Data Quality Metrics
- Legal Risk Logs
- Incident Logs

---

## Detailed Verification (15 minutes)

### 1. Check INSTALLED_APPS
```bash
python manage.py shell
```

```python
from django.conf import settings
print("INSTALLED_APPS:")
for app in settings.INSTALLED_APPS:
    print(f"  - {app}")
```

**Expected Output:**
```
INSTALLED_APPS:
  - django.contrib.admin
  - django.contrib.auth
  - django.contrib.contenttypes
  - django.contrib.sessions
  - django.contrib.messages
  - django.contrib.staticfiles
  - rest_framework
  - drf_spectacular
  - django_celery_beat
  - django_celery_results
  - data_ingestion.apps.DataIngestionConfig
  - risk_scoring.apps.RiskScoringConfig
  - pricing_analysis.apps.PricingAnalysisConfig
  - greenwash_detector.apps.GreenwashDetectorConfig
  - dashboard.apps.DashboardConfig
  - business.apps.BusinessConfig
  - risk_management.apps.RiskManagementConfig
```

### 2. Check Middleware
```bash
python manage.py shell
```

```python
from django.conf import settings
print("MIDDLEWARE:")
for middleware in settings.MIDDLEWARE:
    print(f"  - {middleware}")
```

**Expected Output:**
```
MIDDLEWARE:
  - django.middleware.security.SecurityMiddleware
  - whitenoise.middleware.WhiteNoiseMiddleware
  - django.contrib.sessions.middleware.SessionMiddleware
  - django.middleware.common.CommonMiddleware
  - django.middleware.csrf.CsrfViewMiddleware
  - django.contrib.auth.middleware.AuthenticationMiddleware
  - django.contrib.messages.middleware.MessageMiddleware
  - django.middleware.clickjacking.XFrameOptionsMiddleware
  - business.middleware.RateLimitMiddleware
  - business.middleware.UsageTrackingMiddleware
  - business.middleware.FeatureAccessMiddleware
```

### 3. Check Business Models
```bash
python manage.py shell
```

```python
from business.models import Organization, UserProfile, UsageLog, Invoice, Feature

print("Business Models:")
print(f"  - Organization: {Organization.objects.count()} records")
print(f"  - UserProfile: {UserProfile.objects.count()} records")
print(f"  - UsageLog: {UsageLog.objects.count()} records")
print(f"  - Invoice: {Invoice.objects.count()} records")
print(f"  - Feature: {Feature.objects.count()} records")
```

**Expected Output:**
```
Business Models:
  - Organization: 0 records
  - UserProfile: 0 records
  - UsageLog: 0 records
  - Invoice: 0 records
  - Feature: 0 records
```

### 4. Check Risk Management Models
```bash
python manage.py shell
```

```python
from risk_management.models import (
    SystemFailureScenario,
    ModelDriftAlert,
    ClassificationError,
    DataQualityMetric,
    LegalRiskLog,
    IncidentLog
)

print("Risk Management Models:")
print(f"  - SystemFailureScenario: {SystemFailureScenario.objects.count()} records")
print(f"  - ModelDriftAlert: {ModelDriftAlert.objects.count()} records")
print(f"  - ClassificationError: {ClassificationError.objects.count()} records")
print(f"  - DataQualityMetric: {DataQualityMetric.objects.count()} records")
print(f"  - LegalRiskLog: {LegalRiskLog.objects.count()} records")
print(f"  - IncidentLog: {IncidentLog.objects.count()} records")
```

**Expected Output:**
```
Risk Management Models:
  - SystemFailureScenario: 0 records
  - ModelDriftAlert: 0 records
  - ClassificationError: 0 records
  - DataQualityMetric: 0 records
  - LegalRiskLog: 0 records
  - IncidentLog: 0 records
```

### 5. Check Admin Registration
```bash
python manage.py shell
```

```python
from django.contrib import admin
from django.apps import apps

print("Registered Models in Admin:")
for model, admin_class in admin.site._registry.items():
    print(f"  - {model._meta.app_label}.{model.__name__}")
```

**Expected Output:**
```
Registered Models in Admin:
  - auth.Group
  - auth.User
  - business.Feature
  - business.Invoice
  - business.Organization
  - business.UserProfile
  - business.UsageLog
  - data_ingestion.ClimateHazardData
  - data_ingestion.GreenBond
  - django_celery_beat.ClockedSchedule
  - django_celery_beat.CrontabSchedule
  - django_celery_beat.IntervalSchedule
  - django_celery_beat.PeriodicTask
  - django_celery_beat.SolarSchedule
  - django_celery_results.GroupResult
  - django_celery_results.TaskResult
  - greenwash_detector.GreenwashFlag
  - pricing_analysis.PricingGap
  - pricing_analysis.YieldSpread
  - risk_management.ClassificationError
  - risk_management.DataQualityMetric
  - risk_management.IncidentLog
  - risk_management.LegalRiskLog
  - risk_management.ModelDriftAlert
  - risk_management.SystemFailureScenario
  - risk_scoring.ModelFeedback
  - risk_scoring.PCRSScore
  - risk_scoring.SHAPValue
```

### 6. Check Database Tables
```bash
python manage.py shell
```

```python
from django.db import connection

cursor = connection.cursor()
cursor.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    ORDER BY table_name
""")

print("Database Tables:")
for row in cursor.fetchall():
    print(f"  - {row[0]}")
```

**Expected Output:**
```
Database Tables:
  - auth_group
  - auth_group_permissions
  - auth_permission
  - auth_user
  - auth_user_groups
  - auth_user_user_permissions
  - business_feature
  - business_invoice
  - business_organization
  - business_userprofile
  - business_usagelog
  - data_ingestion_climatehazarddata
  - data_ingestion_greenbond
  - django_admin_log
  - django_celery_beat_clockedschedule
  - django_celery_beat_crontabschedule
  - django_celery_beat_intervalschedule
  - django_celery_beat_periodictask
  - django_celery_beat_solarshedule
  - django_celery_results_groupresult
  - django_celery_results_taskresult
  - django_content_type
  - django_migrations
  - django_session
  - greenwash_detector_greenwashflag
  - pricing_analysis_pricinggap
  - pricing_analysis_yieldspread
  - risk_management_classificationerror
  - risk_management_dataqualitymetric
  - risk_management_incidentlog
  - risk_management_legalrisklog
  - risk_management_modeldriftalert
  - risk_management_systemfailurescenario
  - risk_scoring_modelfeedback
  - risk_scoring_pcrsscore
  - risk_scoring_shapvalue
```

---

## API Verification (10 minutes)

### 1. Test Bond API
```bash
curl http://127.0.0.1:8000/api/bonds/
```

**Expected:** JSON response with bonds list

### 2. Test Viewport API
```bash
curl "http://127.0.0.1:8000/api/bonds/viewport/?min_lat=40&max_lat=50&min_lon=-10&max_lon=10&zoom=5"
```

**Expected:** JSON response with bonds in viewport

### 3. Test Bias Detection API
```bash
curl http://127.0.0.1:8000/api/risk/bias-detection/
```

**Expected:** JSON response with bias analysis

### 4. Test Bias Summary API
```bash
curl http://127.0.0.1:8000/api/risk/bias-summary/
```

**Expected:** JSON response with bias summary

---

## Admin Interface Verification (10 minutes)

### 1. Create Test Organization
1. Go to http://127.0.0.1:8000/admin/
2. Click "Organizations" under Business
3. Click "Add Organization"
4. Fill in:
   - Name: "Test Organization"
   - Slug: "test-org"
   - Tier: "Professional"
   - Billing Email: "test@example.com"
   - Contact Name: "Test User"
5. Click "Save"

**Expected:** Organization created successfully

### 2. Create Test Risk Scenario
1. Go to http://127.0.0.1:8000/admin/
2. Click "System Failure Scenarios" under Risk Management
3. Click "Add System Failure Scenario"
4. Fill in:
   - Name: "Test Scenario"
   - Description: "Test description"
   - Scenario Type: "api_failure"
   - Probability: "medium"
   - Severity: "high"
   - Impact Description: "Test impact"
   - Affected Modules: ["test_module"]
   - Mitigation Strategy: "Test mitigation"
   - Mitigation Status: "identified"
5. Click "Save"

**Expected:** Scenario created successfully with risk score calculated

### 3. Verify Color-Coded Badges
1. Go to http://127.0.0.1:8000/admin/risk_management/systemfailurescenario/
2. Look for the test scenario
3. Verify badges are displayed with colors:
   - Scenario Type: Red badge
   - Probability: Orange badge
   - Severity: Orange badge
   - Status: Red badge
   - Risk Score: Orange badge

**Expected:** All badges display with correct colors

### 4. Test Search Functionality
1. Go to http://127.0.0.1:8000/admin/business/organization/
2. Type "Test" in the search box
3. Press Enter

**Expected:** Test organization appears in results

### 5. Test Filtering
1. Go to http://127.0.0.1:8000/admin/business/organization/
2. Click "Professional" under Tier filter
3. Click "Active" under Is Active filter

**Expected:** Only Professional tier active organizations shown

---

## Performance Verification (5 minutes)

### 1. Check Database Indexes
```bash
python manage.py shell
```

```python
from django.db import connection

cursor = connection.cursor()
cursor.execute("""
    SELECT indexname, indexdef 
    FROM pg_indexes 
    WHERE schemaname = 'public'
    ORDER BY indexname
""")

print("Database Indexes:")
for row in cursor.fetchall():
    print(f"  - {row[0]}")
```

**Expected:** Multiple indexes for performance

### 2. Check Query Performance
```bash
python manage.py shell
```

```python
from django.test.utils import override_settings
from django.db import connection
from django.test import TestCase
from business.models import Organization

# Enable query logging
from django.conf import settings
settings.DEBUG = True

# Query organizations
orgs = Organization.objects.all()
print(f"Queries executed: {len(connection.queries)}")
for query in connection.queries:
    print(f"  - {query['time']}s: {query['sql'][:100]}...")
```

**Expected:** Queries execute quickly with proper indexes

---

## Celery Verification (5 minutes)

### 1. Check Celery Configuration
```bash
python manage.py shell
```

```python
from django.conf import settings

print("Celery Configuration:")
print(f"  - CELERY_BROKER_URL: {settings.CELERY_BROKER_URL}")
print(f"  - CELERY_RESULT_BACKEND: {settings.CELERY_RESULT_BACKEND}")
print(f"  - CELERY_TIMEZONE: {settings.CELERY_TIMEZONE}")
```

**Expected:** Celery URLs configured correctly

### 2. Check Celery Beat Schedule
```bash
python manage.py shell
```

```python
from django.conf import settings

print("Celery Beat Schedule:")
for task_name, task_config in settings.CELERY_BEAT_SCHEDULE.items():
    print(f"  - {task_name}: {task_config['schedule']}")
```

**Expected:** All scheduled tasks listed

---

## Complete Verification Script

Save this as `verify_greenlens.py`:

```python
#!/usr/bin/env python
"""
Complete GreenLens verification script.
Run: python verify_greenlens.py
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'greenlens.settings')
django.setup()

from django.conf import settings
from django.contrib import admin
from django.db import connection
from business.models import Organization, UserProfile, UsageLog, Invoice, Feature
from risk_management.models import (
    SystemFailureScenario,
    ModelDriftAlert,
    ClassificationError,
    DataQualityMetric,
    LegalRiskLog,
    IncidentLog
)

def verify_installed_apps():
    """Verify all apps are installed."""
    required_apps = [
        'business.apps.BusinessConfig',
        'risk_management.apps.RiskManagementConfig',
    ]
    
    for app in required_apps:
        if app in settings.INSTALLED_APPS:
            print(f"✓ {app}")
        else:
            print(f"✗ {app} NOT FOUND")
            return False
    return True

def verify_middleware():
    """Verify all middleware is configured."""
    required_middleware = [
        'business.middleware.RateLimitMiddleware',
        'business.middleware.UsageTrackingMiddleware',
        'business.middleware.FeatureAccessMiddleware',
    ]
    
    for middleware in required_middleware:
        if middleware in settings.MIDDLEWARE:
            print(f"✓ {middleware}")
        else:
            print(f"✗ {middleware} NOT FOUND")
            return False
    return True

def verify_models():
    """Verify all models are created."""
    models = [
        ('Organization', Organization),
        ('UserProfile', UserProfile),
        ('UsageLog', UsageLog),
        ('Invoice', Invoice),
        ('Feature', Feature),
        ('SystemFailureScenario', SystemFailureScenario),
        ('ModelDriftAlert', ModelDriftAlert),
        ('ClassificationError', ClassificationError),
        ('DataQualityMetric', DataQualityMetric),
        ('LegalRiskLog', LegalRiskLog),
        ('IncidentLog', IncidentLog),
    ]
    
    for name, model in models:
        try:
            count = model.objects.count()
            print(f"✓ {name}: {count} records")
        except Exception as e:
            print(f"✗ {name}: {str(e)}")
            return False
    return True

def verify_admin_registration():
    """Verify all models are registered in admin."""
    required_models = [
        'business.Organization',
        'business.UserProfile',
        'business.UsageLog',
        'business.Invoice',
        'business.Feature',
        'risk_management.SystemFailureScenario',
        'risk_management.ModelDriftAlert',
        'risk_management.ClassificationError',
        'risk_management.DataQualityMetric',
        'risk_management.LegalRiskLog',
        'risk_management.IncidentLog',
    ]
    
    registered = [f"{model._meta.app_label}.{model.__name__}" 
                  for model in admin.site._registry.keys()]
    
    for model in required_models:
        if model in registered:
            print(f"✓ {model}")
        else:
            print(f"✗ {model} NOT REGISTERED")
            return False
    return True

def verify_database_tables():
    """Verify all database tables exist."""
    cursor = connection.cursor()
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    
    tables = [row[0] for row in cursor.fetchall()]
    
    required_tables = [
        'business_organization',
        'business_userprofile',
        'business_usagelog',
        'business_invoice',
        'business_feature',
        'risk_management_systemfailurescenario',
        'risk_management_modeldriftalert',
        'risk_management_classificationerror',
        'risk_management_dataqualitymetric',
        'risk_management_legalrisklog',
        'risk_management_incidentlog',
    ]
    
    for table in required_tables:
        if table in tables:
            print(f"✓ {table}")
        else:
            print(f"✗ {table} NOT FOUND")
            return False
    return True

def main():
    """Run all verifications."""
    print("\n" + "="*60)
    print("GreenLens Verification")
    print("="*60 + "\n")
    
    print("1. Checking INSTALLED_APPS...")
    if not verify_installed_apps():
        print("✗ INSTALLED_APPS verification failed\n")
        return False
    print("✓ INSTALLED_APPS verified\n")
    
    print("2. Checking MIDDLEWARE...")
    if not verify_middleware():
        print("✗ MIDDLEWARE verification failed\n")
        return False
    print("✓ MIDDLEWARE verified\n")
    
    print("3. Checking Models...")
    if not verify_models():
        print("✗ Models verification failed\n")
        return False
    print("✓ Models verified\n")
    
    print("4. Checking Admin Registration...")
    if not verify_admin_registration():
        print("✗ Admin registration verification failed\n")
        return False
    print("✓ Admin registration verified\n")
    
    print("5. Checking Database Tables...")
    if not verify_database_tables():
        print("✗ Database tables verification failed\n")
        return False
    print("✓ Database tables verified\n")
    
    print("="*60)
    print("✓ ALL VERIFICATIONS PASSED")
    print("="*60 + "\n")
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
```

**Run verification:**
```bash
python verify_greenlens.py
```

**Expected Output:**
```
============================================================
GreenLens Verification
============================================================

1. Checking INSTALLED_APPS...
✓ business.apps.BusinessConfig
✓ risk_management.apps.RiskManagementConfig
✓ INSTALLED_APPS verified

2. Checking MIDDLEWARE...
✓ business.middleware.RateLimitMiddleware
✓ business.middleware.UsageTrackingMiddleware
✓ business.middleware.FeatureAccessMiddleware
✓ MIDDLEWARE verified

3. Checking Models...
✓ Organization: 0 records
✓ UserProfile: 0 records
✓ UsageLog: 0 records
✓ Invoice: 0 records
✓ Feature: 0 records
✓ SystemFailureScenario: 0 records
✓ ModelDriftAlert: 0 records
✓ ClassificationError: 0 records
✓ DataQualityMetric: 0 records
✓ LegalRiskLog: 0 records
✓ IncidentLog: 0 records
✓ Models verified

4. Checking Admin Registration...
✓ business.Organization
✓ business.UserProfile
✓ business.UsageLog
✓ business.Invoice
✓ business.Feature
✓ risk_management.SystemFailureScenario
✓ risk_management.ModelDriftAlert
✓ risk_management.ClassificationError
✓ risk_management.DataQualityMetric
✓ risk_management.LegalRiskLog
✓ risk_management.IncidentLog
✓ Admin registration verified

5. Checking Database Tables...
✓ business_organization
✓ business_userprofile
✓ business_usagelog
✓ business_invoice
✓ business_feature
✓ risk_management_systemfailurescenario
✓ risk_management_modeldriftalert
✓ risk_management_classificationerror
✓ risk_management_dataqualitymetric
✓ risk_management_legalrisklog
✓ risk_management_incidentlog
✓ Database tables verified

============================================================
✓ ALL VERIFICATIONS PASSED
============================================================
```

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'business'"
**Solution:** Ensure INSTALLED_APPS includes 'business.apps.BusinessConfig'

### Issue: "Table does not exist"
**Solution:** Run migrations: `python manage.py migrate`

### Issue: "Model not registered in admin"
**Solution:** Check admin.py has @admin.register() decorator

### Issue: "Middleware not working"
**Solution:** Ensure middleware is in MIDDLEWARE list in settings.py

---

**Last Updated:** April 27, 2026
**Status:** ✅ All verifications passing
