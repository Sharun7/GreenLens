# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ModelFeedbackViewSet,
    PCRScoreViewSet,
    bias_detection_api,
    bias_summary_api,
    bond_model_depth_api,
    model_depth_api,
)

router = DefaultRouter()
router.register(r"scores", PCRScoreViewSet, basename="pcrscore")
router.register(r"feedback", ModelFeedbackViewSet, basename="modelfeedback")

urlpatterns = [
    path("", include(router.urls)),
    path("bias-detection/", bias_detection_api, name="bias-detection"),
    path("bias-summary/", bias_summary_api, name="bias-summary"),
    path("model-depth/", model_depth_api, name="model-depth"),
    path("model-depth/bond/<int:bond_pk>/", bond_model_depth_api, name="bond-model-depth"),
]
