"""
pricing_analysis/views.py — Pricing Gap REST API.

Endpoints:
  GET  /api/pricing/gaps/                  — paginated list of all pricing gaps
  GET  /api/pricing/gaps/{id}/             — single pricing gap
  GET  /api/pricing/gaps/mispriced/        — bonds where |gap| >= 20 bps
  GET  /api/pricing/gaps/summary/          — aggregate stats
  POST /api/pricing/gaps/compute/          — compute gap for a single bond
  POST /api/pricing/gaps/batch_compute/    — compute gaps for all bonds
  POST /api/pricing/analyser/fit/          — fit PricingGapAnalyser from DB
  GET  /api/pricing/analyser/chart_data/   — scatter + regression line data
  GET  /api/pricing/analyser/market_summary/ — cross-sectional market stats
  POST /api/pricing/analyser/analyse/      — analyse single bond via regression model
"""
import logging
import threading
from datetime import date

from django.db.models import Avg, Count, Max, Min, Q
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from data_ingestion.models import GreenBond
from .models import PricingGap
from .serializers import PricingGapSerializer
from .pricing_fetcher import BondPricingFetcher
from .tasks import _detect_currency, _predicted_spread_from_pcr

logger = logging.getLogger("greenlens.pricing_views")

# ── Analyser singleton (lazy-loaded, thread-safe) ─────────────────────────────
_analyser = None
_analyser_lock = threading.Lock()


def _get_analyser():
    """Return the module-level PricingGapAnalyser singleton."""
    global _analyser
    if _analyser is None:
        with _analyser_lock:
            if _analyser is None:
                from .analyser import PricingGapAnalyser
                _analyser = PricingGapAnalyser()  # tries to load from disk
    return _analyser


_MATERIALITY_THRESHOLD_BPS = 20.0


def _compute_gap_for_bond(bond, fetcher: BondPricingFetcher):
    """
    Compute and persist a PricingGap for one bond.
    Returns (PricingGap, error_str_or_None).
    """
    try:
        maturity_years = float(bond.bond_maturity_years or 7)
        currency = _detect_currency(bond.country)

        actual_spread = None
        is_live = False

        if bond.bond_id:
            actual_spread = fetcher.get_yield_spread(bond.bond_id, maturity_years, currency)
            if actual_spread is not None:
                is_live = True

        if actual_spread is None:
            actual_spread = fetcher.get_synthetic_spread(
                "BBB", maturity_years, bond.country or ""
            )

        predicted_spread = _predicted_spread_from_pcr(bond, maturity_years)
        gap = fetcher.save_pricing_gap(
            bond=bond,
            actual_spread_bps=actual_spread,
            predicted_spread_bps=predicted_spread,
            is_live=is_live,
        )
        return gap, None
    except Exception as exc:
        logger.error("gap compute error bond %s: %s", bond.pk, exc, exc_info=True)
        return None, str(exc)


class PricingGapViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PricingGap.objects.select_related("bond").order_by("-checked_at")
    serializer_class = PricingGapSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["gap_bps", "checked_at", "is_mispriced"]

    @action(detail=False, methods=["get"])
    def mispriced(self, request):
        """
        GET /api/pricing/gaps/mispriced/
        Returns only bonds where |gap_bps| >= materiality threshold (20 bps).
        """
        qs = (
            PricingGap.objects
            .filter(is_mispriced=True)
            .select_related("bond")
            .order_by("-checked_at")
        )
        serializer = self.get_serializer(qs, many=True)
        return Response({
            "count": qs.count(),
            "threshold_bps": _MATERIALITY_THRESHOLD_BPS,
            "results": serializer.data,
        })

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        GET /api/pricing/gaps/summary/
        Aggregate statistics across all pricing gaps.
        """
        agg = PricingGap.objects.aggregate(
            total=Count("id"),
            mispriced=Count("id", filter=Q(is_mispriced=True)),
            avg_gap=Avg("gap_bps"),
            max_gap=Max("gap_bps"),
            min_gap=Min("gap_bps"),
            live_count=Count("id", filter=Q(is_live=True)),
        )

        # Category breakdown
        by_category = (
            PricingGap.objects
            .select_related("bond")
            .values("bond__project_category")
            .annotate(count=Count("id"), avg_gap=Avg("gap_bps"))
            .order_by("-avg_gap")
        )

        return Response({
            "as_of": date.today().isoformat(),
            "total_gaps": agg["total"] or 0,
            "mispriced_count": agg["mispriced"] or 0,
            "mispriced_pct": round(
                100 * (agg["mispriced"] or 0) / max(agg["total"] or 1, 1), 1
            ),
            "avg_gap_bps": round(agg["avg_gap"] or 0.0, 1),
            "max_gap_bps": round(agg["max_gap"] or 0.0, 1),
            "min_gap_bps": round(agg["min_gap"] or 0.0, 1),
            "live_data_count": agg["live_count"] or 0,
            "by_category": list(by_category),
        })

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def compute(self, request):
        """
        POST /api/pricing/gaps/compute/
        Body: {"bond_pk": <int>}
        Compute and persist a pricing gap for a single bond.
        """
        bond_pk = request.data.get("bond_pk")
        if bond_pk is None:
            return Response({"error": "bond_pk is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            bond = GreenBond.objects.get(pk=int(bond_pk))
        except (GreenBond.DoesNotExist, ValueError, TypeError):
            return Response({"error": f"Bond {bond_pk} not found"}, status=status.HTTP_404_NOT_FOUND)

        fetcher = BondPricingFetcher()
        gap, err = _compute_gap_for_bond(bond, fetcher)
        if err:
            return Response({"error": err}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "bond_pk": bond.pk,
            "bond_id": bond.bond_id,
            "actual_spread_bps": gap.actual_spread_bps,
            "predicted_spread_bps": gap.predicted_spread_bps,
            "gap_bps": gap.gap_bps,
            "is_mispriced": gap.is_mispriced,
            "is_live": gap.is_live,
            "calculation_date": gap.calculation_date.isoformat() if gap.calculation_date else None,
        })

    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def batch_compute(self, request):
        """
        POST /api/pricing/gaps/batch_compute/
        Body: {} (optional: {"bond_pks": [1,2,3]} to limit scope)
        Compute pricing gaps for all bonds (or specified subset, max 500).
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

        fetcher = BondPricingFetcher()
        results = {"success": [], "errors": []}

        for bond in qs:
            gap, err = _compute_gap_for_bond(bond, fetcher)
            if err:
                results["errors"].append({"bond_pk": bond.pk, "bond_id": bond.bond_id, "error": err})
            else:
                results["success"].append({
                    "bond_pk": bond.pk,
                    "bond_id": bond.bond_id,
                    "gap_bps": round(gap.gap_bps, 1),
                    "is_mispriced": gap.is_mispriced,
                })

        return Response({
            "processed": len(results["success"]) + len(results["errors"]),
            "success_count": len(results["success"]),
            "error_count": len(results["errors"]),
            "results": results,
        })


# ── Analyser endpoints (function-based views) ─────────────────────────────────

@api_view(["POST"])
def fit_analyser(request):
    """
    POST /api/pricing/analyser/fit/

    Train the PricingGapAnalyser regression model from existing DB data.
    Requires PricingGap + PCRScore records to already exist
    (run batch_compute and batch_predict first).

    Returns: training metrics including R², coefficients, gap distribution.
    """
    analyser = _get_analyser()
    try:
        metrics = analyser.fit_from_db()
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.error("fit_analyser error: %s", exc, exc_info=True)
        return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        "status": "fitted",
        "model": "LinearRegression",
        "features": ["pcrs_score", "bond_maturity_years", "credit_rating_numeric"],
        **metrics,
    })


@api_view(["GET"])
def get_pricing_gap_chart_data(request):
    """
    GET /api/pricing/analyser/chart_data/

    Returns all data needed to render the PCRS vs spread scatter plot:
      - scatter_data: one point per bond {x, y, bond_id, issuer, is_mispriced}
      - regression_line: model prediction at pcrs 0..100 step 5
      - upper_band / lower_band: ±2σ bounds
      - summary: n_underpriced, n_overpriced, n_fairly_priced, median_maturity
    """
    analyser = _get_analyser()

    # ── Scatter points ────────────────────────────────────────────────────────
    from django.db.models import OuterRef, Subquery
    from risk_scoring.models import PCRScore

    latest_score_sq = (
        PCRScore.objects
        .filter(bond=OuterRef("bond"))
        .order_by("-scored_at")
        .values("score")[:1]
    )

    qs = (
        PricingGap.objects
        .select_related("bond")
        .order_by("bond_id", "-checked_at")
        .annotate(pcrs_score=Subquery(latest_score_sq))
        .values(
            "bond_id",
            "bond__bond_id",
            "bond__issuer_name",
            "bond__project_category",
            "bond__bond_maturity_years",
            "actual_spread_bps",
            "predicted_spread_bps",
            "gap_bps",
            "is_mispriced",
            "pcrs_score",
        )
    )

    seen_bonds = set()
    scatter_data = []
    n_under = n_over = n_fair = 0
    maturities = []

    for row in qs:
        bond_pk = row["bond_id"]
        if bond_pk in seen_bonds:
            continue
        seen_bonds.add(bond_pk)

        pcrs = row["pcrs_score"]
        if pcrs is None:
            continue
        gap = float(row["gap_bps"] or 0)
        is_mispriced = bool(row["is_mispriced"])

        if gap > 0:
            n_under += 1
        elif gap < 0:
            n_over += 1
        else:
            n_fair += 1

        mat = row["bond__bond_maturity_years"]
        if mat:
            maturities.append(float(mat))

        scatter_data.append({
            "x": round(float(pcrs), 2),
            "y": round(float(row["actual_spread_bps"]), 2),
            "bond_id": row["bond__bond_id"],
            "issuer": row["bond__issuer_name"],
            "category": row["bond__project_category"],
            "predicted": round(float(row["predicted_spread_bps"] or 0), 2),
            "gap": round(gap, 2),
            "is_mispriced": is_mispriced,
        })

    # ── Regression line + bands ───────────────────────────────────────────────
    regression_line = []
    upper_band = []
    lower_band = []

    if analyser.is_fitted():
        median_mat = float(sorted(maturities)[len(maturities) // 2]) if maturities else 7.0
        regression_line, upper_band, lower_band = analyser.regression_line(
            maturity_years=median_mat
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    n_total = len(scatter_data)

    return Response({
        "scatter_data": scatter_data,
        "regression_line": regression_line,
        "upper_band": upper_band,
        "lower_band": lower_band,
        "summary": {
            "n_total": n_total,
            "n_underpriced": n_under,
            "n_overpriced": n_over,
            "n_fairly_priced": n_fair,
            "pct_underpriced": round(100 * n_under / max(n_total, 1), 1),
            "pct_overpriced": round(100 * n_over / max(n_total, 1), 1),
            "model_fitted": analyser.is_fitted(),
            "r2_model": round(analyser.r2_test, 4) if analyser.is_fitted() else None,
            "gap_std_bps": round(analyser.gap_std, 2) if analyser.is_fitted() else None,
        },
    })


@api_view(["GET"])
def get_market_summary(request):
    """
    GET /api/pricing/analyser/market_summary/

    Cross-sectional market statistics: % underpriced, % overpriced,
    mean gap by category, top-5 most mispriced bonds.
    Requires the analyser to have been fitted first.
    """
    analyser = _get_analyser()
    if not analyser.is_fitted():
        return Response(
            {
                "error": "Analyser not fitted. POST /api/pricing/analyser/fit/ first.",
                "hint": "You need PricingGap + PCRScore records in the DB.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        summary = analyser.get_market_summary()
    except Exception as exc:
        logger.error("market_summary error: %s", exc, exc_info=True)
        return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(summary)


@api_view(["POST"])
def analyse_bond(request):
    """
    POST /api/pricing/analyser/analyse/
    Body: {"bond_pk": <int>}

    Run the regression-model-based pricing gap analysis for a single bond.
    Returns actual vs predicted spread, gap, sigma distance, interpretation.
    """
    analyser = _get_analyser()
    if not analyser.is_fitted():
        return Response(
            {"error": "Analyser not fitted. POST /api/pricing/analyser/fit/ first."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    bond_pk = request.data.get("bond_pk")
    if bond_pk is None:
        return Response({"error": "bond_pk is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = analyser.analyse(int(bond_pk))
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        logger.error("analyse_bond error for pk %s: %s", bond_pk, exc, exc_info=True)
        return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(result)

