"""Bounded, read-only data endpoints for the climate intelligence workbench."""

import math
from datetime import date

from django.db.models import Avg, Count, F, FloatField, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Floor
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from data_ingestion.models import ClimateHazardData, GreenBond
from greenwash_detector.models import GreenwashFlag
from pricing_analysis.models import PricingGap
from risk_scoring.models import PCRScore


PAGE_SIZE = 50
MAP_LIMIT = 500


def _latest(model, timestamp, field):
    return Subquery(model.objects.filter(bond_id=OuterRef("pk")).order_by(
        f"-{timestamp}", "-pk",
    ).values(field)[:1])


def annotated_bonds():
    return GreenBond.objects.annotate(
        current_score=_latest(PCRScore, "scored_at", "score"),
        score_version=_latest(PCRScore, "scored_at", "model_version"),
        score_updated=_latest(PCRScore, "scored_at", "scored_at"),
        price_gap=_latest(PricingGap, "checked_at", "gap_bps"),
        price_flag=_latest(PricingGap, "checked_at", "is_mispriced"),
        price_live=_latest(PricingGap, "checked_at", "is_live"),
        price_updated=_latest(PricingGap, "checked_at", "checked_at"),
        satellite_flag=_latest(GreenwashFlag, "checked_at", "is_inconsistent"),
        satellite_status=_latest(GreenwashFlag, "checked_at", "verification_status"),
        satellite_source=_latest(GreenwashFlag, "checked_at", "raw_ee_metadata"),
        satellite_model=_latest(GreenwashFlag, "checked_at", "model_version"),
        satellite_updated=_latest(GreenwashFlag, "checked_at", "checked_at"),
    )


def observed_satellite(metadata, status, model):
    metadata = metadata if isinstance(metadata, dict) else {}
    return bool(
        status == "verifiable" and not (model or "").startswith("bootstrap")
        and metadata.get("method") != "synthetic"
        and metadata.get("source") not in ("synthetic", "deployment_bootstrap")
        and (metadata.get("source") == "gee" or metadata.get("collection") == "COPERNICUS/S2_SR_HARMONIZED")
    )


def _filtered(request):
    query = annotated_bonds()
    text = request.GET.get("q", "").strip()[:100]
    if text:
        query = query.filter(Q(bond_id__icontains=text) | Q(issuer_name__icontains=text) | Q(country__icontains=text))
    for parameter, field in (("country", "country"), ("category", "project_category")):
        value = request.GET.get(parameter, "").strip()
        if value:
            query = query.filter(**{field: value})
    try:
        year = request.GET.get("year")
        maturity = request.GET.get("maturity")
        minimum = float(request.GET.get("min_score", 0))
        maximum = float(request.GET.get("max_score", 100))
        if not all(math.isfinite(value) for value in (minimum, maximum)) or not 0 <= minimum <= maximum <= 100:
            raise ValueError
        if year:
            year = int(year)
            if not 1900 <= year <= date.today().year + 1:
                raise ValueError
            query = query.filter(issuance_date__year__gte=year)
        if maturity:
            maturity = int(maturity)
            if not 1 <= maturity <= 100:
                raise ValueError
            query = query.filter(bond_maturity_years__gte=maturity)
        if minimum > 0 or maximum < 100:
            query = query.filter(current_score__gte=minimum, current_score__lte=maximum)
        if request.GET.get("mispriced") == "1":
            query = query.filter(price_flag=True)
        if request.GET.get("flagged") == "1":
            query = query.filter(satellite_flag=True, satellite_status="verifiable").filter(
                Q(satellite_source__source="gee") | Q(satellite_source__collection="COPERNICUS/S2_SR_HARMONIZED")
            ).exclude(satellite_model__startswith="bootstrap").exclude(
                satellite_source__method="synthetic"
            ).exclude(satellite_source__source__in=["synthetic", "deployment_bootstrap"])
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid filter values. Check the year, maturity, and PCRS range.") from None
    return query


def _record(row):
    observed = observed_satellite(row.satellite_source, row.satellite_status, row.satellite_model)
    return {
        "id": row.pk, "bond_id": row.bond_id, "issuer": row.issuer_name,
        "country": row.country, "category": row.project_category, "lat": row.lat, "lon": row.lon,
        "location_confidence": row.location_confidence, "issuance_date": row.issuance_date.isoformat(),
        "maturity": row.bond_maturity_years, "score": row.current_score,
        "score_version": row.score_version, "score_updated": row.score_updated,
        "gap_bps": row.price_gap, "mispriced": bool(row.price_flag),
        "pricing_status": "Stored as live; verify source" if row.price_live else "Estimated spread" if row.price_gap is not None else "Unavailable",
        "satellite_status": "Review" if observed and row.satellite_flag else "Observed" if observed else "Unverifiable",
        "satellite_flag": bool(observed and row.satellite_flag),
    }


@require_GET
def workbench_data(request):
    try:
        query = _filtered(request)
        page = int(request.GET.get("page", "1"))
        if page < 1 or page > 100000:
            raise ValueError
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid filters or page number."}, status=400)
    total = query.count()
    page_count = max(1, math.ceil(total / PAGE_SIZE))
    if page > page_count:
        page = page_count
    rows = [_record(row) for row in query.order_by("-issuance_date", "-pk")[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]]
    summary = query.aggregate(
        latest_score_at=Max("score_updated"), latest_price_at=Max("price_updated"),
        latest_satellite_at=Max("satellite_updated"),
    )
    return JsonResponse({
        "total": total, "page": page, "page_size": PAGE_SIZE, "pages": page_count,
        "results": rows, "freshness": summary,
    })


@require_GET
def workbench_map(request):
    try:
        query = _filtered(request)
        zoom = int(request.GET.get("zoom", 2))
        south, west, north, east = [float(request.GET.get(name, default)) for name, default in (
            ("south", -90), ("west", -180), ("north", 90), ("east", 180),
        )]
        if (not all(math.isfinite(value) for value in (south, west, north, east))
                or not -90 <= south <= north <= 90 or not -180 <= west <= 180
                or not -180 <= east <= 180 or not 0 <= zoom <= 22):
            raise ValueError
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid map bounds or filters."}, status=400)
    query = query.filter(lat__gte=south, lat__lte=north)
    query = query.filter(lon__gte=west, lon__lte=east) if west <= east else query.filter(Q(lon__gte=west) | Q(lon__lte=east))
    total = query.count()
    if zoom < 8:
        cell = 20 if zoom < 4 else 5 if zoom < 6 else 1
        clusters = list(query.order_by().annotate(
            grid_lat=Floor(F("lat") / Value(cell), output_field=FloatField()),
            grid_lon=Floor(F("lon") / Value(cell), output_field=FloatField()),
        ).values("grid_lat", "grid_lon").annotate(
            count=Count("pk"), lat=Avg("lat"), lon=Avg("lon"), score=Avg("current_score"),
        ).order_by("-count", "grid_lat", "grid_lon")[:MAP_LIMIT + 1])
        return JsonResponse({"type": "clusters", "total": total, "results": clusters[:MAP_LIMIT], "truncated": len(clusters) > MAP_LIMIT})
    rows = list(query.order_by("-issuance_date", "-pk")[:MAP_LIMIT + 1])
    return JsonResponse({"type": "bonds", "total": total, "results": [_record(row) for row in rows[:MAP_LIMIT]], "truncated": len(rows) > MAP_LIMIT})


@require_GET
def workbench_detail(request, bond_id):
    row = get_object_or_404(annotated_bonds(), bond_id=bond_id)
    score = row.pcr_scores.order_by("-scored_at", "-pk").first()
    hazard = row.hazard_data.order_by("-data_date", "-pk").first()
    price = row.pricing_gaps.order_by("-checked_at", "-pk").first()
    flag = row.greenwash_flags.order_by("-checked_at", "-pk").first()
    metadata = score.feature_metadata if score and isinstance(score.feature_metadata, dict) else {}
    hazard_metadata = hazard.raw_metadata if hazard and isinstance(hazard.raw_metadata, dict) else {}
    demo_hazard = hazard_metadata.get("source") == "deployment_bootstrap" or hazard_metadata.get("method") == "synthetic" or bool(hazard_metadata.get("fallback"))
    explanations = []
    if score and metadata.get("artifact_status") == "manifest_checked" and isinstance(score.shap_values, dict):
        for name, value in score.shap_values.items():
            if isinstance(value, (int, float)) and math.isfinite(value):
                explanations.append({"feature": name, "contribution": value})
        explanations.sort(key=lambda item: abs(item["contribution"]), reverse=True)
    result = _record(row)
    result.update({
        "amount": str(row.amount_millions), "currency": row.currency, "registry_source": row.data_source,
        "score_input_status": metadata.get("provenance", {}).get("primary_status", "Demo estimate" if score and score.model_version.startswith("bootstrap") else "Not documented"),
        "score_driver": score.main_risk_driver if score else None,
        "shap_factors": explanations[:4],
        "hazards": {"flood": hazard.flood_risk_index, "heat": hazard.heat_stress_index,
                    "drought_spei": hazard.drought_spei, "date": hazard.data_date.isoformat(),
                    "status": "Demo / fallback estimate" if demo_hazard else "Stored source; not independently verified",
                    "source": hazard.source} if hazard else None,
        "pricing": {"spread": price.actual_spread_bps, "predicted": price.predicted_spread_bps,
                    "gap": price.gap_bps, "source": price.data_source, "is_live": price.is_live,
                    "checked_at": price.checked_at} if price else None,
        "satellite": {"status": result["satellite_status"], "checked_at": flag.checked_at,
                      "reason": (flag.raw_ee_metadata or {}).get("reason", "") if isinstance(flag.raw_ee_metadata, dict) else ""} if flag else None,
        "detail_url": f"/bond/{row.bond_id}/",
    })
    return JsonResponse(result)