# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

from django.contrib import admin
from .models import ModelFeedback, PCRScore


@admin.register(PCRScore)
class PCRScoreAdmin(admin.ModelAdmin):
    list_display = ["bond", "score", "risk_band", "model_version", "scored_at"]
    list_filter = ["model_version"]
    search_fields = ["bond__bond_id", "bond__issuer_name"]
    ordering = ["-scored_at"]
    readonly_fields = ["scored_at"]

    @admin.display(description="Risk Band")
    def risk_band(self, obj):
        return obj.risk_band


@admin.register(ModelFeedback)
class ModelFeedbackAdmin(admin.ModelAdmin):
    list_display = [
        "bond",
        "decision",
        "outcome",
        "pcr_score_at_decision",
        "pricing_gap_bps_at_decision",
        "review_priority",
        "used_for_retraining",
        "created_at",
    ]
    list_filter = ["decision", "outcome", "used_for_retraining", "created_at"]
    search_fields = ["bond__bond_id", "bond__issuer_name", "notes"]
    readonly_fields = [
        "pcr_score_at_decision",
        "pricing_gap_bps_at_decision",
        "location_confidence_at_decision",
        "created_at",
        "updated_at",
    ]
