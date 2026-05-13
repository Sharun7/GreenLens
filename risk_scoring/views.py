# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""risk_scoring/views.py — PCRS score API endpoints."""
import logging
import numpy as np
from datetime import datetime, timezone
from threading import Lock

from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action, api_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import ModelFeedback, PCRScore
from .explainability import build_bond_model_depth, build_model_depth_framework
from .serializers import (
    ModelFeedbackSerializer,
    PCRScoreSerializer,
    PCRScoreDetailSerializer,
)
from .bias_detection import BiasDetector, generate_bias_summary_table

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


class ModelFeedbackViewSet(viewsets.ModelViewSet):
    """
    Feedback loop for model improvement.

    POST /api/risk/feedback/ records a fund-manager decision and later outcome.
    GET /api/risk/feedback/backtest_summary/ returns adverse-outcome counts used
    to prioritize model review and retraining.
    """
    queryset = ModelFeedback.objects.select_related("bond", "pcr_score").order_by("-created_at")
    serializer_class = ModelFeedbackSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "outcome_date", "realized_loss_bps", "pcr_score_at_decision"]

    @action(detail=False, methods=["get"], url_path="backtest_summary")
    def backtest_summary(self, request):
        adverse_filter = (
            Q(outcome__in=[
                ModelFeedback.Outcome.LOSS,
                ModelFeedback.Outcome.DEFAULT,
                ModelFeedback.Outcome.MODEL_ERROR,
            ])
            | Q(realized_loss_bps__gt=0)
        )
        agg = ModelFeedback.objects.aggregate(
            total=Count("id"),
            adverse=Count("id", filter=adverse_filter),
            used_for_retraining=Count("id", filter=adverse_filter & Q(used_for_retraining=True)),
            avg_loss_bps=Avg("realized_loss_bps", filter=Q(realized_loss_bps__isnull=False)),
        )

        by_outcome = (
            ModelFeedback.objects
            .values("outcome")
            .annotate(count=Count("id"), avg_loss_bps=Avg("realized_loss_bps"))
            .order_by("-count")
        )

        return Response({
            "meta": _META(),
            "result": {
                "total_feedback_events": agg["total"] or 0,
                "adverse_outcomes": agg["adverse"] or 0,
                "used_for_retraining": agg["used_for_retraining"] or 0,
                "review_queue": (agg["adverse"] or 0) - (agg["used_for_retraining"] or 0),
                "avg_realized_loss_bps": round(agg["avg_loss_bps"] or 0.0, 2),
                "by_outcome": list(by_outcome),
            },
        })

    @action(detail=False, methods=["get"], url_path="review_queue")
    def review_queue(self, request):
        adverse_filter = (
            Q(outcome__in=[
                ModelFeedback.Outcome.LOSS,
                ModelFeedback.Outcome.DEFAULT,
                ModelFeedback.Outcome.MODEL_ERROR,
            ])
            | Q(realized_loss_bps__gt=0)
        )
        qs = self.get_queryset().filter(adverse_filter, used_for_retraining=False)
        serializer = self.get_serializer(qs, many=True)
        return Response({
            "meta": _META(),
            "count": qs.count(),
            "results": serializer.data,
        })

    @action(detail=True, methods=["post"], url_path="mark_used_for_retraining")
    def mark_used_for_retraining(self, request, pk=None):
        feedback = self.get_object()
        feedback.used_for_retraining = True
        feedback.save(update_fields=["used_for_retraining", "updated_at"])
        serializer = self.get_serializer(feedback)
        return Response({"meta": _META(), "result": serializer.data})



# ── Bias Detection API ─────────────────────────────────────────────────────────

@api_view(["GET"])
def bias_detection_api(request):
    """
    GET /api/risk/bias-detection/
    
    Returns comprehensive bias detection analysis including:
    - Geographic bias (SHAP variance by region)
    - Synthetic label bias (circular reasoning indicators)
    - CNN classifier bias (tropical vs European accuracy)
    - Fairness metrics by region
    """
    detector = BiasDetector()
    results = detector.run_full_analysis()
    
    return Response({
        "meta": _META(),
        "results": results,
    })


@api_view(["GET"])
def bias_summary_api(request):
    """
    GET /api/risk/bias-summary/
    
    Returns structured bias summary table for documentation and UI display.
    """
    summary = generate_bias_summary_table()
    
    return Response({
        "meta": _META(),
        "summary": summary,
    })


@api_view(["GET"])
def model_depth_api(request):
    """
    GET /api/risk/model-depth/

    Returns the full Category 11 model-depth framework:
    three-level SHAP explainability, runtime bias detection, known bias table,
    and fairness metrics.
    """
    return Response({
        "meta": _META(),
        "result": build_model_depth_framework(include_runtime_bias=True),
    })


@api_view(["GET"])
def bond_model_depth_api(request, bond_pk):
    """
    GET /api/risk/model-depth/bond/<bond_pk>/

    Returns the plain-English and technical explanation for one bond.
    """
    from data_ingestion.models import GreenBond

    bond = get_object_or_404(GreenBond, pk=bond_pk)
    return Response({
        "meta": _META(),
        "result": build_bond_model_depth(bond),
    })
