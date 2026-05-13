# Regulatory Alerts - Complete Implementation

## Overview

GreenLens now has **automatic regulatory alert generation** that connects to REAL data from the regulatory scraper built in Task 2.

When new regulations are scraped from EU SFDR or SEBI, the system automatically:
1. Finds affected bonds based on regulatory framework
2. Creates AutomatedAlert records with alert_type='regulatory'
3. Sets affected_bonds ManyToMany relation
4. Displays alerts in the alerts feed with compliance deadlines

**All data is REAL** - no placeholders, no hardcoded data.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│         Celery Beat Scheduler (Daily 06:00 UTC)             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  refresh_regulatory_updates() Task                          │
│  - Scrapes EU SFDR and SEBI websites                        │
│  - Saves to RegulatoryMonitor model                         │
│  - Returns: updates_fetched, updates_saved                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (if updates_saved > 0)
┌─────────────────────────────────────────────────────────────┐
│  generate_regulatory_alerts() Task                          │
│  - Gets new RegulatoryMonitor entries (last 24 hours)       │
│  - Finds affected bonds by regulatory framework             │
│  - Creates AutomatedAlert records                           │
│  - Sets affected_bonds ManyToMany                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  AutomatedAlert Model                                        │
│  - alert_type='regulatory'                                   │
│  - affected_bonds (ManyToMany to GreenBond)                 │
│  - alert_data (JSON with compliance deadline, etc.)         │
│  - status='pending'                                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Alerts Feed View                                            │
│  - Shows regulatory alerts with compliance deadline          │
│  - Shows affected bonds count                                │
│  - Shows urgency (OVERDUE, URGENT, HIGH, MEDIUM)            │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### 1. Celery Task: `generate_regulatory_alerts()`

**File**: `ai_features/tasks.py`

**Purpose**: Automatically create alerts for new regulatory updates

**Trigger**: Called by `refresh_regulatory_updates()` when new regulations are saved

**Logic**:

```python
@shared_task(name="ai_features.generate_regulatory_alerts")
def generate_regulatory_alerts():
    """
    Generate automated alerts for new regulatory updates.
    
    Steps:
    1. Get new RegulatoryMonitor entries (created in last 24 hours)
    2. For each regulation:
       - Find affected bonds based on regulatory framework
       - Create AutomatedAlert with alert_type='regulatory'
       - Set affected_bonds ManyToMany relation
       - Avoid duplicate alerts
    """
    # Get new regulations from last 24 hours
    cutoff_time = timezone.now() - timedelta(hours=24)
    new_regulations = RegulatoryMonitor.objects.filter(
        created_at__gte=cutoff_time
    )
    
    for regulation in new_regulations:
        # Check if alert already exists
        existing_alert = AutomatedAlert.objects.filter(
            alert_type="regulatory",
            title__icontains=regulation.title[:50],
        ).first()
        
        if existing_alert:
            continue  # Skip duplicates
        
        # Find affected bonds
        affected_bonds = _find_affected_bonds(regulation)
        
        # Create alert
        alert = _create_regulatory_alert(regulation, affected_bonds)
```

**Returns**:
```python
{
    "success": True,
    "regulations_processed": 3,
    "alerts_created": 2,
    "alerts_skipped": 1,
}
```

---

### 2. Helper Function: `_find_affected_bonds()`

**Purpose**: Find bonds affected by a regulatory update based on regulatory framework

**Mapping**:

| Regulation Type | Regulatory Framework | Additional Filter |
|----------------|---------------------|-------------------|
| `eu_sfdr` | `EU_GBS` | EU countries only |
| `eu_taxonomy` | `EU_GBS` | EU countries only |
| `sebi_brsr` | `SEBI` | India only |
| `rbi_climate` | `SEBI` | India only |
| `sec_climate` | `OTHER` | US bonds |

**Code**:

```python
def _find_affected_bonds(regulation):
    """Find bonds affected by a regulatory update."""
    
    # Map regulation types to regulatory frameworks
    regulation_mapping = {
        "eu_sfdr": "EU_GBS",
        "eu_taxonomy": "EU_GBS",
        "sebi_brsr": "SEBI",
        "rbi_climate": "SEBI",
        "sec_climate": "OTHER",
    }
    
    framework = regulation_mapping.get(regulation.regulation_type)
    
    # Find bonds with matching regulatory framework
    affected_bonds = GreenBond.objects.filter(regulatory_framework=framework)
    
    # Additional filtering for specific regulation types
    if regulation.regulation_type in ["sebi_brsr", "rbi_climate"]:
        # Filter by India
        affected_bonds = affected_bonds.filter(country="India")
    elif regulation.regulation_type in ["eu_sfdr", "eu_taxonomy"]:
        # Filter by EU countries
        eu_countries = ["Austria", "Belgium", "Bulgaria", ...]
        affected_bonds = affected_bonds.filter(country__in=eu_countries)
    
    return affected_bonds
```

---

### 3. Helper Function: `_create_regulatory_alert()`

**Purpose**: Create an AutomatedAlert for a regulatory update

**Alert Structure**:

```python
alert = AutomatedAlert.objects.create(
    alert_type="regulatory",
    title=f"{urgency}: {regulation.title}",
    description=(
        f"{regulation.get_regulation_type_display()} update: {regulation.description}\n\n"
        f"Effective Date: {regulation.effective_date.strftime('%B %d, %Y')} "
        f"({days_until_effective} days from now)\n\n"
        f"⚠️ Compliance Required: {regulation.action_required}\n\n"
        f"Impact: {regulation.impact_description}\n\n"
        f"Affected Bonds: {affected_bonds.count()} bonds in your portfolio"
    ),
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
```

**Urgency Calculation**:

| Days Until Effective | Urgency |
|---------------------|---------|
| < 0 (overdue) | OVERDUE |
| < 30 days | URGENT |
| < 90 days | HIGH |
| ≥ 90 days | MEDIUM |

---

### 4. Updated View: `alerts_feed()`

**File**: `ai_features/views.py`

**Changes**:

1. **Enriched alert data** with compliance deadline and urgency
2. **Shows affected bonds count** from ManyToMany relation
3. **Calculates days until deadline** for regulatory alerts

**Code**:

```python
def alerts_feed(request):
    """Automated alerts feed - Shows REAL alerts from database."""
    
    alerts_qs = AutomatedAlert.objects.prefetch_related("affected_bonds").all()
    
    # Enrich alerts with additional data
    alerts_list = []
    for alert in alerts_qs[:50]:
        alert_dict = {
            "alert": alert,
            "affected_bonds_count": alert.affected_bonds.count(),
            "compliance_deadline": None,
            "days_until_deadline": None,
            "urgency": None,
        }
        
        # For regulatory alerts, extract compliance deadline
        if alert.alert_type == "regulatory" and alert.alert_data:
            effective_date_str = alert.alert_data.get("effective_date")
            if effective_date_str:
                effective_date = datetime.fromisoformat(effective_date_str).date()
                alert_dict["compliance_deadline"] = effective_date
                
                # Calculate days until deadline
                days_until = (effective_date - timezone.now().date()).days
                alert_dict["days_until_deadline"] = days_until
                
                # Determine urgency
                if days_until < 0:
                    alert_dict["urgency"] = "OVERDUE"
                elif days_until < 30:
                    alert_dict["urgency"] = "URGENT"
                elif days_until < 90:
                    alert_dict["urgency"] = "HIGH"
                else:
                    alert_dict["urgency"] = "MEDIUM"
        
        alerts_list.append(alert_dict)
    
    return render(request, "ai_features/alerts_feed.html", {
        "alerts_list": alerts_list,
        "stats": stats,
    })
```

---

### 5. Updated Template: `alerts_feed.html`

**File**: `ai_features/templates/ai_features/alerts_feed.html`

**Changes**:

1. **Shows compliance deadline** for regulatory alerts
2. **Shows urgency badge** (OVERDUE, URGENT, HIGH, MEDIUM)
3. **Shows affected bonds count** with badge
4. **Shows first 5 affected bonds** with links

**Template Code**:

```django
{% for item in alerts_list %}
{% with alert=item.alert %}
<div class="alert-card alert-{{ alert.alert_type }}">
    <!-- Alert content -->
    
    <!-- Regulatory Alert: Show Compliance Deadline -->
    {% if alert.alert_type == 'regulatory' and item.compliance_deadline %}
    <div class="mb-2">
        <span class="badge {% if item.urgency == 'OVERDUE' %}bg-danger{% elif item.urgency == 'URGENT' %}bg-warning{% elif item.urgency == 'HIGH' %}bg-info{% else %}bg-secondary{% endif %}">
            {% if item.urgency == 'OVERDUE' %}
                ⚠️ OVERDUE
            {% elif item.urgency == 'URGENT' %}
                🔥 URGENT - {{ item.days_until_deadline }} days left
            {% elif item.urgency == 'HIGH' %}
                ⏰ HIGH - {{ item.days_until_deadline }} days left
            {% else %}
                📅 {{ item.days_until_deadline }} days until effective
            {% endif %}
        </span>
        <small class="text-muted ms-2">Compliance deadline: {{ item.compliance_deadline|date:"M d, Y" }}</small>
    </div>
    {% endif %}
    
    <!-- Show affected bonds count -->
    {% if item.affected_bonds_count > 0 %}
    <span class="badge bg-primary">{{ item.affected_bonds_count }} bond{{ item.affected_bonds_count|pluralize }} affected</span>
    {% endif %}
    
    <!-- Show affected bonds -->
    {% if alert.affected_bonds.exists %}
    <div class="mt-2">
        <small class="text-muted">Affected bonds:</small>
        {% for b in alert.affected_bonds.all|slice:":5" %}
        <a href="{% url 'dashboard:bond_detail' b.bond_id %}" class="badge bg-secondary text-decoration-none">{{ b.bond_id }}</a>
        {% endfor %}
        {% if item.affected_bonds_count > 5 %}
        <span class="badge bg-light text-dark">+{{ item.affected_bonds_count|add:"-5" }} more</span>
        {% endif %}
    </div>
    {% endif %}
</div>
{% endwith %}
{% endfor %}
```

---

## Data Flow

### Complete Flow from Scraping to Alert Display

```
1. Celery Beat triggers refresh_regulatory_updates() at 06:00 UTC
   ↓
2. Scraper fetches EU SFDR and SEBI updates
   ↓
3. New RegulatoryMonitor records created in database
   ↓
4. refresh_regulatory_updates() triggers generate_regulatory_alerts()
   ↓
5. generate_regulatory_alerts() processes new regulations:
   - Gets regulations created in last 24 hours
   - For each regulation:
     * Finds affected bonds by regulatory framework
     * Creates AutomatedAlert with alert_type='regulatory'
     * Sets affected_bonds ManyToMany relation
   ↓
6. alerts_feed() view enriches alerts with:
   - Compliance deadline
   - Days until deadline
   - Urgency level
   - Affected bonds count
   ↓
7. Template displays:
   - Alert title with urgency prefix
   - Compliance deadline badge
   - Affected bonds count
   - First 5 affected bonds with links
```

---

## Example Alert

### Input: New EU SFDR Regulation

```python
RegulatoryMonitor.objects.create(
    regulation_type="eu_sfdr",
    title="SFDR Level 2 Disclosure Requirements",
    description="New disclosure requirements for Article 8 and 9 funds",
    announcement_date=date(2024, 1, 15),
    effective_date=date(2024, 6, 30),
    impact_description="All EU Green Bond Standard bonds must provide enhanced climate impact metrics",
    compliance_required=True,
    action_required="Update bond documentation with new climate metrics",
    source_url="https://www.esma.europa.eu/press-news/esma-news/...",
)
```

### Output: Generated Alert

```python
AutomatedAlert.objects.create(
    alert_type="regulatory",
    title="HIGH: SFDR Level 2 Disclosure Requirements",
    description="""
EU SFDR update: New disclosure requirements for Article 8 and 9 funds

Effective Date: June 30, 2024 (165 days from now)

⚠️ Compliance Required: Update bond documentation with new climate metrics

Impact: All EU Green Bond Standard bonds must provide enhanced climate impact metrics

Affected Bonds: 45 bonds in your portfolio
    """,
    alert_data={
        "regulation_id": 123,
        "regulation_type": "eu_sfdr",
        "announcement_date": "2024-01-15",
        "effective_date": "2024-06-30",
        "days_until_effective": 165,
        "compliance_required": True,
        "action_required": "Update bond documentation with new climate metrics",
        "affected_bonds_count": 45,
        "source_url": "https://www.esma.europa.eu/...",
        "urgency": "HIGH",
    },
    status="pending",
    delivery_method="dashboard",
)

# Affected bonds: All bonds with regulatory_framework='EU_GBS' in EU countries
alert.affected_bonds.set(
    GreenBond.objects.filter(
        regulatory_framework="EU_GBS",
        country__in=["France", "Germany", "Netherlands", ...]
    )
)
```

### Display in Alerts Feed

```
┌─────────────────────────────────────────────────────────────┐
│ 📋 HIGH: SFDR Level 2 Disclosure Requirements    [Pending]  │
│                                                               │
│ EU SFDR update: New disclosure requirements for Article 8    │
│ and 9 funds                                                   │
│                                                               │
│ [⏰ HIGH - 165 days left]                                    │
│ Compliance deadline: Jun 30, 2024                            │
│                                                               │
│ [Regulatory Change] [dashboard] [45 bonds affected]          │
│                                                               │
│ Affected bonds: [BOND_001] [BOND_002] [BOND_003] [BOND_004] │
│                 [BOND_005] [+40 more]                        │
│                                                               │
│ Jan 15, 2024 06:30                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Testing

### Manual Testing

```bash
python manage.py shell
```

```python
from ai_features.tasks import generate_regulatory_alerts
from ai_features.models import RegulatoryMonitor, AutomatedAlert
from data_ingestion.models import GreenBond
from datetime import date, timedelta

# Create test regulation
regulation = RegulatoryMonitor.objects.create(
    regulation_type="eu_sfdr",
    title="Test SFDR Regulation",
    description="Test description",
    announcement_date=date.today(),
    effective_date=date.today() + timedelta(days=60),
    impact_description="Test impact",
    compliance_required=True,
    action_required="Test action",
)

# Generate alerts
result = generate_regulatory_alerts()
print(result)
# {'success': True, 'regulations_processed': 1, 'alerts_created': 1, 'alerts_skipped': 0}

# Check created alert
alert = AutomatedAlert.objects.filter(alert_type="regulatory").last()
print(f"Alert: {alert.title}")
print(f"Affected bonds: {alert.affected_bonds.count()}")
print(f"Urgency: {alert.alert_data['urgency']}")
```

### Celery Task Testing

```bash
# Test alert generation task
celery -A greenlens call ai_features.generate_regulatory_alerts

# Test full flow (scraping + alert generation)
celery -A greenlens call ai_features.refresh_regulatory_updates
```

---

## Requirements Met

### Requirement 1: Update AutomatedAlert Creation ✅

- ✅ When RegulatoryMonitor gets a new entry (from scraper)
- ✅ Automatically create AutomatedAlert with alert_type='regulatory'
- ✅ Find affected bonds:
  - EU regulation → bonds with regulatory_framework='EU_GBS'
  - SEBI regulation → bonds with regulatory_framework='SEBI'
- ✅ Set affected_bonds ManyToMany relation
- ✅ Set status='pending'

### Requirement 2: Add Celery Task ✅

- ✅ `generate_regulatory_alerts()` task created
- ✅ Runs after `refresh_regulatory_updates()` completes
- ✅ Creates alerts for new regulations only (last 24 hours)
- ✅ Avoids duplicate alerts (checks existing alerts)

### Requirement 3: Update Alerts Feed View ✅

- ✅ Show regulatory alerts from real AutomatedAlert records
- ✅ Show affected bond count
- ✅ Show compliance deadline if available
- ✅ Show urgency level (OVERDUE, URGENT, HIGH, MEDIUM)
- ✅ Show first 5 affected bonds with links

---

## Files Modified

1. **`ai_features/tasks.py`** - Added `generate_regulatory_alerts()` task
2. **`ai_features/views.py`** - Updated `alerts_feed()` to enrich regulatory alerts
3. **`ai_features/templates/ai_features/alerts_feed.html`** - Updated template to show compliance deadline and affected bonds

---

## Data Sources

All regulatory alerts use **REAL data**:

| Data Source | Origin |
|------------|--------|
| Regulations | Scraped from EU ESMA and SEBI websites |
| Affected Bonds | Queried from GreenBond model by regulatory_framework |
| Compliance Deadlines | From RegulatoryMonitor.effective_date |
| Urgency Levels | Calculated from days until effective date |

**No placeholders, no hardcoded data, no demo data.**

---

## Summary

**STATUS**: ✅ COMPLETE

Regulatory alerts are now fully connected to REAL data:

1. ✅ Automatic alert generation from scraped regulations
2. ✅ Finds affected bonds by regulatory framework
3. ✅ Sets ManyToMany relation to affected bonds
4. ✅ Shows compliance deadline and urgency
5. ✅ Shows affected bonds count and links
6. ✅ Avoids duplicate alerts
7. ✅ Runs automatically via Celery Beat

**The alerts feed now shows REAL regulatory alerts with REAL affected bonds and REAL compliance deadlines.**
