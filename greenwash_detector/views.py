# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
greenwash_detector/views.py — Greenwash Detection REST API.

Endpoints:
  GET  /api/greenwash/flags/           — paginated list of all flags
  GET  /api/greenwash/flags/{id}/      — single flag
  GET  /api/greenwash/flags/flagged/   — only bonds flagged as inconsistent
  GET  /api/greenwash/flags/summary/   — aggregate stats
  POST /api/greenwash/flags/check/     — run check for a single bond
  POST /api/greenwash/flags/batch_check/ — run check for all bonds
"""
import logging
import threading

from django.db.models import Avg, Count, Q
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from data_ingestion.models import GreenBond
from .models import GreenwashFlag
from .serializers import GreenwashFlagSerializer

logger = logging.getLogger("greenlens.greenwash_views")

# Lazy singleton detector (model loads GEE once per process)
_detector = None
_detector_lock = threading.Lock()


def _get_detector():
    global _detector
    if _detector is None:
        with _detector_lock:
            if _detector is None:
                from .detection_engine import GreenwashDetector
                _detector = GreenwashDetector()
    return _detector


class GreenwashFlagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GreenwashFlag.objects.select_related("bond").order_by("-checked_at")
    serializer_class = GreenwashFlagSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["confidence", "checked_at", "is_inconsistent"]

    @action(detail=False, methods=["get"])
    def flagged(self, request):
        """
        GET /api/greenwash/flags/flagged/
        Returns only bonds where greenwash evidence is inconsistent.
        """
        qs = (
            GreenwashFlag.objects
            .filter(is_inconsistent=True)
            .select_related("bond")
            .order_by("-confidence", "-checked_at")
        )
        serializer = self.get_serializer(qs, many=True)
        return Response({
            "count": qs.count(),
            "results": serializer.data,
        })

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        GET /api/greenwash/flags/summary/
        Aggregate statistics across all greenwash checks.
        """
        agg = GreenwashFlag.objects.aggregate(
            total=Count("id"),
            flagged=Count("id", filter=Q(is_inconsistent=True)),
            avg_confidence=Avg("confidence"),
        )

        by_category = (
            GreenwashFlag.objects
            .select_related("bond")
            .values("bond__project_category")
            .annotate(
                count=Count("id"),
                flagged=Count("id", filter=Q(is_inconsistent=True)),
                avg_confidence=Avg("confidence"),
            )
            .order_by("-flagged")
        )

        by_land_use = (
            GreenwashFlag.objects
            .values("satellite_land_use")
            .annotate(count=Count("id"), flagged=Count("id", filter=Q(is_inconsistent=True)))
            .order_by("-flagged")
        )

        return Response({
            "total_checked": agg["total"] or 0,
            "flagged_count": agg["flagged"] or 0,
            "flagged_pct": round(
                100 * (agg["flagged"] or 0) / max(agg["total"] or 1, 1), 1
            ),
            "avg_confidence": round(agg["avg_confidence"] or 0.0, 3),
            "by_category": list(by_category),
            "by_land_use": list(by_land_use),
        })

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def check(self, request):
        """
        POST /api/greenwash/flags/check/
        Body: {"bond_pk": <int>}
        Run greenwash detection for a single bond and persist result.
        """
        bond_pk = request.data.get("bond_pk")
        if bond_pk is None:
            return Response({"error": "bond_pk is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            bond = GreenBond.objects.get(pk=int(bond_pk))
        except (GreenBond.DoesNotExist, ValueError, TypeError):
            return Response({"error": f"Bond {bond_pk} not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            detector = _get_detector()
            result = detector.check_bond(bond)
        except Exception as exc:
            logger.error("Greenwash check failed for bond %s: %s", bond_pk, exc, exc_info=True)
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        flag, _ = GreenwashFlag.objects.update_or_create(
            bond=bond,
            defaults={k: v for k, v in result.items() if k != "bond"},
        )

        return Response({
            "bond_pk": bond.pk,
            "bond_id": bond.bond_id,
            "claimed_project_type": flag.claimed_project_type,
            "satellite_land_use": flag.satellite_land_use,
            "ndvi_change": flag.ndvi_change,
            "is_inconsistent": flag.is_inconsistent,
            "confidence": flag.confidence,
            "model_version": flag.model_version,
            "pre_project_image_date": flag.pre_project_image_date.isoformat() if flag.pre_project_image_date else None,
            "post_project_image_date": flag.post_project_image_date.isoformat() if flag.post_project_image_date else None,
        })

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def visualise(self, request):
        """
        GET /api/greenwash/flags/visualise/?bond_pk=123
        Returns GEE RGB thumbnail URLs for before/after images.
        """
        bond_pk = request.query_params.get("bond_pk")
        if not bond_pk:
            return Response({"error": "bond_pk is required"}, status=400)
            
        try:
            bond = GreenBond.objects.get(pk=int(bond_pk))
        except GreenBond.DoesNotExist:
            return Response({"error": "Bond not found"}, status=404)
            
        try:
            from datetime import timedelta
            from .satellite_verifier import get_dynamic_radius
            issue_dt = bond.issuance_date
            before_str = (issue_dt - timedelta(days=365)).isoformat()
            after_str = (issue_dt + timedelta(days=365)).isoformat()
            
            dynamic_radius = get_dynamic_radius(bond.project_category)
            
            detector = _get_detector()
            verifier = detector._verifier
            urls = verifier.get_visualisation_urls(
                float(bond.lat), float(bond.lon), before_str, after_str, radius_km=dynamic_radius
            )
            return Response(urls)
        except Exception as exc:
            return Response({"error": str(exc)}, status=500)

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def batch_check(self, request):
        """
        POST /api/greenwash/flags/batch_check/
        Body: {} (optional: {"bond_pks": [1,2,3]} to limit scope, max 500)
        Run greenwash detection for all bonds (or specified subset).
        """
        bond_pks = request.data.get("bond_pks")
        qs = GreenBond.objects.all()
        if bond_pks:
            if len(bond_pks) > 500:
                return Response(
                    {"error": "Maximum 500 bonds per batch"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(pk__in=bond_pks)

        detector = _get_detector()
        results = {"flagged": [], "consistent": [], "errors": []}

        for bond in qs:
            try:
                result = detector.check_bond(bond)
                flag, _ = GreenwashFlag.objects.update_or_create(
                    bond=bond,
                    defaults={k: v for k, v in result.items() if k != "bond"},
                )
                bucket = "flagged" if flag.is_inconsistent else "consistent"
                results[bucket].append({
                    "bond_pk": bond.pk,
                    "bond_id": bond.bond_id,
                    "is_inconsistent": flag.is_inconsistent,
                    "confidence": flag.confidence,
                    "satellite_land_use": flag.satellite_land_use,
                    "ndvi_change": flag.ndvi_change,
                })
            except Exception as exc:
                logger.error("batch_check error bond %s: %s", bond.pk, exc)
                results["errors"].append({"bond_pk": bond.pk, "bond_id": bond.bond_id, "error": str(exc)})

        return Response({
            "processed": len(results["flagged"]) + len(results["consistent"]) + len(results["errors"]),
            "flagged_count": len(results["flagged"]),
            "consistent_count": len(results["consistent"]),
            "error_count": len(results["errors"]),
            "results": results,
        })
