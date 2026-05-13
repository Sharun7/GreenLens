# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_management/apps.py — App configuration for risk management module.
"""
from django.apps import AppConfig


class RiskManagementConfig(AppConfig):
    """Configuration for the risk_management app."""
    
    default_auto_field = "django.db.models.BigAutoField"
    name = "risk_management"
    verbose_name = "Risk Management"
