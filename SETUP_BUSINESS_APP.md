# GreenLens Business App Setup Guide

**Complete step-by-step guide to set up the business & monetization module**

---

## ✅ Step 1: Verify App Configuration

### Check `greenlens/settings.py`

```python
INSTALLED_APPS = [
    ...
    "business.apps.BusinessConfig",  # ✓ Should be present
]

MIDDLEWARE = [
    ...
    # Business middleware (rate limiting, usage tracking)
    "business.middleware.RateLimitMiddleware",
    "business.middleware.UsageTrackingMiddleware",
    "business.middleware.FeatureAccessMiddleware",
]
```

**Why `BusinessConfig` instead of just `business`?**
- ✅ Better practice — explicit app configuration
- ✅ Allows custom app settings in `apps.py`
- ✅ Django recommendation for modern projects

---

## ✅ Step 2: Create Migrations

```bash
# Create migrations for business app
python manage.py makemigrations business
```

**Expected Output:**
```
Migrations for 'business':
  business/migrations/0001_initial.py
    - Create model Organization
    - Create model UserProfile
    - Create model UsageLog
    - Create model Invoice
    - Create model Feature
```

**Common Mistakes to Avoid:**
- ❌ `python manage.py makemigrations` (without app name) — creates migrations for ALL apps
- ❌ Not saving `models.py` before running command
- ❌ Typo in app name (`bussiness` instead of `business`)

---

## ✅ Step 3: Apply Migrations

```bash
# Apply ALL pending migrations (recommended)
python manage.py migrate
```

**Expected Output:**
```
Running migrations:
  Applying business.0001_initial... OK
```

**Why NOT `migrate business`?**
- ✅ `migrate` (no app name) — applies ALL pending migrations (best practice)
- ⚠️ `migrate business` — only applies business migrations (can cause dependency issues)

**When to use `migrate business`:**
- Only when debugging specific app migrations
- When you want to rollback specific app only

---

## ✅ Step 4: Create Superuser

```bash
python manage.py createsuperuser
```

**Prompts:**
```
Username: admin
Email address: admin@greenlens.io
Password: ********
Password (again): ********
Superuser created successfully.
```

**Tips:**
- Use strong password for production
- Remember credentials — no password recovery in dev!

---

## ✅ Step 5: Start Development Server

```bash
python manage.py runserver
```

**Expected Output:**
```
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

---

## ✅ Step 6: Access Admin Panel

### Open Browser:
```
http://127.0.0.1:8000/admin/
```

### Login with superuser credentials

### Verify Business Models:

You should see:
- ✅ **Organizations** — Company/org management
- ✅ **User Profiles** — User-organization linking
- ✅ **Usage Logs** — API calls, bond views tracking
- ✅ **Invoices** — Billing management
- ✅ **Features** — Feature flags

---

## ✅ Step 7: Create Test Organization

### In Admin Panel:

1. Click **Organizations** → **Add Organization**

2. Fill in details:
   ```
   Name: Test Company
   Slug: test-company
   Tier: Professional
   Is active: ✓
   Billing email: test@example.com
   Contact name: Test User
   Subscription start date: 2026-01-01
   Subscription end date: 2026-12-31
   ```

3. Click **Save**

### Verify:
- ✅ Organization appears in list
- ✅ Tier badge shows "Professional" in green
- ✅ Status shows "✓ Active"
- ✅ Monthly price shows "€299"

---

## ✅ Step 8: Create Test User Profile

### In Admin Panel:

1. Click **User Profiles** → **Add User Profile**

2. Fill in details:
   ```
   User: admin (select from dropdown)
   Organization: Test Company
   Role: Administrator
   ```

3. Click **Save**

### Verify:
- ✅ User profile created
- ✅ Linked to organization
- ✅ Role badge shows "Administrator" in red

---

## ✅ Step 9: Test Rate Limiting

### Make API Request:

```bash
# Test API endpoint (should work)
curl http://127.0.0.1:8000/api/bonds/

# Check rate limit headers in response
```

**Expected Headers:**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 2026-04-27 00:00 UTC
```

---

## ✅ Step 10: Test Usage Tracking

### View Bond Detail:

1. Open: `http://127.0.0.1:8000/bond/GB001/`
2. Go to Admin → **Usage Logs**
3. Verify new log entry:
   ```
   Organization: Test Company
   User: admin
   Action type: Bond View
   Bond ID: GB001
   ```

---

## 🎯 Advanced Configuration

### 1. Customize Admin Site

Edit `business/admin.py`:

```python
# Already implemented with:
- Color-coded badges
- Search functionality
- Filters
- Collapsible sections
- Readonly fields
```

### 2. Add Custom Admin Actions

```python
@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    actions = ['renew_subscription']
    
    def renew_subscription(self, request, queryset):
        from datetime import timedelta
        for org in queryset:
            org.subscription_end_date += timedelta(days=30)
            org.save()
        self.message_user(request, f"{queryset.count()} subscriptions renewed")
    renew_subscription.short_description = "Renew subscription for 30 days"
```

### 3. Add Inline Editing

```python
class UserProfileInline(admin.TabularInline):
    model = UserProfile
    extra = 1

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    inlines = [UserProfileInline]
```

---

## 🔍 Troubleshooting

### Problem 1: Models not showing in admin

**Cause:** Models not registered in `admin.py`

**Solution:**
```python
# business/admin.py
from django.contrib import admin
from .models import Organization

admin.site.register(Organization)
```

---

### Problem 2: Migration errors

**Error:** `No changes detected`

**Solution:**
```bash
# Ensure models.py is saved
# Check INSTALLED_APPS includes 'business.apps.BusinessConfig'
python manage.py makemigrations business --dry-run  # Preview changes
python manage.py makemigrations business
```

---

### Problem 3: Rate limiting not working

**Cause:** Middleware not added to settings

**Solution:**
```python
# greenlens/settings.py
MIDDLEWARE = [
    ...
    "business.middleware.RateLimitMiddleware",
]
```

---

### Problem 4: Redis connection error

**Error:** `ConnectionError: Error connecting to Redis`

**Solution:**
```bash
# Start Redis server
docker run -p 6379:6379 redis:7-alpine

# Or install Redis locally
# Windows: https://github.com/microsoftarchive/redis/releases
# Mac: brew install redis
# Linux: sudo apt-get install redis-server
```

---

## 📊 Verify Installation

### Run this checklist:

```bash
# 1. Check migrations
python manage.py showmigrations business

# Expected output:
# business
#  [X] 0001_initial

# 2. Check models
python manage.py shell
>>> from business.models import Organization
>>> Organization.objects.count()
1  # Should show your test organization

# 3. Check admin
# Open http://127.0.0.1:8000/admin/
# Verify all 5 models visible

# 4. Check middleware
# Make API request and check headers
curl -I http://127.0.0.1:8000/api/bonds/
# Should see X-RateLimit-* headers
```

---

## ✅ Success Criteria

Your business app is correctly set up if:

1. ✅ All 5 models visible in admin panel
2. ✅ Can create organizations with different tiers
3. ✅ Can create user profiles linked to organizations
4. ✅ Rate limiting headers appear in API responses
5. ✅ Usage logs are created when viewing bonds
6. ✅ Admin panel shows color-coded badges
7. ✅ Search and filters work in admin

---

## 🚀 Next Steps

### 1. Add Pricing Page Route

```python
# dashboard/urls.py
urlpatterns = [
    ...
    path("pricing/", views.pricing, name="pricing"),
]

# dashboard/views.py
def pricing(request):
    return render(request, "dashboard/pricing.html")
```

### 2. Test Pricing Page

```
http://127.0.0.1:8000/pricing/
```

### 3. Integrate Stripe (Optional)

```bash
pip install stripe
```

```python
# business/views.py
import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
```

---

## 📚 Additional Resources

- Django Admin Customization: https://docs.djangoproject.com/en/5.0/ref/contrib/admin/
- Middleware: https://docs.djangoproject.com/en/5.0/topics/http/middleware/
- Rate Limiting: https://django-ratelimit.readthedocs.io/

---

**Setup Complete! 🎉**

Your GreenLens business & monetization module is now ready for production.
