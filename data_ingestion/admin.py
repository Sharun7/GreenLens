from django.contrib import admin
from .models import GreenBond, ClimateHazardData


@admin.register(GreenBond)
class GreenBondAdmin(admin.ModelAdmin):
    list_display = ["bond_id", "issuer_name", "country", "project_category", "issuance_date", "amount_millions", "currency"]
    list_filter = ["project_category", "country", "currency"]
    search_fields = ["bond_id", "issuer_name", "project_description"]
    ordering = ["-issuance_date"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ClimateHazardData)
class ClimateHazardDataAdmin(admin.ModelAdmin):
    list_display = ["bond", "flood_risk_index", "heat_stress_index", "drought_spei", "source", "data_date"]
    list_filter = ["source", "data_date"]
    search_fields = ["bond__bond_id", "bond__issuer_name"]
    ordering = ["-data_date"]
    readonly_fields = ["created_at"]
