"""pricing_analysis/urls.py"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PricingGapViewSet,
    fit_analyser,
    get_pricing_gap_chart_data,
    get_market_summary,
    analyse_bond,
)

router = DefaultRouter()
router.register(r"gaps", PricingGapViewSet, basename="pricinggap")

urlpatterns = [
    path("", include(router.urls)),
    # PricingGapAnalyser endpoints
    path("analyser/fit/",            fit_analyser,               name="analyser-fit"),
    path("analyser/chart_data/",     get_pricing_gap_chart_data, name="analyser-chart-data"),
    path("analyser/market_summary/", get_market_summary,         name="analyser-market-summary"),
    path("analyser/analyse/",        analyse_bond,               name="analyser-analyse"),
]
