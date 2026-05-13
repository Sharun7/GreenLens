# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

# Ensure Celery app is loaded when Django starts
from .celery import app as celery_app

__all__ = ("celery_app",)
