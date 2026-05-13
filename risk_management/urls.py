# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""risk_management/urls.py — URL routing for risk management API."""
from django.urls import path
from .views import (
    risk_dashboard_api,
    failure_scenarios_api,
    legal_risks_api,
    classification_errors_api,
    drift_alerts_api,
    run_risk_check_api,
)

urlpatterns = [
    path("dashboard/",  risk_dashboard_api,       name="risk-dashboard"),
    path("scenarios/",  failure_scenarios_api,     name="risk-scenarios"),
    path("legal/",      legal_risks_api,           name="risk-legal"),
    path("errors/",     classification_errors_api, name="risk-errors"),
    path("drift/",      drift_alerts_api,          name="risk-drift"),
    path("run-check/",  run_risk_check_api,        name="risk-run-check"),
]
