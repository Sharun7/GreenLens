from django.contrib import admin
from .models import PCRScore


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
