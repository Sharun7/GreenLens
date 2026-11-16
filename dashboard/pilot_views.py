from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from data_ingestion.models import PilotIngestionRun, PilotOutcome, PilotProject


def pilot_snapshot():
    projects = list(PilotProject.objects.filter(region="TX", category="solar").prefetch_related("evidence_runs")[:50])
    rows, features = [], []
    for project in projects:
        evidence = next(iter(project.evidence_runs.all()), None)
        current = evidence is not None and evidence.boundary_sha256 == project.boundary_sha256
        row = {
            "id": project.pk, "source_id": project.source_id, "name": project.name,
            "county": project.source_metadata.get("p_county", "Unknown"),
            "review": project.review_status, "source_url": project.source_url,
            "version": project.source_version, "boundary_sha256": project.boundary_sha256,
            "capacity_mw": project.source_metadata.get("p_cap_ac"),
            "status": evidence.status if current else "not_collected",
            "windows": evidence.windows if current else {},
            "optical": evidence.optical if current else {}, "sar": evidence.sar if current else {},
            "collected_at": evidence.collected_at.isoformat() if current else None,
        }
        rows.append(row)
        features.append({"type": "Feature", "geometry": project.boundary, "properties": {"id": project.pk, "name": project.name}})
    labels = PilotOutcome.objects.filter(project__in=projects, independently_observed=True, reviewed_by__isnull=False, reviewed_at__isnull=False).count()
    return {
        "projects": rows, "geojson": {"type": "FeatureCollection", "features": features},
        "summary": {"projects": len(rows), "reviewed_boundaries": sum(row["review"] == "approved" for row in rows),
                    "both_observed": sum(row["status"] == "both_observed" for row in rows), "reviewed_outcomes": labels},
        "ingestion": list(PilotIngestionRun.objects.values("started_at", "completed_at", "status", "result")[:5]),
        "evaluation": "Blocked: independent reviewed outcomes are required" if not labels else "Split, provenance, and calibration gates must pass before evaluation",
        "encoder_benchmark": "Pending independent labels and reproducible encoder prediction artifacts",
        "financial_optimization": "Blocked: no independently evidenced financial-return scenario dataset supplied",
        "climate_scenarios": "Blocked: no reviewed multi-model climate-projection dataset supplied",
    }


@require_GET
def pilot_workspace(request):
    snapshot = pilot_snapshot()
    return render(request, "dashboard/project_pilot.html", {"pilot": snapshot, "projects": snapshot["projects"], "summary": snapshot["summary"]})


@require_GET
def pilot_status(request):
    return JsonResponse(pilot_snapshot())


@require_POST
def review_pilot_boundary(request):
    if not request.user.is_staff or not request.user.has_perm("data_ingestion.change_pilotproject"):
        return JsonResponse({"error": "Authorized analyst sign-in is required."}, status=403)
    project = get_object_or_404(PilotProject, source_id=request.POST.get("source_id", ""))
    review_status = request.POST.get("review_status")
    notes = request.POST.get("notes", "").strip()
    if review_status not in ("approved", "rejected") or not 10 <= len(notes) <= 4000:
        return JsonResponse({"error": "Choose approve or reject and provide 10-4000 characters of evidence notes."}, status=400)
    if request.POST.get("boundary_sha256") != project.boundary_sha256:
        return JsonResponse({"error": "The boundary changed. Reload the current evidence before reviewing."}, status=409)
    project.review_status = review_status
    project.review_notes = notes
    project.reviewed_by = request.user
    project.reviewed_at = timezone.now()
    try:
        project.full_clean()
    except ValidationError:
        return JsonResponse({"error": "Project evidence did not pass validation."}, status=400)
    project.save(update_fields=["review_status", "review_notes", "reviewed_by", "reviewed_at"])
    return redirect(f"/pilot/?project={project.source_id}")