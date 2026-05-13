# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""ai_features/urls.py — Routes for AI predictions, alerts, portfolio, regulatory."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = "ai_features"

router = DefaultRouter()
router.register(r"scenarios", views.ScenarioViewSet, basename="scenario")
router.register(r"predictions", views.PredictionViewSet, basename="prediction")
router.register(r"alerts", views.AlertViewSet, basename="alert")
router.register(r"portfolios", views.PortfolioViewSet, basename="portfolio")
router.register(r"regulations", views.RegulatoryViewSet, basename="regulation")

urlpatterns = [
    path("predictions/", views.predictions_dashboard, name="predictions_dashboard"),
    path("alerts/", views.alerts_feed, name="alerts_feed"),
    path("portfolio/", views.portfolio_optimizer, name="portfolio_optimizer"),
    path("regulatory/", views.regulatory_monitor, name="regulatory_monitor"),
    path("api/v1/", include(router.urls)),
]
