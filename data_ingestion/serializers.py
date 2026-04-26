"""data_ingestion/serializers.py"""
from rest_framework import serializers
from .models import GreenBond, ClimateHazardData


class LatestPCRScoreSerializer(serializers.Serializer):
    """Minimal PCRScore inline for bond list/detail."""
    score             = serializers.FloatField()
    risk_band         = serializers.CharField()
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

    class Meta:
        model  = GreenBond
        fields = [
            "id", "bond_id", "issuer_name", "country",
            "project_category", "amount_millions", "currency",
            "issuance_date", "bond_maturity_years",
            "lat", "lon",
            "latest_score", "is_mispriced",
        ]

    def get_latest_score(self, obj):
        score_obj = self._latest_pcr(obj)
        if score_obj is None:
            return None
        return {
            "score":               round(score_obj.score, 2),
            "risk_band":           score_obj.risk_band,
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

    @staticmethod
    def _latest_pcr(obj):
        return obj.pcr_scores.order_by("-scored_at").first()


class GreenBondDetailSerializer(serializers.ModelSerializer):
    """Full bond detail with PCRS, pricing gap, and greenwash flag."""
    latest_pcr_score = serializers.SerializerMethodField()
    pricing_gap      = serializers.SerializerMethodField()
    greenwash_flag   = serializers.SerializerMethodField()
    is_mispriced     = serializers.SerializerMethodField()

    class Meta:
        model  = GreenBond
        fields = "__all__"
        extra_fields = [
            "latest_pcr_score", "pricing_gap",
            "greenwash_flag", "is_mispriced",
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
        fields = "__all__"

