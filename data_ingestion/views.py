# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""data_ingestion/views.py — REST API views for GreenBond and ClimateHazardData."""
from datetime import datetime, timezone

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import GreenBond, ClimateHazardData
from .serializers import (
    GreenBondListSerializer,
    GreenBondDetailSerializer,
    GreenBondSerializer,
    ClimateHazardDataSerializer,
)
from .reliability import build_bond_reliability, build_global_reliability_summary

MODEL_VERSION = "v1.0.0"
_META = lambda: {"timestamp": datetime.now(timezone.utc).isoformat(), "model_version": MODEL_VERSION}


class GreenBondViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/bonds/               — list with latest PCRScore + is_mispriced
    GET /api/bonds/<pk>/          — full detail (PCRS + pricing + greenwash)
    POST /api/bonds/<pk>/rescore/ — trigger async PCRS refresh
    Filters: ?category=solar  ?min_score=50
    """
    queryset = GreenBond.objects.all().order_by("-issuance_date")
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields   = ["bond_id", "issuer_name", "country", "project_category"]
    ordering_fields = ["issuance_date", "amount_millions", "country"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return GreenBondDetailSerializer
        return GreenBondListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        category  = self.request.query_params.get("category")
        min_score = self.request.query_params.get("min_score")

        if category:
            qs = qs.filter(project_category=category)

        if min_score is not None:
            try:
                threshold = float(min_score)
                from risk_scoring.models import PCRScore
                from django.db.models import OuterRef, Subquery
                latest_score_sq = (
                    PCRScore.objects.filter(bond=OuterRef("pk"))
                    .order_by("-scored_at")
                    .values("score")[:1]
                )
                qs = qs.annotate(latest_score_val=Subquery(latest_score_sq))
                qs = qs.filter(latest_score_val__gte=threshold)
            except (ValueError, TypeError):
                pass

        return qs

    @method_decorator(cache_page(60 * 5))
    def list(self, request, *args, **kwargs):
        qs         = self.filter_queryset(self.get_queryset())
        page       = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True)
        data       = serializer.data
        if page is not None:
            return self.get_paginated_response({"meta": _META(), "results": data})
        return Response({"meta": _META(), "results": data})

    def retrieve(self, request, *args, **kwargs):
        instance   = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({"meta": _META(), "result": serializer.data})

    @action(detail=True, methods=["get"], url_path="reliability")
    def reliability(self, request, pk=None):
        """
        GET /api/bonds/<pk>/reliability/
        Per-bond source trust, missing-data handling, and conflict resolution.
        """
        bond = self.get_object()
        return Response({
            "meta": _META(),
            "bond_id": bond.bond_id,
            "result": build_bond_reliability(bond),
        })

    @action(detail=False, methods=["get"], url_path="reliability_framework")
    def reliability_framework(self, request):
        """
        GET /api/bonds/reliability_framework/
        Dataset-level reliability policy and counts.
        """
        return Response({
            "meta": _META(),
            "result": build_global_reliability_summary(),
        })

    @action(detail=True, methods=["post"], url_path="rescore")
    def rescore(self, request, pk=None):
        """
        POST /api/bonds/<pk>/rescore/
        Enqueues an async Celery task to refresh the PCRS for this bond.
        """
        bond = self.get_object()
        try:
            from risk_scoring.tasks import score_single_bond
            task = score_single_bond.delay(bond.pk)
            return Response(
                {
                    "meta":    _META(),
                    "message": f"Rescore task queued for bond {bond.bond_id}",
                    "task_id": task.id,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as exc:
            return Response(
                {"meta": _META(), "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"], url_path="sebi-disclosure")
    def sebi_disclosure(self, request, pk=None):
        """
        GET /api/bonds/<pk>/sebi-disclosure/
        SEBI Green Bond Framework compliant disclosure report for India bonds.
        Category 19 — Global vs India Context
        """
        bond = self.get_object()
        try:
            from .regulatory_compliance import RegulatoryComplianceGenerator
            report = RegulatoryComplianceGenerator.generate_sebi_report(bond)
            report["report_generated_at"] = datetime.now(timezone.utc).isoformat()
            return Response({
                "meta": _META(),
                "bond_id": bond.bond_id,
                "result": report,
            })
        except Exception as exc:
            return Response(
                {"meta": _META(), "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"], url_path="esma-disclosure")
    def esma_disclosure(self, request, pk=None):
        """
        GET /api/bonds/<pk>/esma-disclosure/
        ESMA/EU Green Bond Standard compliant disclosure report for Germany bonds.
        Category 19 — Global vs India Context
        """
        bond = self.get_object()
        try:
            from .regulatory_compliance import RegulatoryComplianceGenerator
            report = RegulatoryComplianceGenerator.generate_esma_report(bond)
            report["report_generated_at"] = datetime.now(timezone.utc).isoformat()
            return Response({
                "meta": _META(),
                "bond_id": bond.bond_id,
                "result": report,
            })
        except Exception as exc:
            return Response(
                {"meta": _META(), "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ClimateHazardDataViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ClimateHazardData.objects.select_related("bond").order_by("-data_date")
    serializer_class = ClimateHazardDataSerializer
    filter_backends  = [filters.OrderingFilter]
    ordering_fields  = ["data_date", "flood_risk_index", "heat_stress_index"]




# ── Viewport-Based Loading for Scaling ────────────────────────────────────────

@api_view(["GET"])
def bonds_in_viewport(request):
    """
    GET /api/bonds/viewport/?min_lat=&max_lat=&min_lon=&max_lon=&zoom=
    
    Returns bonds within the specified viewport bounding box.
    Implements viewport-based loading for scaling to 1 lakh bonds.
    
    Query Parameters:
    - min_lat, max_lat, min_lon, max_lon: Bounding box coordinates
    - zoom: Map zoom level (1-20)
    - limit: Max bonds to return (default: 1000)
    
    Behavior:
    - Zoom < 5: Returns country-level clusters
    - Zoom 5-8: Returns bonds with clustering
    - Zoom > 8: Returns individual bonds
    """
    from django.db.models import Count, Avg
    
    try:
        min_lat = float(request.GET.get('min_lat', -90))
        max_lat = float(request.GET.get('max_lat', 90))
        min_lon = float(request.GET.get('min_lon', -180))
        max_lon = float(request.GET.get('max_lon', 180))
        zoom = int(request.GET.get('zoom', 1))
        limit = min(int(request.GET.get('limit', 1000)), 5000)  # Max 5000 bonds
    except (ValueError, TypeError):
        return Response(
            {"error": "Invalid viewport parameters"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Filter bonds within viewport
    bonds_qs = GreenBond.objects.filter(
        lat__gte=min_lat,
        lat__lte=max_lat,
        lon__gte=min_lon,
        lon__lte=max_lon,
    ).prefetch_related('pcr_scores', 'greenwash_flags', 'pricing_gaps')
    
    # Zoom-based clustering
    if zoom < 5:
        # Country-level clusters
        clusters = bonds_qs.values('country').annotate(
            count=Count('id'),
            avg_lat=Avg('lat'),
            avg_lon=Avg('lon'),
            avg_pcr=Avg('pcr_scores__score'),
        ).order_by('-count')[:100]
        
        return Response({
            "type": "clusters",
            "zoom": zoom,
            "clusters": list(clusters),
            "total_bonds": bonds_qs.count(),
        })
    
    elif zoom < 8:
        # Category-level clusters within countries
        clusters = bonds_qs.values('country', 'project_category').annotate(
            count=Count('id'),
            avg_lat=Avg('lat'),
            avg_lon=Avg('lon'),
            avg_pcr=Avg('pcr_scores__score'),
        ).order_by('-count')[:200]
        
        return Response({
            "type": "clusters",
            "zoom": zoom,
            "clusters": list(clusters),
            "total_bonds": bonds_qs.count(),
        })
    
    else:
        # Individual bonds
        bonds = bonds_qs[:limit]
        serializer = GreenBondListSerializer(bonds, many=True)
        
        return Response({
            "type": "bonds",
            "zoom": zoom,
            "bonds": serializer.data,
            "total_in_viewport": bonds_qs.count(),
            "returned": len(serializer.data),
        })
