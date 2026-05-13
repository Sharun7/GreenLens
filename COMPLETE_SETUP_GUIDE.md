# GreenLens — Complete Setup Guide

## Overview

GreenLens is a satellite-verified climate risk scoring system for green bonds. This guide covers the complete setup from scratch.

**Current Status:** ✅ All 4 categories implemented
- Category 11: Model Depth Questions (Explainability & Bias Detection) ✅
- Category 12: Technical Architecture & Scaling ✅
- Category 13: Business & Monetization ✅
- Category 14: Risk & Failure Management ✅

---

## Prerequisites

### System Requirements
- Python 3.11+
- PostgreSQL 13+
- Redis 6+
- Node.js 18+ (for frontend assets)

### Python Packages
```bash
pip install -r requirements.txt
```

Key packages:
- Django 5.0
- Django REST Framework
- Celery + Redis
- SHAP (explainability)
- Scikit-learn (ML models)
- Pandas + NumPy (data processing)
- Pillow (image processing)

---

## Step 1: Environment Setup

### 1.1 Create .env file
```bash
cp .env.example .env
```

### 1.2 Configure .env
```env
# Django
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/greenlens_db
# OR individual settings:
DB_NAME=greenlens_db
DB_USER=greenlens_user
DB_PASSWORD=greenlens_pass
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Google Earth Engine
EE_SERVICE_ACCOUNT=your-gee-service-account
EE_PRIVATE_KEY_FILE=path/to/private-key.json
EE_PROJECT_ID=your-gee-project-id

# NASA Earthdata
EARTHDATA_USERNAME=your-earthdata-username
EARTHDATA_PASSWORD=your-earthdata-password

# Render (if deploying)
RENDER_EXTERNAL_HOSTNAME=your-app.onrender.com
```

---

## Step 2: Database Setup

### 2.1 Create PostgreSQL Database
```bash
# On Windows (using psql)
psql -U postgres
CREATE DATABASE greenlens_db;
CREATE USER greenlens_user WITH PASSWORD 'greenlens_pass';
ALTER ROLE greenlens_user SET client_encoding TO 'utf8';
ALTER ROLE greenlens_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE greenlens_user SET default_transaction_deferrable TO on;
ALTER ROLE greenlens_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE greenlens_db TO greenlens_user;
\q
```

### 2.2 Run Migrations
```bash
python manage.py migrate
```

This will create all tables for:
- Django core (auth, sessions, etc.)
- data_ingestion (bonds, climate hazards)
- risk_scoring (PCRS scores, SHAP values)
- pricing_analysis (yield spreads, pricing gaps)
- greenwash_detector (greenwash flags)
- dashboard (UI data)
- business (subscriptions, usage tracking)
- risk_management (risk logs, incidents)

---

## Step 3: Create Superuser

```bash
python manage.py createsuperuser
```

Enter:
- Username: admin
- Email: admin@greenlens.local
- Password: (choose a strong password)

---

## Step 4: Load Initial Data (Optional)

### 4.1 Create Sample Organizations
```bash
python manage.py shell
```

```python
from business.models import Organization, SubscriptionTier

# Create Academic organization
org_academic = Organization.objects.create(
    name="Academic Research Lab",
    slug="academic-lab",
    tier=SubscriptionTier.ACADEMIC,
    billing_email="research@lab.edu",
    contact_name="Dr. Jane Smith",
    country="United States"
)

# Create Professional organization
org_pro = Organization.objects.create(
    name="Green Finance Corp",
    slug="green-finance",
    tier=SubscriptionTier.PROFESSIONAL,
    billing_email="billing@greenfinance.com",
    contact_name="John Doe",
    country="United Kingdom",
    subscription_start_date="2026-01-01",
    subscription_end_date="2026-12-31"
)

# Create Business organization
org_business = Organization.objects.create(
    name="ESG Investment Fund",
    slug="esg-fund",
    tier=SubscriptionTier.BUSINESS,
    billing_email="billing@esgfund.com",
    contact_name="Alice Johnson",
    country="Germany",
    subscription_start_date="2026-01-01",
    subscription_end_date="2026-12-31"
)

print("Organizations created successfully!")
exit()
```

### 4.2 Create Sample Risk Scenarios
```bash
python manage.py shell
```

```python
from risk_management.models import SystemFailureScenario

# Create GEE API failure scenario
scenario = SystemFailureScenario.objects.create(
    name="Google Earth Engine API Down",
    description="GEE API is temporarily unavailable for satellite data retrieval",
    scenario_type="api_failure",
    probability="medium",
    severity="high",
    impact_description="Greenwash detection stops, new bonds cannot be verified",
    affected_modules=["greenwash_detector", "risk_scoring"],
    mitigation_strategy="Use Copernicus API as fallback, then cached NDVI values",
    mitigation_status="monitoring",
    has_fallback=True,
    fallback_description="Copernicus API → Cached NDVI → Unverifiable flag",
    recovery_time_minutes=30
)

print(f"Scenario created: {scenario.name} (Risk Score: {scenario.risk_score})")
exit()
```

---

## Step 5: Start Development Server

### 5.1 Start Django Development Server
```bash
python manage.py runserver
```

Server will be available at: http://127.0.0.1:8000/

### 5.2 Start Celery Worker (in separate terminal)
```bash
celery -A greenlens worker -l info
```

### 5.3 Start Celery Beat (in separate terminal)
```bash
celery -A greenlens beat -l info
```

---

## Step 6: Access Admin Panel

1. Open browser: http://127.0.0.1:8000/admin/
2. Login with superuser credentials
3. Verify all apps are visible:
   - **Authentication and Authorization**: Users, Groups
   - **Data Ingestion**: Green Bonds, Climate Hazard Data
   - **Risk Scoring**: PCRS Scores, Model Feedback
   - **Pricing Analysis**: Yield Spreads, Pricing Gaps
   - **Greenwash Detector**: Greenwash Flags
   - **Dashboard**: (UI data)
   - **Business**: Organizations, User Profiles, Usage Logs, Invoices, Features
   - **Risk Management**: System Failure Scenarios, Model Drift Alerts, Classification Errors, Data Quality Metrics, Legal Risk Logs, Incident Logs

---

## Step 7: Access Dashboard

1. Open browser: http://127.0.0.1:8000/
2. Explore pages:
   - `/` — Home page
   - `/portfolio/` — Bond portfolio analysis
   - `/greenlens-map/` — Interactive map
   - `/pricing/` — Pricing page
   - `/pricing-analysis/` — Pricing gap analysis
   - `/model-bias/` — Model bias detection
   - `/about/` — About page
   - `/terms/` — Terms of service

---

## Step 8: API Testing

### 8.1 List All Bonds
```bash
curl http://127.0.0.1:8000/api/bonds/
```

### 8.2 Get Bond Details
```bash
curl http://127.0.0.1:8000/api/bonds/{id}/
```

### 8.3 Get Bonds in Viewport (for scaling)
```bash
curl "http://127.0.0.1:8000/api/bonds/viewport/?min_lat=40&max_lat=50&min_lon=-10&max_lon=10&zoom=5"
```

### 8.4 Get Bias Detection Summary
```bash
curl http://127.0.0.1:8000/api/risk/bias-summary/
```

### 8.5 Get Bias Detection Details
```bash
curl http://127.0.0.1:8000/api/risk/bias-detection/
```

---

## Step 9: Run Tests

### 9.1 Run All Tests
```bash
python manage.py test
```

### 9.2 Run Specific App Tests
```bash
python manage.py test risk_scoring
python manage.py test business
python manage.py test risk_management
```

### 9.3 Run with Coverage
```bash
coverage run --source='.' manage.py test
coverage report
coverage html
```

---

## Step 10: Deployment (Render.com)

### 10.1 Create Render Account
- Go to https://render.com
- Sign up with GitHub account

### 10.2 Create PostgreSQL Database
- New → PostgreSQL
- Name: greenlens-db
- Region: Frankfurt (EU)
- Copy DATABASE_URL

### 10.3 Create Redis Cache
- New → Redis
- Name: greenlens-redis
- Region: Frankfurt (EU)
- Copy REDIS_URL

### 10.4 Create Web Service
- New → Web Service
- Connect GitHub repository
- Build command: `pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput`
- Start command: `gunicorn greenlens.wsgi:application --bind 0.0.0.0:$PORT`
- Environment variables:
  - DATABASE_URL (from PostgreSQL)
  - REDIS_URL (from Redis)
  - SECRET_KEY (generate new)
  - DEBUG=False
  - ALLOWED_HOSTS=your-app.onrender.com

### 10.5 Create Background Worker
- New → Background Worker
- Same repository
- Build command: `pip install -r requirements.txt`
- Start command: `celery -A greenlens worker -l info`
- Environment variables: (same as web service)

### 10.6 Create Celery Beat Scheduler
- New → Background Worker
- Same repository
- Build command: `pip install -r requirements.txt`
- Start command: `celery -A greenlens beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler`
- Environment variables: (same as web service)

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'django'"
**Solution:** Install requirements
```bash
pip install -r requirements.txt
```

### Issue: "psycopg2 error: could not connect to server"
**Solution:** Check PostgreSQL is running and DATABASE_URL is correct
```bash
# Windows: Start PostgreSQL service
net start postgresql-x64-13

# Check connection
psql -U greenlens_user -d greenlens_db -h localhost
```

### Issue: "Redis connection refused"
**Solution:** Check Redis is running
```bash
# Windows: Start Redis
redis-server

# Or use WSL
wsl redis-server
```

### Issue: "No such table: auth_user"
**Solution:** Run migrations
```bash
python manage.py migrate
```

### Issue: "GDAL/GEOS not found"
**Solution:** GeoDjango is disabled by default. If you need spatial queries:
```bash
# Install GDAL (Windows)
pip install gdal

# Or use conda
conda install gdal
```

---

## Project Structure

```
greenlens/
├── greenlens/              # Project settings
│   ├── settings.py         # Django settings
│   ├── urls.py             # URL routing
│   ├── wsgi.py             # WSGI application
│   └── asgi.py             # ASGI application
├── data_ingestion/         # Bond data ingestion
│   ├── models.py           # GreenBond, ClimateHazardData
│   ├── views.py            # REST API views
│   ├── serializers.py      # DRF serializers
│   └── urls.py             # API routes
├── risk_scoring/           # PCRS scoring & SHAP
│   ├── models.py           # PCRSScore, SHAPValue
│   ├── views.py            # Scoring API
│   └── bias_detection.py   # Bias detection
├── pricing_analysis/       # Yield spread analysis
│   ├── models.py           # YieldSpread, PricingGap
│   └── views.py            # Pricing API
├── greenwash_detector/     # Greenwash detection
│   ├── models.py           # GreenwashFlag
│   └── detector.py         # Detection logic
├── dashboard/              # Web UI
│   ├── views.py            # Page views
│   ├── urls.py             # Page routes
│   └── templates/          # HTML templates
├── business/               # Subscriptions & billing
│   ├── models.py           # Organization, Invoice, etc.
│   ├── middleware.py       # Rate limiting
│   └── admin.py            # Admin interface
├── risk_management/        # Risk tracking
│   ├── models.py           # Risk models
│   ├── monitoring.py       # Monitoring utilities
│   └── admin.py            # Admin interface
├── static/                 # CSS, JS, images
├── templates/              # Base templates
├── manage.py               # Django CLI
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
└── README.md               # Project README
```

---

## Key Features

### Category 11: Model Depth Questions
- ✅ SHAP explainability (waterfall charts)
- ✅ 3-level risk explanations
- ✅ Comprehensive bias detection (4 types)
- ✅ Bias detection API & dashboard

### Category 12: Technical Architecture & Scaling
- ✅ Database indexes for 1 lakh bonds
- ✅ Viewport-based loading API
- ✅ Distributed Celery workers
- ✅ Nginx load balancer configuration
- ✅ 3-phase scaling roadmap

### Category 13: Business & Monetization
- ✅ 4-tier pricing model (€0-€4,999/month)
- ✅ Subscription management
- ✅ Usage tracking & rate limiting
- ✅ Pricing page
- ✅ Revenue projections (€82K → €2.6M)

### Category 14: Risk & Failure Management
- ✅ 5 system failure scenarios
- ✅ 3 classification error types
- ✅ 3 legal risk types
- ✅ Model drift detection
- ✅ Data quality monitoring
- ✅ Incident logging

---

## Next Steps

1. **Load Sample Data**
   - Import green bonds from CBI registry
   - Load climate hazard data from NASA
   - Generate PCRS scores

2. **Configure External APIs**
   - Google Earth Engine authentication
   - NASA Earthdata credentials
   - Yahoo Finance API key

3. **Customize Branding**
   - Update logo in `static/images/`
   - Customize colors in `static/css/`
   - Update company name in templates

4. **Set Up Monitoring**
   - Configure Sentry for error tracking
   - Set up DataDog for performance monitoring
   - Configure email alerts

5. **Go Live**
   - Deploy to Render.com
   - Set up custom domain
   - Configure SSL certificate
   - Monitor performance

---

## Support

For questions or issues:
1. Check the documentation files:
   - `CATEGORY_11_IMPLEMENTATION.md` — Bias detection
   - `CATEGORY_12_IMPLEMENTATION.md` — Scaling
   - `CATEGORY_13_IMPLEMENTATION.md` — Business model
   - `CATEGORY_14_IMPLEMENTATION.md` — Risk management

2. Review the admin panel for existing data

3. Check logs:
   ```bash
   tail -f batch_score.log
   ```

4. Run Django shell for debugging:
   ```bash
   python manage.py shell
   ```

---

**Last Updated:** April 27, 2026
**Status:** ✅ Complete — Ready for production deployment
