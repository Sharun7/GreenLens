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
    path("about/", views.about, name="about"),
    path("export/", views.export_bonds_csv, name="export_csv"),
    path("export/sfdr/", views.export_sfdr_report, name="export_sfdr"),
    path("terms/", views.terms, name="terms"),
    
    # Legacy API endpoint
    path("api/dashboard/stats/", views.dashboard_stats, name="stats"),
    
    # API v1 endpoints (DRF ViewSets)
    path("api/v1/", include(api_router.urls)),
]
