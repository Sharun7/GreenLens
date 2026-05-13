# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""dashboard/urls.py — URL routing for dashboard and API endpoints."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = "dashboard"

# =============================================================================
# API Router
# =============================================================================

api_router = DefaultRouter()
api_router.register(r"bonds", views.BondViewSet, basename="bond")
api_router.register(r"pcrs", views.PCRSViewSet, basename="pcrs")
api_router.register(r"pricing", views.PricingGapViewSet, basename="pricing")

# =============================================================================
# URL Patterns
# =============================================================================

urlpatterns = [
    # HTML Views
    path("", views.index, name="index"),
    path("bond/<str:bond_id>/", views.bond_detail, name="bond_detail"),
    path("pricing/", views.pricing_analysis, name="pricing_analysis"),
    path("portfolio/", views.portfolio_optimizer, name="portfolio"),
    path("about/", views.about, name="about"),
    path("model-bias/", views.model_bias_analysis, name="model_bias"),
    path("risk-management/", views.risk_management_view, name="risk_management"),
    path("decision-impact/", views.decision_impact, name="decision_impact"),
    path("model-trust/", views.model_trust_explainability, name="model_trust"),
    path("data-pipeline/", views.data_pipeline_reality, name="data_pipeline"),
    path("future/", views.future_innovations, name="future_innovations"),
    path("export/", views.export_bonds_csv, name="export_csv"),
    path("export/sfdr/", views.export_sfdr_report, name="export_sfdr"),
    path("terms/", views.terms, name="terms"),
    
    # API endpoints
    path("api/alerts/", views.live_alerts_api, name="api_alerts"),
    path("api/data-reliability/", views.data_reliability_api, name="api_data_reliability"),
    path("api/model-depth/", views.model_depth_api, name="api_model_depth"),
    path("api/dashboard/stats/", views.dashboard_stats, name="stats"),
    
    # API v1 endpoints (DRF ViewSets)
    path("api/v1/", include(api_router.urls)),
]
