# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
greenlens/settings.py — Production-ready Django 5 settings for GreenLens.
"""
import os
from pathlib import Path

import environ
import dj_database_url

# Force local memory cache - no Redis
os.environ['CACHE_BACKEND'] = 'django.core.cache.backends.locmem.LocMemCache'

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# Note: django.contrib.gis is disabled (no PointField used in models).
# Using django.db.backends.postgresql — GDAL/GEOS are not loaded at startup.
# Re-enable when adding spatial queries (requires trusted GDAL on the host).

# ── Environment ────────────────────────────────────────────────────────────────
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(BASE_DIR / ".env")

# ── Core ───────────────────────────────────────────────────────────────────────
SECRET_KEY = env("SECRET_KEY")
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
# ── Allowed Hosts — supports Railway + Render automatically ───────────────────
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.railway.app',
    '.onrender.com',
    'greenlens-production-5af0.up.railway.app',
    os.environ.get('RAILWAY_PUBLIC_DOMAIN', ''),
    os.environ.get('RENDER_EXTERNAL_HOSTNAME', ''),
    os.environ.get('ALLOWED_HOSTS', ''),
]

# Remove empty strings from list
ALLOWED_HOSTS = [h for h in ALLOWED_HOSTS if h]

# ── Installed Apps ─────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # GeoDjango — must come before any app using spatial models
    # "django.contrib.gis",   # disabled: no PointField used; avoids GDAL load on Windows
    # Third-party
    "rest_framework",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",
    # GreenLens apps
    "data_ingestion.apps.DataIngestionConfig",
    "risk_scoring.apps.RiskScoringConfig",
    "pricing_analysis.apps.PricingAnalysisConfig",
    "greenwash_detector.apps.GreenwashDetectorConfig",
    "dashboard.apps.DashboardConfig",
    "business.apps.BusinessConfig",  # Business & Monetization
    "risk_management.apps.RiskManagementConfig",  # Risk & Failure Management
    "ai_features.apps.AiFeaturesConfig",  # AI Prediction, Alerts, Portfolio Optimization
]

# ── Middleware ─────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Business middleware (rate limiting, usage tracking)
    "business.middleware.RateLimitMiddleware",
    "business.middleware.UsageTrackingMiddleware",
    "business.middleware.FeatureAccessMiddleware",
]

ROOT_URLCONF = "greenlens.urls"

# ── Templates ──────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "greenlens.wsgi.application"
ASGI_APPLICATION = "greenlens.asgi.application"

# ── Database — Railway + Render + local dev ───────────────────────────────────
# Railway and Render both inject DATABASE_URL automatically.
# Fall back to individual env vars for local development.
if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", default="greenlens_db"),
            "USER": env("DB_USER", default="greenlens_user"),
            "PASSWORD": env("DB_PASSWORD", default="greenlens_pass"),
            "HOST": env("DB_HOST", default="localhost"),
            "PORT": env("DB_PORT", default="5432"),
            "OPTIONS": {"connect_timeout": 10},
            "CONN_MAX_AGE": 600,
        }
    }

# ── Password validation ────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Localisation ───────────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Static / Media ─────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Use WhiteNoise for serving static files in production
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Django REST Framework ──────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "GreenLens API",
    "DESCRIPTION": "Satellite-verified climate risk scoring system for green bonds.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ── Caching — local memory (no Redis required on Railway or Render) ───────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "greenlens-cache",
    }
}

# ── Celery ─────────────────────────────────────────────────────────────────────
# Use Redis if available, otherwise disable Celery
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND") or os.environ.get("REDIS_URL")

if CELERY_BROKER_URL:
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
else:
    # Celery disabled - no Redis available
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ── Celery Beat Schedule ───────────────────────────────────────────────────────
# These entries are synced to the django_celery_beat_periodictask DB table on
# beat startup.  Override them in the Django admin (Periodic Tasks) if needed.
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Re-score all bonds every Sunday at 02:00 UTC
    "weekly-score-all-bonds": {
        "task": "risk_scoring.score_all_bonds",
        "schedule": crontab(hour=2, minute=0, day_of_week="sunday"),
        "options": {"expires": 82800},  # discard if not picked up within 23 h
    },
    # Refresh yield spread / pricing gaps every day at 03:00 UTC
    "daily-refresh-pricing": {
        "task": "pricing_analysis.refresh_pricing_data",
        "schedule": crontab(hour=3, minute=0),
        "options": {"expires": 82800},
    },
    # Re-check greenwash every Monday at 04:00 UTC
    "weekly-check-greenwash": {
        "task": "greenwash_detector.check_all_bonds",
        "schedule": crontab(hour=4, minute=0, day_of_week="monday"),
        "options": {"expires": 82800},
    },
    # Refresh NASA climate hazard data on the 1st of each month at 01:00 UTC
    "monthly-refresh-hazards": {
        "task": "data_ingestion.refresh_all_climate_hazards",
        "schedule": crontab(hour=1, minute=0, day_of_month="1"),
        "options": {"expires": 82800},
    },
    # Daily bond registry sync — marks all bonds as CBI-verified at 00:30 UTC
    "daily-sync-bond-registry": {
        "task": "data_ingestion.sync_bond_registry",
        "schedule": crontab(hour=0, minute=30),
        "options": {"expires": 82800},
    },
    # Re-train the PCRS model on the 1st day of each quarter at 05:00 UTC
    "quarterly-retrain-pcrs-model": {
        "task": "risk_scoring.train_model_task",
        "schedule": crontab(hour=5, minute=0, day_of_month="1", month_of_year="1,4,7,10"),
        "options": {"expires": 82800},
    },
    # ── NEW: Automatic Risk Management Monitoring ──
    # Monitor API health every 30 minutes
    "api-health-monitor": {
        "task": "risk_management.monitor_api_health",
        "schedule": 1800.0,  # Every 30 minutes (in seconds)
        "options": {"expires": 3600},
    },
    # Detect model drift weekly on Sundays at 03:00 UTC
    "weekly-model-drift-detector": {
        "task": "risk_management.detect_model_drift",
        "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
        "options": {"expires": 82800},
    },
    # Check data quality daily at 05:00 UTC
    "daily-data-quality-checker": {
        "task": "risk_management.check_data_quality",
        "schedule": crontab(hour=5, minute=0),
        "options": {"expires": 82800},
    },
    # Scrape regulatory updates weekly on Mondays at 06:00 UTC
    "weekly-scrape-regulatory-updates": {
        "task": "risk_management.scrape_regulatory_updates",
        "schedule": crontab(hour=6, minute=0, day_of_week="monday"),
        "options": {"expires": 82800},
    },
    # ── NEW: AI Features Regulatory Updates ──
    # Fetch real regulatory updates daily at 06:00 UTC
    "daily-refresh-regulatory-updates": {
        "task": "ai_features.refresh_regulatory_updates",
        "schedule": crontab(hour=6, minute=0),
        "options": {"expires": 82800},
    },
    # Clean up old resolved incidents daily at 07:00 UTC
    "daily-cleanup-old-incidents": {
        "task": "risk_management.cleanup_old_incidents",
        "schedule": crontab(hour=7, minute=0),
        "options": {"expires": 82800},
    },
    # Generate daily monitoring report at 08:00 UTC
    "daily-monitoring-report": {
        "task": "risk_management.generate_daily_monitoring_report",
        "schedule": crontab(hour=8, minute=0),
        "options": {"expires": 82800},
    },
}

# ── Google Earth Engine ────────────────────────────────────────────────────────
EE_SERVICE_ACCOUNT = env("EE_SERVICE_ACCOUNT", default="")
EE_PRIVATE_KEY_FILE = env("EE_PRIVATE_KEY_FILE", default="")
EE_PROJECT_ID = env("EE_PROJECT_ID", default="")

# ── AI Chat Assistant — Google Gemini ─────────────────────────────────────────
# Get a free key at: https://aistudio.google.com/app/apikey
# Set as environment variable GEMINI_API_KEY on Render dashboard.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


# ── NASA Earthdata ─────────────────────────────────────────────────────────────
EARTHDATA_USERNAME = env("EARTHDATA_USERNAME", default="")
EARTHDATA_PASSWORD = env("EARTHDATA_PASSWORD", default="")

# ── Security hardening (production only) ──────────────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = False
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"

# ── Logging ────────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "greenlens": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}
