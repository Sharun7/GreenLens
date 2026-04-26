"""data_ingestion/urls.py"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GreenBondViewSet, ClimateHazardDataViewSet

router = DefaultRouter()
router.register(r"", GreenBondViewSet, basename="greenbond")
router.register(r"hazards", ClimateHazardDataViewSet, basename="climatehazard")

urlpatterns = [path("", include(router.urls))]
