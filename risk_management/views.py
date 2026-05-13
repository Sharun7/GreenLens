# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_management/views.py — API endpoints for risk management dashboard.
"""
import logging
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import (
    SystemFailureScenario,
    ModelDriftAlert,
    ClassificationError,
    DataQualityMetric,
    LegalRiskLog,
    IncidentLog,
)

logger = logging.getLogger("greenlens.risk_management")


@api_view(["GET"])
def risk_dashboard_api(request):
    """
    GET /api/risk-management/dashboard/
    Returns full risk dashboard summary.
    """
    # Open incidents
    open_incidents = IncidentLog.objects.filter(
        status__in=["open", "investigating"]
    ).count()

    # Unresolved classification errors
    unresolved_errors = ClassificationError.objects.filter(
        is_resolved=False
    ).count()

    # Active drift alerts
    active_drift = ModelDriftAlert.objects.filter(
        resolved_at__isnull=True
    ).count()

    # Critical legal risks
    critical_legal = LegalRiskLog.objects.filter(
        severity="critical",
        mitigation_status__in=["identified", "mitigating"],
    ).count()

    # Latest data quality
    latest_quality = DataQualityMetric.objects.order_by("-measured_at").first()

    # Failure scenarios by status
    scenario_counts = SystemFailureScenario.objects.values(
        "mitigation_status"
    ).annotate(count=Count("id"))

    # Recent incidents (last 7 days)
    seven_days_ago = timezone.now() - timedelta(days=7)
    recent_incidents = IncidentLog.objects.filter(
        detected_at__gte=seven_days_ago
    ).values(
        "title", "incident_type", "status", "detected_at"
    ).order_by("-detected_at")[:5]

    return Response({
        "summary": {
            "open_incidents": open_incidents,
            "unresolved_errors": unresolved_errors,
            "active_drift_alerts": active_drift,
            "critical_legal_risks": critical_legal,
            "data_quality_status": latest_quality.status if latest_quality else "unknown",
        },
        "scenario_counts": list(scenario_counts),
        "recent_incidents": list(recent_incidents),
    })


@api_view(["GET"])
def failure_scenarios_api(request):
    """
    GET /api/risk-management/scenarios/
    Returns all system failure scenarios.
    """
    scenarios = SystemFailureScenario.objects.all().values(
        "id", "name", "scenario_type", "probability",
        "severity", "mitigation_status", "has_fallback",
        "recovery_time_minutes", "impact_description",
        "mitigation_strategy",
    )
    return Response({"scenarios": list(scenarios)})


@api_view(["GET"])
def legal_risks_api(request):
    """
    GET /api/risk-management/legal/
    Returns all legal risk logs.
    """
    risks = LegalRiskLog.objects.all().values(
        "id", "risk_type", "description", "severity",
        "mitigation_action", "mitigation_status",
        "compliance_requirement", "compliance_deadline",
        "legal_review_required", "identified_at",
    )
    return Response({"legal_risks": list(risks)})


@api_view(["GET"])
def classification_errors_api(request):
    """
    GET /api/risk-management/errors/
    Returns classification errors (wrong PCRS, false greenwash flags, etc.)
    """
    errors = ClassificationError.objects.all().values(
        "id", "bond_id", "error_type", "severity",
        "predicted_value", "actual_value", "error_description",
        "root_cause_category", "is_resolved", "reported_at",
    ).order_by("-reported_at")[:100]
    return Response({"errors": list(errors)})


@api_view(["GET"])
def drift_alerts_api(request):
    """
    GET /api/risk-management/drift/
    Returns model drift alerts.
    """
    alerts = ModelDriftAlert.objects.all().values(
        "id", "model_name", "drift_type",
        "previous_accuracy", "current_accuracy",
        "accuracy_drop_percentage", "alert_severity",
        "retraining_scheduled", "detected_at",
    ).order_by("-detected_at")[:50]
    return Response({"drift_alerts": list(alerts)})


@api_view(["GET"])
def run_risk_check_api(request):
    """
    GET /api/risk-management/run-check/
    Runs all risk checks and returns results.
    """
    try:
        from .monitoring import run_all_monitors
        results = run_all_monitors()
        return Response({"status": "ok", "results": results})
    except Exception as e:
        logger.error(f"Risk check failed: {e}")
        return Response({"status": "error", "message": str(e)}, status=500)
