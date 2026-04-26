"""
greenlens/settings.py — Production-ready Django 5 settings for GreenLens.
"""
import os
from pathlib import Path

import environ

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
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

RENDER_EXTERNAL_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME", default=None)
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

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
    "data_ingestion",
    "risk_scoring",
    "pricing_analysis",
    "greenwash_detector",
    "dashboard",
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

# ── Database — PostgreSQL + PostGIS ───────────────────────────────────────────
# Render/Heroku provide DATABASE_URL; fall back to individual env vars for local dev.
_database_url = env("DATABASE_URL", default="")
if _database_url:
    DATABASES = {"default": env.db("DATABASE_URL")}
    # Force plain PostgreSQL engine — postgis:// engine triggers GDAL load (Windows issue)
    DATABASES["default"]["ENGINE"] = "django.db.backends.postgresql"
    DATABASES["default"]["CONN_MAX_AGE"] = 600
    DATABASES["default"].setdefault("OPTIONS", {})["connect_timeout"] = 10
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", default="greenlens_db"),
            "USER": env("DB_USER", default="greenlens_user"),
            "PASSWORD": env("DB_PASSWORD", default="greenlens_pass"),
            "HOST": env("DB_HOST", default="localhost"),
            "PORT": env("DB_PORT", default="5432"),
            "OPTIONS": {
                "connect_timeout": 10,
            },
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

# ── Caching (Redis in production, LocMem in dev) ──────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/2"),
    } if not DEBUG else {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# ── Celery ─────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
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
}

# ── Google Earth Engine ────────────────────────────────────────────────────────
EE_SERVICE_ACCOUNT = env("EE_SERVICE_ACCOUNT", default="")
EE_PRIVATE_KEY_FILE = env("EE_PRIVATE_KEY_FILE", default="")
EE_PROJECT_ID = env("EE_PROJECT_ID", default="")

# ── NASA Earthdata ─────────────────────────────────────────────────────────────
EARTHDATA_USERNAME = env("EARTHDATA_USERNAME", default="")
EARTHDATA_PASSWORD = env("EARTHDATA_PASSWORD", default="")

# ── Security hardening (production only) ──────────────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = True
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
