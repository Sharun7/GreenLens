# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_management/admin.py — Django admin interface for risk management models.

Provides:
- System failure scenario tracking
- Model drift alerts
- Classification error logging
- Data quality metrics
- Legal risk logs
- Incident logs
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    SystemFailureScenario,
    ModelDriftAlert,
    ClassificationError,
    DataQualityMetric,
    LegalRiskLog,
    IncidentLog,
)


@admin.register(SystemFailureScenario)
class SystemFailureScenarioAdmin(admin.ModelAdmin):
    """Admin interface for system failure scenarios."""
    
    list_display = [
        "name",
        "scenario_type_badge",
        "probability_badge",
        "severity_badge",
        "mitigation_status_badge",
        "risk_score_display",
    ]
    list_filter = [
        "scenario_type",
        "probability",
        "severity",
        "mitigation_status",
        "created_at",
    ]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at", "risk_score_display"]
    
    fieldsets = (
        ("Identification", {
            "fields": ("name", "description", "scenario_type"),
        }),
        ("Risk Assessment", {
            "fields": ("probability", "severity", "risk_score_display"),
        }),
        ("Impact", {
            "fields": ("impact_description", "affected_modules"),
        }),
        ("Mitigation", {
            "fields": ("mitigation_strategy", "mitigation_status"),
        }),
        ("Fallback & Recovery", {
            "fields": ("has_fallback", "fallback_description", "recovery_time_minutes"),
            "classes": ("collapse",),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at", "last_reviewed_at"),
            "classes": ("collapse",),
        }),
    )
    
    def scenario_type_badge(self, obj):
        """Display scenario type as badge."""
        colors = {
            "api_failure": "#FF6B6B",
            "model_drift": "#FFA500",
            "data_poisoning": "#DC143C",
            "infrastructure": "#4169E1",
            "classification_error": "#9370DB",
        }
        color = colors.get(obj.scenario_type, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_scenario_type_display(),
        )
    scenario_type_badge.short_description = "Type"
    
    def probability_badge(self, obj):
        """Display probability as badge."""
        colors = {
            "low": "#90EE90",
            "medium": "#FFD700",
            "high": "#FFA500",
            "critical": "#FF4500",
        }
        color = colors.get(obj.probability, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_probability_display(),
        )
    probability_badge.short_description = "Probability"
    
    def severity_badge(self, obj):
        """Display severity as badge."""
        colors = {
            "low": "#90EE90",
            "medium": "#FFD700",
            "high": "#FFA500",
            "critical": "#FF4500",
        }
        color = colors.get(obj.severity, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_severity_display(),
        )
    severity_badge.short_description = "Severity"
    
    def mitigation_status_badge(self, obj):
        """Display mitigation status as badge."""
        colors = {
            "identified": "#FF6B6B",
            "mitigating": "#FFA500",
            "mitigated": "#90EE90",
            "monitoring": "#4169E1",
        }
        color = colors.get(obj.mitigation_status, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_mitigation_status_display(),
        )
    mitigation_status_badge.short_description = "Status"
    
    def risk_score_display(self, obj):
        """Display risk score with color coding."""
        score = obj.risk_score
        if score >= 70:
            color = "#FF4500"
        elif score >= 40:
            color = "#FFA500"
        else:
            color = "#90EE90"
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 10px; '
            'border-radius: 3px; font-weight: bold; font-size: 14px;">{}/100</span>',
            color,
            score,
        )
    risk_score_display.short_description = "Risk Score"


@admin.register(ModelDriftAlert)
class ModelDriftAlertAdmin(admin.ModelAdmin):
    """Admin interface for model drift alerts."""
    
    list_display = [
        "model_name",
        "drift_type_badge",
        "accuracy_drop_display",
        "alert_severity_badge",
        "detected_at",
    ]
    list_filter = [
        "model_name",
        "drift_type",
        "alert_severity",
        "detected_at",
        "retraining_scheduled",
    ]
    search_fields = ["model_name", "description"]
    readonly_fields = ["detected_at", "accuracy_drop_percentage"]
    
    fieldsets = (
        ("Detection", {
            "fields": ("model_name", "drift_type", "description"),
        }),
        ("Metrics", {
            "fields": ("previous_accuracy", "current_accuracy", "accuracy_drop_percentage", "affected_predictions"),
        }),
        ("Action", {
            "fields": ("alert_severity", "action_taken", "retraining_scheduled", "retraining_date"),
        }),
        ("Metadata", {
            "fields": ("detected_at", "resolved_at"),
            "classes": ("collapse",),
        }),
    )
    
    def drift_type_badge(self, obj):
        """Display drift type as badge."""
        colors = {
            "accuracy_drop": "#FF6B6B",
            "prediction_shift": "#FFA500",
            "feature_change": "#9370DB",
            "distribution_shift": "#4169E1",
        }
        color = colors.get(obj.drift_type, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_drift_type_display(),
        )
    drift_type_badge.short_description = "Drift Type"
    
    def accuracy_drop_display(self, obj):
        """Display accuracy drop with color coding."""
        if obj.accuracy_drop_percentage >= 10:
            color = "#FF4500"
        elif obj.accuracy_drop_percentage >= 5:
            color = "#FFA500"
        else:
            color = "#90EE90"
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{:.1f}%</span>',
            color,
            obj.accuracy_drop_percentage,
        )
    accuracy_drop_display.short_description = "Accuracy Drop"
    
    def alert_severity_badge(self, obj):
        """Display alert severity as badge."""
        colors = {
            "warning": "#FFD700",
            "alert": "#FFA500",
            "critical": "#FF4500",
        }
        color = colors.get(obj.alert_severity, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_alert_severity_display(),
        )
    alert_severity_badge.short_description = "Severity"


@admin.register(ClassificationError)
class ClassificationErrorAdmin(admin.ModelAdmin):
    """Admin interface for classification errors."""
    
    list_display = [
        "bond_id",
        "error_type_badge",
        "severity_badge",
        "is_resolved_badge",
        "reported_at",
    ]
    list_filter = [
        "error_type",
        "severity",
        "is_resolved",
        "root_cause_category",
        "reported_at",
    ]
    search_fields = ["bond_id", "error_description"]
    readonly_fields = ["reported_at"]
    
    fieldsets = (
        ("Identification", {
            "fields": ("bond_id", "error_type", "error_description"),
        }),
        ("Details", {
            "fields": ("predicted_value", "actual_value"),
        }),
        ("Impact", {
            "fields": ("severity", "potential_user_impact"),
        }),
        ("Root Cause", {
            "fields": ("root_cause", "root_cause_category"),
        }),
        ("Resolution", {
            "fields": ("is_resolved", "resolution_action", "resolved_at"),
        }),
        ("Metadata", {
            "fields": ("reported_at", "reported_by"),
            "classes": ("collapse",),
        }),
    )
    
    def error_type_badge(self, obj):
        """Display error type as badge."""
        colors = {
            "pcrs_wrong": "#FF6B6B",
            "gw_false_pos": "#DC143C",
            "gw_false_neg": "#FFA500",
            "pricing_wrong": "#9370DB",
        }
        color = colors.get(obj.error_type, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_error_type_display(),
        )
    error_type_badge.short_description = "Error Type"
    
    def severity_badge(self, obj):
        """Display severity as badge."""
        colors = {
            "low": "#90EE90",
            "medium": "#FFD700",
            "high": "#FFA500",
            "critical": "#FF4500",
        }
        color = colors.get(obj.severity, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_severity_display(),
        )
    severity_badge.short_description = "Severity"
    
    def is_resolved_badge(self, obj):
        """Display resolution status as badge."""
        color = "#90EE90" if obj.is_resolved else "#FF6B6B"
        status = "✓ Resolved" if obj.is_resolved else "✗ Open"
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            status,
        )
    is_resolved_badge.short_description = "Status"


@admin.register(DataQualityMetric)
class DataQualityMetricAdmin(admin.ModelAdmin):
    """Admin interface for data quality metrics."""
    
    list_display = [
        "metric_name",
        "metric_type",
        "value_display",
        "status_badge",
        "measured_at",
    ]
    list_filter = [
        "metric_type",
        "status",
        "measured_at",
    ]
    search_fields = ["metric_name", "description"]
    readonly_fields = ["measured_at"]
    
    fieldsets = (
        ("Metric", {
            "fields": ("metric_name", "metric_type", "description"),
        }),
        ("Value", {
            "fields": ("value", "threshold_warning", "threshold_critical"),
        }),
        ("Status", {
            "fields": ("status", "affected_records"),
        }),
        ("Metadata", {
            "fields": ("measured_at",),
            "classes": ("collapse",),
        }),
    )
    
    def value_display(self, obj):
        """Display metric value with color coding."""
        if obj.status == "healthy":
            color = "#90EE90"
        elif obj.status == "warning":
            color = "#FFD700"
        else:
            color = "#FF4500"
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{:.2f}</span>',
            color,
            obj.value,
        )
    value_display.short_description = "Value"
    
    def status_badge(self, obj):
        """Display status as badge."""
        colors = {
            "healthy": "#90EE90",
            "warning": "#FFD700",
            "critical": "#FF4500",
        }
        color = colors.get(obj.status, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )
    status_badge.short_description = "Status"


@admin.register(LegalRiskLog)
class LegalRiskLogAdmin(admin.ModelAdmin):
    """Admin interface for legal risk logs."""
    
    list_display = [
        "risk_type_badge",
        "severity_badge",
        "mitigation_status_badge",
        "legal_review_required_badge",
        "identified_at",
    ]
    list_filter = [
        "risk_type",
        "severity",
        "mitigation_status",
        "legal_review_required",
        "identified_at",
    ]
    search_fields = ["description", "mitigation_action"]
    readonly_fields = ["identified_at"]
    
    fieldsets = (
        ("Risk", {
            "fields": ("risk_type", "description", "severity"),
        }),
        ("Mitigation", {
            "fields": ("mitigation_action", "mitigation_status"),
        }),
        ("Compliance", {
            "fields": ("compliance_requirement", "compliance_deadline"),
        }),
        ("Legal Review", {
            "fields": ("legal_review_required",),
        }),
        ("Metadata", {
            "fields": ("identified_at", "resolved_at"),
            "classes": ("collapse",),
        }),
    )
    
    def risk_type_badge(self, obj):
        """Display risk type as badge."""
        colors = {
            "investment_advice": "#FF6B6B",
            "defamation": "#DC143C",
            "gdpr": "#FFA500",
            "regulatory": "#9370DB",
            "ip": "#4169E1",
        }
        color = colors.get(obj.risk_type, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_risk_type_display(),
        )
    risk_type_badge.short_description = "Risk Type"
    
    def severity_badge(self, obj):
        """Display severity as badge."""
        colors = {
            "low": "#90EE90",
            "medium": "#FFD700",
            "high": "#FFA500",
            "critical": "#FF4500",
        }
        color = colors.get(obj.severity, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_severity_display(),
        )
    severity_badge.short_description = "Severity"
    
    def mitigation_status_badge(self, obj):
        """Display mitigation status as badge."""
        colors = {
            "identified": "#FF6B6B",
            "mitigating": "#FFA500",
            "resolved": "#90EE90",
            "escalated": "#9370DB",
        }
        color = colors.get(obj.mitigation_status, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_mitigation_status_display(),
        )
    mitigation_status_badge.short_description = "Status"
    
    def legal_review_required_badge(self, obj):
        """Display legal review requirement as badge."""
        if obj.legal_review_required:
            return format_html(
                '<span style="background-color: #FF4500; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-weight: bold;">⚠ Required</span>'
            )
        return format_html(
            '<span style="background-color: #90EE90; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">✓ Not Required</span>'
        )
    legal_review_required_badge.short_description = "Legal Review"


@admin.register(IncidentLog)
class IncidentLogAdmin(admin.ModelAdmin):
    """Admin interface for incident logs."""
    
    list_display = [
        "title",
        "incident_type_badge",
        "status_badge",
        "affected_users_display",
        "detected_at",
    ]
    list_filter = [
        "incident_type",
        "status",
        "detected_at",
    ]
    search_fields = ["title", "description", "root_cause"]
    readonly_fields = ["detected_at", "time_to_resolution_display"]
    
    fieldsets = (
        ("Incident", {
            "fields": ("title", "incident_type", "description"),
        }),
        ("Status", {
            "fields": ("status",),
        }),
        ("Impact", {
            "fields": ("affected_users", "affected_bonds", "downtime_minutes"),
        }),
        ("Resolution", {
            "fields": ("root_cause", "resolution_action", "time_to_resolution_display"),
        }),
        ("Metadata", {
            "fields": ("detected_at", "resolved_at"),
            "classes": ("collapse",),
        }),
    )
    
    def incident_type_badge(self, obj):
        """Display incident type as badge."""
        colors = {
            "api_failure": "#FF6B6B",
            "db_error": "#DC143C",
            "model_error": "#FFA500",
            "data_error": "#9370DB",
            "infrastructure": "#4169E1",
            "security": "#FF4500",
        }
        color = colors.get(obj.incident_type, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_incident_type_display(),
        )
    incident_type_badge.short_description = "Type"
    
    def status_badge(self, obj):
        """Display status as badge."""
        colors = {
            "open": "#FF6B6B",
            "investigating": "#FFA500",
            "resolved": "#90EE90",
            "closed": "#4169E1",
        }
        color = colors.get(obj.status, "#808080")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )
    status_badge.short_description = "Status"
    
    def affected_users_display(self, obj):
        """Display affected users count."""
        if obj.affected_users == 0:
            return "—"
        return f"{obj.affected_users} users"
    affected_users_display.short_description = "Affected Users"
    
    def time_to_resolution_display(self, obj):
        """Display time to resolution."""
        if not obj.time_to_resolution:
            return "—"
        hours = obj.time_to_resolution.total_seconds() / 3600
        return f"{hours:.1f} hours"
    time_to_resolution_display.short_description = "Time to Resolution"
