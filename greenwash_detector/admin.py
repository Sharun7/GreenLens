from django.contrib import admin
from .models import GreenwashFlag


@admin.register(GreenwashFlag)
class GreenwashFlagAdmin(admin.ModelAdmin):
    list_display = ["bond", "claimed_project_type", "satellite_land_use", "ndvi_change", "is_inconsistent", "confidence", "checked_at"]
    list_filter = ["is_inconsistent", "model_version"]
    search_fields = ["bond__bond_id", "bond__issuer_name", "claimed_project_type"]
    ordering = ["-checked_at"]
    readonly_fields = ["checked_at"]
