# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

from django.contrib import admin
from django.utils import timezone
from .models import GreenBond, ClimateHazardData, PilotProject, PilotOutcome, PilotEvidence, PilotIngestionRun


@admin.register(GreenBond)
class GreenBondAdmin(admin.ModelAdmin):
    list_display = [
        "bond_id", "issuer_name", "country", "project_category",
        "regulatory_framework", "disclosure_quality", "location_confidence",  # Category 19
        "issuance_date", "amount_millions", "currency"
    ]
    list_filter = [
        "project_category", "country", "currency",
        "regulatory_framework", "disclosure_quality", "location_confidence",  # Category 19
    ]
    search_fields = ["bond_id", "issuer_name", "project_description"]
    ordering = ["-issuance_date"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ClimateHazardData)
class ClimateHazardDataAdmin(admin.ModelAdmin):
    list_display = [
        "bond", "flood_risk_index", "heat_stress_index", "drought_spei",
        "monsoon_risk_index", "cyclone_risk_index", "heat_wave_risk_index",  # Category 19
        "source", "data_date"
    ]
    list_filter = ["source", "data_date"]
    search_fields = ["bond__bond_id", "bond__issuer_name"]
    ordering = ["-data_date"]
    readonly_fields = ["created_at"]


class PilotReviewAdmin(admin.ModelAdmin):
    readonly_fields = ["reviewed_by", "reviewed_at"]

    def get_form(self, request, obj=None, **kwargs):
        base_form = super().get_form(request, obj, **kwargs)

        class ReviewForm(base_form):
            def clean(self):
                cleaned = super().clean()
                if cleaned.get("review_status") == "approved" or cleaned.get("independently_observed"):
                    self.instance.reviewed_by = request.user
                    self.instance.reviewed_at = timezone.now()
                return cleaned

        return ReviewForm


@admin.register(PilotProject)
class PilotProjectAdmin(PilotReviewAdmin):
    list_display = ["source_id", "name", "region", "review_status", "reviewed_at"]
    list_filter = ["region", "review_status"]
    search_fields = ["source_id", "name"]
    readonly_fields = PilotReviewAdmin.readonly_fields + [
        "source_id", "name", "country", "region", "category", "boundary", "boundary_sha256",
        "source_url", "source_version", "source_metadata", "imported_at",
    ]

    def has_add_permission(self, request):
        return False


@admin.register(PilotOutcome)
class PilotOutcomeAdmin(PilotReviewAdmin):
    list_display = ["project", "feature_date", "outcome_date", "damage_fraction", "independently_observed", "reviewed_at"]
    list_filter = ["independently_observed", "outcome_date"]
    search_fields = ["project__source_id", "project__name"]


class ReadOnlyPilotAuditAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PilotEvidence)
class PilotEvidenceAdmin(ReadOnlyPilotAuditAdmin):
    list_display = ["project", "status", "recipe_version", "collected_at"]
    list_filter = ["status"]


@admin.register(PilotIngestionRun)
class PilotIngestionRunAdmin(ReadOnlyPilotAuditAdmin):
    list_display = ["started_at", "completed_at", "status"]
    list_filter = ["status"]
