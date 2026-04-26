"""greenlens/asgi.py — ASGI config for GreenLens."""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "greenlens.settings")
application = get_asgi_application()
