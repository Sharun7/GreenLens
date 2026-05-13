# Regulatory Alerts - Quick Start Guide

## Overview

Regulatory alerts are now automatically generated from REAL scraped data. When new regulations are fetched from EU SFDR or SEBI, the system automatically creates alerts for affected bonds.

---

## Quick Start

### 1. Trigger Regulatory Update (Manual)

```bash
python manage.py shell
```

```python
from ai_features.tasks import refresh_regulatory_updates

# Fetch latest regulations and generate alerts
result = refresh_regulatory_updates()
print(result)
```

**Expected output**:
```python
{
    'success': True,
    'updates_fetched': 5,
    'updates_saved': 3,
    'last_updated': datetime(2024, 1, 15, 6, 0, 0),
}
```

### 2. View Generated Alerts

Visit the alerts feed:
```
http://127.0.0.1:8000/ai/alerts/?type=regulatory
```

You should see:
- Alert title with urgency prefix (URGENT, HIGH, MEDIUM)
- Compliance deadline badge
- Days until deadline
- Affected bonds count
- First 5 affected bonds with links

---

## Manual Testing

### Create Test Regulation

```bash
python manage.py shell
```

```python
from ai_features.models import RegulatoryMonitor
from datetime import date, timedelta

# Create test EU regulation
regulation = RegulatoryMonitor.objects.create(
    regulation_type="eu_sfdr",
    title="Test SFDR Disclosure Requirements",
    description="New disclosure requirements for Article 8 and 9 funds",
    announcement_date=date.today(),
    effective_date=date.today() + timedelta(days=60),  # 60 days from now
    impact_description="All EU Green Bond Standard bonds must provide enhanced climate impact metrics",
    compliance_required=True,
    action_required="Update bond documentation with new climate metrics",
    source_url="https://www.esma.europa.eu/test",
)

print(f"Created regulation: {regulation.title}")
```

### Generate Alert for Test Regulation

```python
from ai_features.tasks import generate_regulatory_alerts

# Generate alerts
result = generate_regulatory_alerts()
print(result)
# {'success': True, 'regulations_processed': 1, 'alerts_created': 1, 'alerts_skipped': 0}
```

### Verify Alert Was Created

```python
from ai_features.models import AutomatedAlert

# Get latest regulatory alert
alert = AutomatedAlert.objects.filter(alert_type="regulatory").last()

print(f"Alert title: {alert.title}")
print(f"Affected bonds: {alert.affected_bonds.count()}")
print(f"Urgency: {alert.alert_data['urgency']}")
print(f"Days until effective: {alert.alert_data['days_until_effective']}")
print(f"Compliance required: {alert.alert_data['compliance_required']}")
```

**Expected output**:
```
Alert title: HIGH: Test SFDR Disclosure Requirements
Affected bonds: 15
Urgency: HIGH
Days until effective: 60
Compliance required: True
```

---

## Celery Task Testing

### Test Alert Generation Task

```bash
# Test alert generation task
celery -A greenlens call ai_features.generate_regulatory_alerts
```

**Expected output**:
```
[2024-01-15 06:30:00,123: INFO] Task ai_features.generate_regulatory_alerts succeeded
Result: {'success': True, 'regulations_processed': 1, 'alerts_created': 1, 'alerts_skipped': 0}
```

### Test Full Flow (Scraping + Alert Generation)

```bash
# Test full flow
celery -A greenlens call ai_features.refresh_regulatory_updates
```

**Expected output**:
```
[2024-01-15 06:00:00,123: INFO] Task ai_features.refresh_regulatory_updates succeeded
Result: {'success': True, 'updates_fetched': 5, 'updates_saved': 3, 'last_updated': '2024-01-15T06:00:00'}
```

---

## Verify Affected Bonds Mapping

### Check EU Bonds

```python
from data_ingestion.models import GreenBond

# Check EU bonds with EU_GBS framework
eu_bonds = GreenBond.objects.filter(regulatory_framework="EU_GBS")
print(f"EU bonds: {eu_bonds.count()}")

# Check by country
for country in ["France", "Germany", "Netherlands"]:
    count = eu_bonds.filter(country=country).count()
    print(f"  {country}: {count} bonds")
```

### Check SEBI Bonds

```python
# Check Indian bonds with SEBI framework
sebi_bonds = GreenBond.objects.filter(
    regulatory_framework="SEBI",
    country="India"
)
print(f"SEBI bonds: {sebi_bonds.count()}")
```

---

## View Alert in Dashboard

### 1. Start Django Server

```bash
python manage.py runserver
```

### 2. Navigate to Alerts Feed

```
http://127.0.0.1:8000/ai/alerts/
```

### 3. Filter by Regulatory Alerts

Click on "Regulatory" filter pill or visit:
```
http://127.0.0.1:8000/ai/alerts/?type=regulatory
```

### 4. Verify Alert Display

You should see:

```
┌─────────────────────────────────────────────────────────────┐
│ 📋 HIGH: Test SFDR Disclosure Requirements      [Pending]   │
│                                                               │
│ EU SFDR update: New disclosure requirements for Article 8    │
│ and 9 funds                                                   │
│                                                               │
│ [⏰ HIGH - 60 days left]                                     │
│ Compliance deadline: Mar 15, 2024                            │
│                                                               │
│ [Regulatory Change] [dashboard] [15 bonds affected]          │
│                                                               │
│ Affected bonds: [BOND_001] [BOND_002] [BOND_003] [BOND_004] │
│                 [BOND_005] [+10 more]                        │
│                                                               │
│ Jan 15, 2024 06:30                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Automatic Scheduling

### Celery Beat Schedule

Regulatory alerts are generated automatically:

```python
# greenlens/settings.py
CELERY_BEAT_SCHEDULE = {
    "daily-refresh-regulatory-updates": {
        "task": "ai_features.refresh_regulatory_updates",
        "schedule": crontab(hour=6, minute=0),  # Daily at 06:00 UTC
        "options": {"expires": 82800},
    },
}
```

### Start Celery Beat

```bash
celery -A greenlens beat --loglevel=info
```

**Expected output**:
```
Scheduler: Sending due task daily-refresh-regulatory-updates (ai_features.refresh_regulatory_updates)
```

---

## Troubleshooting

### No Alerts Generated

**Problem**: `generate_regulatory_alerts()` returns `alerts_created: 0`

**Solutions**:

1. Check if regulations exist:
```python
from ai_features.models import RegulatoryMonitor
from datetime import timedelta
from django.utils import timezone

cutoff = timezone.now() - timedelta(hours=24)
new_regs = RegulatoryMonitor.objects.filter(created_at__gte=cutoff)
print(f"New regulations: {new_regs.count()}")
```

2. Check if bonds exist with matching framework:
```python
from data_ingestion.models import GreenBond

eu_bonds = GreenBond.objects.filter(regulatory_framework="EU_GBS")
sebi_bonds = GreenBond.objects.filter(regulatory_framework="SEBI")

print(f"EU bonds: {eu_bonds.count()}")
print(f"SEBI bonds: {sebi_bonds.count()}")
```

3. Check if alert already exists (duplicate):
```python
from ai_features.models import AutomatedAlert

existing = AutomatedAlert.objects.filter(
    alert_type="regulatory",
    title__icontains="Test SFDR"
)
print(f"Existing alerts: {existing.count()}")
```

### Affected Bonds Count is 0

**Problem**: Alert created but `affected_bonds_count: 0`

**Solutions**:

1. Check regulatory framework mapping:
```python
regulation = RegulatoryMonitor.objects.last()
print(f"Regulation type: {regulation.regulation_type}")

# Check mapping
regulation_mapping = {
    "eu_sfdr": "EU_GBS",
    "eu_taxonomy": "EU_GBS",
    "sebi_brsr": "SEBI",
    "rbi_climate": "SEBI",
}
framework = regulation_mapping.get(regulation.regulation_type)
print(f"Mapped framework: {framework}")

# Check bonds
bonds = GreenBond.objects.filter(regulatory_framework=framework)
print(f"Bonds with framework: {bonds.count()}")
```

2. Check country filtering:
```python
# For EU regulations
if regulation.regulation_type in ["eu_sfdr", "eu_taxonomy"]:
    eu_countries = ["France", "Germany", "Netherlands", ...]
    bonds = bonds.filter(country__in=eu_countries)
    print(f"EU bonds: {bonds.count()}")

# For SEBI regulations
if regulation.regulation_type in ["sebi_brsr", "rbi_climate"]:
    bonds = bonds.filter(country="India")
    print(f"Indian bonds: {bonds.count()}")
```

---

## Summary

**Quick Commands**:

```bash
# Manual trigger
python manage.py shell -c "from ai_features.tasks import refresh_regulatory_updates; print(refresh_regulatory_updates())"

# Test alert generation
celery -A greenlens call ai_features.generate_regulatory_alerts

# View alerts
http://127.0.0.1:8000/ai/alerts/?type=regulatory
```

**Expected Results**:
- ✅ Regulations scraped from EU SFDR and SEBI
- ✅ Alerts auto-generated for new regulations
- ✅ Affected bonds identified by regulatory framework
- ✅ Compliance deadline displayed with urgency
- ✅ Affected bonds count and links shown

**All data is REAL** - no placeholders, no hardcoded data.
