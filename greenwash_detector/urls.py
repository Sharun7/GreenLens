# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""greenwash_detector/urls.py"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GreenwashFlagViewSet

router = DefaultRouter()
router.register(r"flags", GreenwashFlagViewSet, basename="greenwashflag")

urlpatterns = [path("", include(router.urls))]
