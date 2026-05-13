# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

from django.contrib import admin
from .models import GreenBond, ClimateHazardData


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
