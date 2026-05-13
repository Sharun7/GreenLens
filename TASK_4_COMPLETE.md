# Task 4: Connect Regulatory Alerts to Real Data - COMPLETE ✅

## User Request

> In ai_features/, regulatory alerts are hardcoded. Connect them to real data:
> 
> 1. Update AutomatedAlert creation for regulatory alerts
> 2. Add Celery task: generate_regulatory_alerts()
> 3. Update alerts feed view to show real data

## Implementation Summary

### ✅ All Requirements Met

| Requirement | Status | Implementation |
|------------|--------|----------------|
| Auto-create alerts from regulations | ✅ COMPLETE | `generate_regulatory_alerts()` task |
| Find affected bonds by framework | ✅ COMPLETE | `_find_affected_bonds()` helper |
| Set ManyToMany relation | ✅ COMPLETE | `alert.affected_bonds.set()` |
| Avoid duplicate alerts | ✅ COMPLETE | Check existing alerts |
| Show compliance deadline | ✅ COMPLETE | Updated template |
| Show affected bonds count | ✅ COMPLETE | Updated view |

---

## Implementation Details

### 1. Celery Task: `generate_regulatory_alerts()` ✅

**File**: `ai_features/tasks.py`

**Purpose**: Automatically create alerts for new regulatory updates

**Trigger**: Called by `refresh_regulatory_updates()` when new regulations are saved

**Logic**:
- Gets new RegulatoryMonitor entries (created in last 24 hours)
- For each regulation:
  - Checks if alert already exists (avoids duplicates)
  - Finds affected bonds by regulatory framework
  - Creates AutomatedAlert with alert_type='regulatory'
  - Sets affected_bonds ManyToMany relation
  - Updates regulation.affected_bonds_count

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

### 2. Helper Function: `_find_affected_bonds()` ✅

**Purpose**: Find bonds affected by a regulatory update

**Mapping**:

| Regulation Type | Regulatory Framework | Additional Filter |
|----------------|---------------------|-------------------|
| `eu_sfdr` | `EU_GBS` | EU countries only |
| `eu_taxonomy` | `EU_GBS` | EU countries only |
| `sebi_brsr` | `SEBI` | India only |
| `rbi_climate` | `SEBI` | India only |

**Code**:
```python
def _find_affected_bonds(regulation):
    regulation_mapping = {
        "eu_sfdr": "EU_GBS",
        "eu_taxonomy": "EU_GBS",
        "sebi_brsr": "SEBI",
        "rbi_climate": "SEBI",
    }
    
    framework = regulation_mapping.get(regulation.regulation_type)
    affected_bonds = GreenBond.objects.filter(regulatory_framework=framework)
    
    # Additional filtering by country
    if regulation.regulation_type in ["sebi_brsr", "rbi_climate"]:
        affected_bonds = affected_bonds.filter(country="India")
    elif regulation.regulation_type in ["eu_sfdr", "eu_taxonomy"]:
        affected_bonds = affected_bonds.filter(country__in=eu_countries)
    
    return affected_bonds
```

---

### 3. Helper Function: `_create_regulatory_alert()` ✅

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
        "effective_date": regulation.effective_date.isoformat(),
        "days_until_effective": days_until_effective,
        "compliance_required": regulation.compliance_required,
        "action_required": regulation.action_required,
        "affected_bonds_count": affected_bonds.count(),
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

### 4. Updated View: `alerts_feed()` ✅

**File**: `ai_features/views.py`

**Changes**:
- Enriches alerts with compliance deadline and urgency
- Shows affected bonds count from ManyToMany relation
- Calculates days until deadline for regulatory alerts

**Code**:
```python
def alerts_feed(request):
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

### 5. Updated Template: `alerts_feed.html` ✅

**File**: `ai_features/templates/ai_features/alerts_feed.html`

**Changes**:
- Shows compliance deadline for regulatory alerts
- Shows urgency badge (OVERDUE, URGENT, HIGH, MEDIUM)
- Shows affected bonds count with badge
- Shows first 5 affected bonds with links

**Template Code**:
```django
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
{% for b in alert.affected_bonds.all|slice:":5" %}
<a href="{% url 'dashboard:bond_detail' b.bond_id %}" class="badge bg-secondary">{{ b.bond_id }}</a>
{% endfor %}
{% if item.affected_bonds_count > 5 %}
<span class="badge bg-light text-dark">+{{ item.affected_bonds_count|add:"-5" }} more</span>
{% endif %}
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

## Example Alert Display

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

## Files Modified

1. **`ai_features/tasks.py`** - Added `generate_regulatory_alerts()` task and helper functions
2. **`ai_features/views.py`** - Updated `alerts_feed()` to enrich regulatory alerts
3. **`ai_features/templates/ai_features/alerts_feed.html`** - Updated template to show compliance deadline and affected bonds

---

## Testing

### Manual Testing

```bash
python manage.py shell
```

```python
from ai_features.tasks import generate_regulatory_alerts
from ai_features.models import RegulatoryMonitor, AutomatedAlert
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

# Check created alert
alert = AutomatedAlert.objects.filter(alert_type="regulatory").last()
print(f"Alert: {alert.title}")
print(f"Affected bonds: {alert.affected_bonds.count()}")
```

### Celery Task Testing

```bash
# Test alert generation task
celery -A greenlens call ai_features.generate_regulatory_alerts

# Test full flow
celery -A greenlens call ai_features.refresh_regulatory_updates
```

---

## Requirements Verification

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

## Documentation

Created comprehensive documentation:
- **REGULATORY_ALERTS_IMPLEMENTATION.md** - Full technical documentation

---

## Status: ✅ COMPLETE

Regulatory alerts are now fully connected to REAL data:

1. ✅ Automatic alert generation from scraped regulations
2. ✅ Finds affected bonds by regulatory framework
3. ✅ Sets ManyToMany relation to affected bonds
4. ✅ Shows compliance deadline and urgency
5. ✅ Shows affected bonds count and links
6. ✅ Avoids duplicate alerts
7. ✅ Runs automatically via Celery Beat

**The alerts feed now shows REAL regulatory alerts with REAL affected bonds and REAL compliance deadlines.**
