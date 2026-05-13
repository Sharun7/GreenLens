# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""data_ingestion/urls.py"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GreenBondViewSet, ClimateHazardDataViewSet, bonds_in_viewport

router = DefaultRouter()
router.register(r"", GreenBondViewSet, basename="greenbond")
router.register(r"hazards", ClimateHazardDataViewSet, basename="climatehazard")

urlpatterns = [
    path("", include(router.urls)),
    path("viewport/", bonds_in_viewport, name="bonds-viewport"),
]
