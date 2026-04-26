"""risk_scoring/views.py — PCRS score API endpoints."""
import logging
import numpy as np
from datetime import datetime, timezone
from threading import Lock

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import PCRScore
from .serializers import PCRScoreSerializer, PCRScoreDetailSerializer

logger = logging.getLogger("greenlens.risk_scoring.views")

MODEL_VERSION = "v1.0.0"
_META = lambda: {"timestamp": datetime.now(timezone.utc).isoformat(), "model_version": MODEL_VERSION}

# ── Lazy predictor singleton — loaded once per worker process ─────────────────
_predictor = None
_predictor_lock = Lock()


def _get_predictor():
    global _predictor
    if _predictor is None:
        with _predictor_lock:
            if _predictor is None:
                from risk_scoring.ml_engine import PCRSPredictor
                _predictor = PCRSPredictor()
    return _predictor


class PCRScoreViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/risk/scores/                 — list all PCRS scores
    GET  /api/risk/scores/<pk>/            — single score detail
    GET  /api/risk/scores/distribution/   — histogram data
    POST /api/risk/scores/predict/         — score a single bond  { "bond_pk": <int> }
    POST /api/risk/scores/batch_predict/   — score multiple bonds { "bond_pks": [<int>, …] }
    """
    queryset = PCRScore.objects.select_related("bond").order_by("-scored_at")
    serializer_class = PCRScoreSerializer
    filter_backends  = [filters.OrderingFilter]
    ordering_fields  = ["score", "scored_at", "model_version"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PCRScoreDetailSerializer
        return PCRScoreSerializer

    @method_decorator(cache_page(60 * 5))
    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(qs, many=True)
        return Response({"meta": _META(), "results": serializer.data})

    def retrieve(self, request, *args, **kwargs):
        instance   = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({"meta": _META(), "result": serializer.data})

    @action(detail=False, methods=["get"], url_path="distribution")
    @method_decorator(cache_page(60 * 10))
    def distribution(self, request):
        """
        GET /api/risk/scores/distribution/
        Returns histogram of PCRS scores across the full dataset.
        """
        # PostgreSQL DISTINCT ON requires bond_id to be first in ORDER BY
        scores = list(
            PCRScore.objects.order_by("bond_id", "-scored_at")
            .distinct("bond_id")
            .values_list("score", flat=True)
        )
        if not scores:
            return Response(
                {"meta": _META(), "result": {"bins": [], "counts": [], "total": 0, "mean": 0.0, "median": 0.0}}
            )

        arr    = np.array(scores, dtype=float)
        counts, bin_edges = np.histogram(arr, bins=10, range=(0, 100))

        return Response({
            "meta": _META(),
            "result": {
                "bins":   [round(float(b), 1) for b in bin_edges],
                "counts": [int(c) for c in counts],
                "total":  len(scores),
                "mean":   round(float(arr.mean()), 2),
                "median": round(float(np.median(arr)), 2),
            },
        })

    @action(detail=False, methods=["post"], url_path="predict",
            permission_classes=[AllowAny])
    def predict(self, request):
        """
        POST /api/risk/scores/predict/
        Body: { "bond_pk": <int> }

        Runs PCRS inference for the given bond, persists the PCRScore record,
        and returns the full result.
        """
        bond_pk = request.data.get("bond_pk")
        if bond_pk is None:
            return Response(
                {"error": "bond_pk is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            bond_pk = int(bond_pk)
        except (TypeError, ValueError):
            return Response(
                {"error": "bond_pk must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            predictor = _get_predictor()
            result = predictor.predict(bond_pk)
        except FileNotFoundError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            logger.exception("predict failed for bond_pk=%s", bond_pk)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"meta": _META(), "result": result}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="batch_predict",
            permission_classes=[AllowAny])
    def batch_predict(self, request):
        """
        POST /api/risk/scores/batch_predict/
        Body: { "bond_pks": [<int>, …] }

        Runs PCRS inference for each bond in the list (max 200 at a time).
        Returns per-bond results and a summary of any errors.
        """
        bond_pks = request.data.get("bond_pks")
        if not bond_pks or not isinstance(bond_pks, list):
            return Response(
                {"error": "bond_pks must be a non-empty list of integers"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(bond_pks) > 200:
            return Response(
                {"error": "Maximum 200 bonds per batch request"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            bond_pks = [int(pk) for pk in bond_pks]
        except (TypeError, ValueError):
            return Response(
                {"error": "All bond_pks must be integers"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            predictor = _get_predictor()
        except FileNotFoundError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        results = []
        errors  = []
        for pk in bond_pks:
            try:
                results.append(predictor.predict(pk))
            except Exception as exc:
                logger.warning("batch_predict: bond_pk=%s failed: %s", pk, exc)
                errors.append({"bond_pk": pk, "error": str(exc)})

        return Response({
            "meta":    _META(),
            "results": results,
            "errors":  errors,
            "summary": {
                "requested": len(bond_pks),
                "succeeded": len(results),
                "failed":    len(errors),
            },
        }, status=status.HTTP_200_OK)

