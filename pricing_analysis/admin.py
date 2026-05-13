# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

from django.contrib import admin
from .models import PricingGap


@admin.register(PricingGap)
class PricingGapAdmin(admin.ModelAdmin):
    list_display = ["bond", "actual_spread_bps", "predicted_spread_bps", "gap_bps", "is_mispriced", "checked_at"]
    list_filter = ["is_mispriced", "data_source"]
    search_fields = ["bond__bond_id", "bond__issuer_name"]
    ordering = ["-checked_at"]
    readonly_fields = ["checked_at", "gap_bps", "is_mispriced"]
