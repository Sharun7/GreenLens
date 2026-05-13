# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""greenlens/celery.py — Celery application instance."""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "greenlens.settings")

app = Celery("greenlens")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
