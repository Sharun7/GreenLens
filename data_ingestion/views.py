"""data_ingestion/views.py — REST API views for GreenBond and ClimateHazardData."""
from datetime import datetime, timezone

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import GreenBond, ClimateHazardData
from .serializers import (
    GreenBondListSerializer,
    GreenBondDetailSerializer,
    GreenBondSerializer,
    ClimateHazardDataSerializer,
)

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


class ClimateHazardDataViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ClimateHazardData.objects.select_related("bond").order_by("-data_date")
    serializer_class = ClimateHazardDataSerializer
    filter_backends  = [filters.OrderingFilter]
    ordering_fields  = ["data_date", "flood_risk_index", "heat_stress_index"]

