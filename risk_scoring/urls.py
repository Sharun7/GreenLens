"""risk_scoring/urls.py"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PCRScoreViewSet

router = DefaultRouter()
router.register(r"scores", PCRScoreViewSet, basename="pcrscore")

urlpatterns = [path("", include(router.urls))]
