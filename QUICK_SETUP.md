# GreenLens Business App — Quick Setup (5 Minutes)

## 🚀 Fast Track Setup

```bash
# 1. Create migrations
python manage.py makemigrations business

# 2. Apply migrations
python manage.py migrate

# 3. Create superuser (if not exists)
python manage.py createsuperuser

# 4. Start server
python manage.py runserver

# 5. Open admin
# http://127.0.0.1:8000/admin/
```

---

## ✅ Verification Checklist

```bash
# Check migrations applied
python manage.py showmigrations business
# Should show: [X] 0001_initial

# Check models accessible
python manage.py shell
>>> from business.models import Organization
>>> Organization.objects.count()
# Should work without errors

# Check admin
# Open http://127.0.0.1:8000/admin/
# Should see: Organizations, User Profiles, Usage Logs, Invoices, Features
```

---

## 🎯 Create Test Data (Optional)

```python
# In Django shell: python manage.py shell

from business.models import Organization
from django.contrib.auth.models import User

# Create test organization
org = Organization.objects.create(
    name="Test Company",
    slug="test-company",
    tier="professional",
    billing_email="test@example.com",
    contact_name="Test User",
    is_active=True
)

# Create user profile
from business.models import UserProfile
user = User.objects.first()  # Get admin user
profile = UserProfile.objects.create(
    user=user,
    organization=org,
    role="admin"
)

print(f"✓ Created {org.name} with {org.get_tier_display()} tier")
print(f"✓ Monthly price: €{org.monthly_price_eur}")
print(f"✓ API calls/day: {org.api_calls_per_day}")
```

---

## 🔧 Common Issues & Fixes

### Issue: "No module named 'business'"
**Fix:** Add to `INSTALLED_APPS` in `settings.py`:
```python
INSTALLED_APPS = [
    ...
    'business.apps.BusinessConfig',
]
```

### Issue: "No changes detected"
**Fix:** Ensure `models.py` is saved, then:
```bash
python manage.py makemigrations business --dry-run  # Preview
python manage.py makemigrations business
```

### Issue: Models not in admin
**Fix:** Already registered in `business/admin.py` ✓

### Issue: Rate limiting not working
**Fix:** Add middleware to `settings.py`:
```python
MIDDLEWARE = [
    ...
    'business.middleware.RateLimitMiddleware',
]
```

---

## 📊 Test Rate Limiting

```bash
# Make API request
curl -I http://127.0.0.1:8000/api/bonds/

# Check headers:
# X-RateLimit-Limit: 1000
# X-RateLimit-Remaining: 999
```

---

## ✅ Done!

Your business app is ready. See `SETUP_BUSINESS_APP.md` for detailed guide.
