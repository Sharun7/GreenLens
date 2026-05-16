# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""greenlens/urls.py — Root URL configuration."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def _favicon(request):
    """Serve an inline SVG favicon to suppress 404 errors."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<text y=".9em" font-size="90">🌿</text></svg>'
    )
    return HttpResponse(svg, content_type="image/svg+xml")

urlpatterns = [
    path("favicon.ico", _favicon, name="favicon"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/bonds/", include("data_ingestion.urls")),
    path("api/risk/", include("risk_scoring.urls")),
    path("api/pricing/", include("pricing_analysis.urls")),
    path("api/greenwash/", include("greenwash_detector.urls")),
    path("api/risk-management/", include("risk_management.urls")),
    path("ai/", include("ai_features.urls")),
    path("", include("dashboard.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
