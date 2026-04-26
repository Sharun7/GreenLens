import os
import dj_database_url
from .settings import *

# Override DEBUG flag
DEBUG = False

# Extract ALLOWED_HOSTS from environment variable
allowed_hosts_env = os.environ.get("ALLOWED_HOSTS", "")
if allowed_hosts_env:
    ALLOWED_HOSTS = allowed_hosts_env.split(",")
else:
    # Fallback to general domains for Render
    ALLOWED_HOSTS = [".onrender.com"]

# Setup Database using dj-database-url (parses DATABASE_URL from Render)
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600,
        ssl_require=True
    )
}

# Ensure PostGIS engine is respected if database string starts with postgres:// 
if DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql':
    DATABASES['default']['ENGINE'] = 'django.contrib.gis.db.backends.postgis'

# Whitenoise for Static File Delivery
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# CORS configuration for external API requests
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "https://greenlens-demo.onrender.com", 
    "https://greenlens-web.onrender.com"
]

# Security enforcing SSL Redirects and Security Headers
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
