# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_management/models.py — Risk tracking, failure scenarios, and mitigation

Implements:
- System failure scenarios
- Model drift detection
- Data quality monitoring
- Legal risk tracking
- Incident logging
"""
from django.db import models
from django.utils import timezone
from datetime import timedelta


class SystemFailureScenario(models.Model):
    """
    Track potential system failure scenarios and their mitigation.
    """
    
    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"
    
    class Status(models.TextChoices):
        IDENTIFIED = "identified", "Identified"
        MITIGATING = "mitigating", "Mitigating"
        MITIGATED = "mitigated", "Mitigated"
        MONITORING = "monitoring", "Monitoring"
    
    # Identification
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    scenario_type = models.CharField(
        max_length=50,
        choices=[
            ("api_failure", "API Failure"),
            ("model_drift", "Model Drift"),
            ("data_poisoning", "Data Poisoning"),
            ("infrastructure", "Infrastructure"),
            ("classification_error", "Classification Error"),
        ],
        db_index=True,
    )
    
    # Risk Assessment
    probability = models.CharField(
        max_length=20,
        choices=[
            ("low", "Low (< 10%)"),
            ("medium", "Medium (10-50%)"),
            ("high", "High (50-90%)"),
            ("critical", "Critical (> 90%)"),
        ],
    )
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.HIGH,
    )
    
    # Impact
    impact_description = models.TextField()
    affected_modules = models.JSONField(
        default=list,
        help_text="List of affected modules (e.g., ['greenwash_detector', 'risk_scoring'])",
    )
    
    # Mitigation
    mitigation_strategy = models.TextField()
    mitigation_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IDENTIFIED,
        db_index=True,
    )
    
    # Fallback/Recovery
    has_fallback = models.BooleanField(default=False)
    fallback_description = models.TextField(blank=True)
    recovery_time_minutes = models.IntegerField(
        null=True,
        blank=True,
        help_text="Estimated recovery time in minutes",
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-severity", "-probability"]
        indexes = [
            models.Index(fields=["scenario_type", "mitigation_status"]),
            models.Index(fields=["severity"]),
        ]
        verbose_name = "System Failure Scenario"
        verbose_name_plural = "System Failure Scenarios"
    
    def __str__(self):
        return f"{self.name} ({self.get_severity_display()})"
    
    @property
    def risk_score(self) -> int:
        """Calculate risk score (1-100)."""
        probability_map = {"low": 1, "medium": 5, "high": 8, "critical": 10}
        severity_map = {"low": 1, "medium": 3, "high": 7, "critical": 10}
        
        prob = probability_map.get(self.probability, 5)
        sev = severity_map.get(self.severity, 5)
        
        return min(100, (prob * sev))


class ModelDriftAlert(models.Model):
    """
    Track model performance degradation and drift detection.
    """
    
    class DriftType(models.TextChoices):
        ACCURACY_DROP = "accuracy_drop", "Accuracy Drop"
        PREDICTION_SHIFT = "prediction_shift", "Prediction Shift"
        FEATURE_IMPORTANCE_CHANGE = "feature_change", "Feature Importance Change"
        DISTRIBUTION_SHIFT = "distribution_shift", "Distribution Shift"
    
    # Detection
    model_name = models.CharField(max_length=100, db_index=True)
    drift_type = models.CharField(
        max_length=30,
        choices=DriftType.choices,
        db_index=True,
    )
    
    # Metrics
    previous_accuracy = models.FloatField()
    current_accuracy = models.FloatField()
    accuracy_drop_percentage = models.FloatField()
    
    # Details
    description = models.TextField()
    affected_predictions = models.IntegerField(
        help_text="Number of predictions affected",
    )
    
    # Action
    alert_severity = models.CharField(
        max_length=20,
        choices=[
            ("warning", "Warning"),
            ("alert", "Alert"),
            ("critical", "Critical"),
        ],
        db_index=True,
    )
    action_taken = models.TextField(blank=True)
    retraining_scheduled = models.BooleanField(default=False)
    retraining_date = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-detected_at"]
        indexes = [
            models.Index(fields=["model_name", "detected_at"]),
            models.Index(fields=["alert_severity"]),
        ]
        verbose_name = "Model Drift Alert"
        verbose_name_plural = "Model Drift Alerts"
    
    def __str__(self):
        return f"{self.model_name} - {self.get_drift_type_display()} ({self.accuracy_drop_percentage:.1f}%)"


class ClassificationError(models.Model):
    """
    Track classification errors (wrong PCRS, false greenwash flags, etc.)
    """
    
    class ErrorType(models.TextChoices):
        PCRS_WRONG = "pcrs_wrong", "PCRS Score Wrong"
        GREENWASH_FALSE_POSITIVE = "gw_false_pos", "Greenwash False Positive"
        GREENWASH_FALSE_NEGATIVE = "gw_false_neg", "Greenwash False Negative"
        PRICING_GAP_WRONG = "pricing_wrong", "Pricing Gap Wrong"
    
    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"
    
    # Identification
    bond_id = models.CharField(max_length=100, db_index=True)
    error_type = models.CharField(
        max_length=30,
        choices=ErrorType.choices,
        db_index=True,
    )
    
    # Details
    predicted_value = models.CharField(max_length=255)
    actual_value = models.CharField(max_length=255)
    error_description = models.TextField()
    
    # Impact
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    potential_user_impact = models.TextField()
    
    # Root Cause
    root_cause = models.TextField(blank=True)
    root_cause_category = models.CharField(
        max_length=50,
        choices=[
            ("data_quality", "Data Quality"),
            ("model_limitation", "Model Limitation"),
            ("api_error", "API Error"),
            ("edge_case", "Edge Case"),
            ("unknown", "Unknown"),
        ],
        blank=True,
    )
    
    # Resolution
    is_resolved = models.BooleanField(default=False)
    resolution_action = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    reported_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reported_by = models.CharField(max_length=255, blank=True)
    
    class Meta:
        ordering = ["-reported_at"]
        indexes = [
            models.Index(fields=["error_type", "severity"]),
            models.Index(fields=["is_resolved"]),
        ]
        verbose_name = "Classification Error"
        verbose_name_plural = "Classification Errors"
    
    def __str__(self):
        return f"{self.bond_id} - {self.get_error_type_display()}"


class DataQualityMetric(models.Model):
    """
    Track data quality metrics and anomalies.
    """
    
    # Metric
    metric_name = models.CharField(max_length=100, db_index=True)
    metric_type = models.CharField(
        max_length=50,
        choices=[
            ("completeness", "Completeness"),
            ("accuracy", "Accuracy"),
            ("consistency", "Consistency"),
            ("timeliness", "Timeliness"),
        ],
    )
    
    # Value
    value = models.FloatField()
    threshold_warning = models.FloatField()
    threshold_critical = models.FloatField()
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=[
            ("healthy", "Healthy"),
            ("warning", "Warning"),
            ("critical", "Critical"),
        ],
        db_index=True,
    )
    
    # Details
    description = models.TextField(blank=True)
    affected_records = models.IntegerField(null=True, blank=True)
    
    # Metadata
    measured_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ["-measured_at"]
        indexes = [
            models.Index(fields=["metric_name", "measured_at"]),
            models.Index(fields=["status"]),
        ]
        verbose_name = "Data Quality Metric"
        verbose_name_plural = "Data Quality Metrics"
    
    def __str__(self):
        return f"{self.metric_name}: {self.value:.2f} ({self.get_status_display()})"


class LegalRiskLog(models.Model):
    """
    Track legal risks and compliance issues.
    """
    
    class RiskType(models.TextChoices):
        INVESTMENT_ADVICE = "investment_advice", "Investment Advice Liability"
        DEFAMATION = "defamation", "Defamation / False Greenwash Flag"
        GDPR = "gdpr", "GDPR / Data Privacy"
        REGULATORY = "regulatory", "Regulatory Compliance"
        INTELLECTUAL_PROPERTY = "ip", "Intellectual Property"
    
    class Status(models.TextChoices):
        IDENTIFIED = "identified", "Identified"
        MITIGATING = "mitigating", "Mitigating"
        RESOLVED = "resolved", "Resolved"
        ESCALATED = "escalated", "Escalated to Legal"
    
    # Risk
    risk_type = models.CharField(
        max_length=30,
        choices=RiskType.choices,
        db_index=True,
    )
    description = models.TextField()
    
    # Severity
    severity = models.CharField(
        max_length=20,
        choices=[
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ],
        db_index=True,
    )
    
    # Mitigation
    mitigation_action = models.TextField()
    mitigation_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IDENTIFIED,
    )
    
    # Compliance
    compliance_requirement = models.CharField(max_length=255, blank=True)
    compliance_deadline = models.DateField(null=True, blank=True)
    
    # Metadata
    identified_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    legal_review_required = models.BooleanField(default=False)
    
    class Meta:
        ordering = ["-identified_at"]
        indexes = [
            models.Index(fields=["risk_type", "severity"]),
            models.Index(fields=["mitigation_status"]),
        ]
        verbose_name = "Legal Risk Log"
        verbose_name_plural = "Legal Risk Logs"
    
    def __str__(self):
        return f"{self.get_risk_type_display()} - {self.get_severity_display()}"


class IncidentLog(models.Model):
    """
    Log all system incidents, errors, and recovery actions.
    """
    
    class IncidentType(models.TextChoices):
        API_FAILURE = "api_failure", "API Failure"
        DATABASE_ERROR = "db_error", "Database Error"
        MODEL_ERROR = "model_error", "Model Error"
        DATA_ERROR = "data_error", "Data Error"
        INFRASTRUCTURE = "infrastructure", "Infrastructure"
        SECURITY = "security", "Security"
    
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"
    
    # Incident
    incident_type = models.CharField(
        max_length=30,
        choices=IncidentType.choices,
        db_index=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    
    # Impact
    affected_users = models.IntegerField(default=0)
    affected_bonds = models.IntegerField(default=0)
    downtime_minutes = models.IntegerField(null=True, blank=True)
    
    # Resolution
    root_cause = models.TextField(blank=True)
    resolution_action = models.TextField(blank=True)
    
    # Metadata
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-detected_at"]
        indexes = [
            models.Index(fields=["incident_type", "status"]),
            models.Index(fields=["detected_at"]),
        ]
        verbose_name = "Incident Log"
        verbose_name_plural = "Incident Logs"
    
    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
    
    @property
    def time_to_resolution(self) -> timedelta:
        """Calculate time from detection to resolution."""
        if not self.resolved_at:
            return None
        return self.resolved_at - self.detected_at
