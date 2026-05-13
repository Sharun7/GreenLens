# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""data_ingestion/serializers.py"""
from rest_framework import serializers
from .models import GreenBond, ClimateHazardData
from .reliability import build_bond_reliability
from risk_scoring.explainability import build_bond_model_depth, build_prediction_explanation


class LatestPCRScoreSerializer(serializers.Serializer):
    """Minimal PCRScore inline for bond list/detail."""
    score             = serializers.FloatField()
    risk_band         = serializers.CharField()
    risk_label        = serializers.CharField()
    confidence_interval = serializers.DictField()
    flood_contribution  = serializers.FloatField()
    heat_contribution   = serializers.FloatField()
    drought_contribution = serializers.FloatField()
    model_version     = serializers.CharField()
    scored_at         = serializers.DateTimeField()
    shap_values       = serializers.DictField(child=serializers.FloatField())


class GreenBondListSerializer(serializers.ModelSerializer):
    """Compact serializer for the bond list endpoint."""
    latest_score  = serializers.SerializerMethodField()
    is_mispriced  = serializers.SerializerMethodField()
    data_reliability_score = serializers.SerializerMethodField()
    data_reliability_label = serializers.SerializerMethodField()

    class Meta:
        model  = GreenBond
        fields = [
            "id", "bond_id", "issuer_name", "country",
            "project_category", "amount_millions", "currency",
            "issuance_date", "bond_maturity_years",
            "lat", "lon", "location_confidence",
            "regulatory_framework", "disclosure_quality",  # Category 19
            "latest_score", "is_mispriced",
            "data_reliability_score", "data_reliability_label",
        ]

    def get_latest_score(self, obj):
        score_obj = self._latest_pcr(obj)
        if score_obj is None:
            return None
        return {
            "score":               round(score_obj.score, 2),
            "risk_band":           score_obj.risk_band,
            "risk_label":          score_obj.three_band_label,
            "confidence_interval": score_obj.confidence_interval,
            "main_risk_driver":    score_obj.main_risk_driver,
            "why_risky":           build_prediction_explanation(obj, score_obj).get("popup"),
            "model_version":       score_obj.model_version,
            "scored_at":           score_obj.scored_at,
        }

    def get_is_mispriced(self, obj):
        from pricing_analysis.models import PricingGap
        gap = PricingGap.objects.filter(bond=obj).order_by("-calculation_date").first()
        if gap is None:
            return None
        diff = (gap.actual_spread_bps or 0) - (gap.predicted_spread_bps or 0)
        return abs(diff) > 50      # 50 bps threshold

    def get_data_reliability_score(self, obj):
        return self._reliability(obj)["overall_score"]

    def get_data_reliability_label(self, obj):
        return self._reliability(obj)["overall_label"]

    @staticmethod
    def _latest_pcr(obj):
        return obj.pcr_scores.order_by("-scored_at").first()

    def _reliability(self, obj):
        cache = getattr(self, "_reliability_cache", {})
        if obj.pk not in cache:
            cache[obj.pk] = build_bond_reliability(obj)
            self._reliability_cache = cache
        return cache[obj.pk]


class GreenBondDetailSerializer(serializers.ModelSerializer):
    """Full bond detail with PCRS, pricing gap, and greenwash flag."""
    latest_pcr_score = serializers.SerializerMethodField()
    pricing_gap      = serializers.SerializerMethodField()
    greenwash_flag   = serializers.SerializerMethodField()
    is_mispriced     = serializers.SerializerMethodField()
    data_reliability = serializers.SerializerMethodField()
    model_depth      = serializers.SerializerMethodField()

    class Meta:
        model  = GreenBond
        fields = "__all__"
        extra_fields = [
            "latest_pcr_score", "pricing_gap",
            "greenwash_flag", "is_mispriced", "data_reliability",
            "model_depth",
        ]

    def get_fields(self):
        fields = super().get_fields()
        for f in self.Meta.extra_fields:
            fields[f] = getattr(self, f"_{f}_field")() if False else serializers.SerializerMethodField()
        return fields

    def get_latest_pcr_score(self, obj):
        score_obj = obj.pcr_scores.order_by("-scored_at").first()
        if score_obj is None:
            return None
        return {
            "score":                round(score_obj.score, 2),
            "risk_band":            score_obj.risk_band,
            "risk_label":           score_obj.three_band_label,
            "confidence_interval":  score_obj.confidence_interval,
            "main_risk_driver":     score_obj.main_risk_driver,
            "why_risky":            build_prediction_explanation(obj, score_obj).get("detail_summary"),
            "flood_contribution":   round(score_obj.flood_contribution, 4),
            "heat_contribution":    round(score_obj.heat_contribution, 4),
            "drought_contribution": round(score_obj.drought_contribution, 4),
            "model_version":        score_obj.model_version,
            "scored_at":            score_obj.scored_at,
            "shap_values":          score_obj.shap_values,
        }

    def get_pricing_gap(self, obj):
        from pricing_analysis.models import PricingGap
        gap = PricingGap.objects.filter(bond=obj).order_by("-calculation_date").first()
        if gap is None:
            return None
        return {
            "actual_spread_bps":    gap.actual_spread_bps,
            "predicted_spread_bps": gap.predicted_spread_bps,
            "gap_bps":              round((gap.actual_spread_bps or 0) - (gap.predicted_spread_bps or 0), 2),
            "is_live":              gap.is_live,
            "calculation_date":     gap.calculation_date,
        }

    def get_greenwash_flag(self, obj):
        from greenwash_detector.models import GreenwashFlag
        flag = GreenwashFlag.objects.filter(bond=obj).order_by("-checked_at").first()
        if flag is None:
            return None
        return {
            "is_inconsistent":       flag.is_inconsistent,
            "confidence":            flag.confidence,
            "detection_date":        flag.checked_at,
            "claimed_project_type":  flag.claimed_project_type,
            "satellite_land_use":    flag.satellite_land_use,
            "ndvi_change":           flag.ndvi_change,
        }

    def get_is_mispriced(self, obj):
        from pricing_analysis.models import PricingGap
        gap = PricingGap.objects.filter(bond=obj).order_by("-calculation_date").first()
        if gap is None:
            return None
        diff = (gap.actual_spread_bps or 0) - (gap.predicted_spread_bps or 0)
        return abs(diff) > 50

    def get_data_reliability(self, obj):
        return build_bond_reliability(obj)

    def get_model_depth(self, obj):
        return build_bond_model_depth(obj)


class GreenBondSerializer(GreenBondListSerializer):
    """Alias kept for backwards compatibility (ClimateHazardData views etc.)."""
    class Meta(GreenBondListSerializer.Meta):
        fields = "__all__"
        extra_fields = []

    def get_latest_score(self, obj):  # noqa: F811
        return super().get_latest_score(obj)

    def get_is_mispriced(self, obj):  # noqa: F811
        return super().get_is_mispriced(obj)


class ClimateHazardDataSerializer(serializers.ModelSerializer):
    bond_id = serializers.CharField(source="bond.bond_id", read_only=True)

    class Meta:
        model  = ClimateHazardData
        fields = [
            "id", "bond", "bond_id",
            "flood_risk_index", "heat_stress_index", "drought_spei",
            "carbon_intensity_score", "policy_risk_score", "transition_risk_score",
            "monsoon_risk_index", "cyclone_risk_index", "heat_wave_risk_index",  # Category 19
            "data_date", "source", "raw_metadata", "created_at",
        ]

