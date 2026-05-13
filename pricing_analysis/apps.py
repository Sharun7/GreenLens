# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

from django.apps import AppConfig


class PricingAnalysisConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pricing_analysis"
    verbose_name = "Pricing Analysis"
