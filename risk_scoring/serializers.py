"""risk_scoring/serializers.py"""
from rest_framework import serializers
from .models import PCRScore


class PCRScoreSerializer(serializers.ModelSerializer):
    bond_id    = serializers.CharField(source="bond.bond_id", read_only=True)
    issuer_name = serializers.CharField(source="bond.issuer_name", read_only=True)
    risk_band  = serializers.CharField(read_only=True)

    class Meta:
        model  = PCRScore
        fields = [
            "id", "bond_id", "issuer_name", "score", "risk_band",
            "flood_contribution", "heat_contribution", "drought_contribution",
            "model_version", "scored_at", "shap_values",
        ]


class PCRScoreDetailSerializer(PCRScoreSerializer):
    """Extended serializer with full SHAP breakdown — for bond detail view."""
    class Meta(PCRScoreSerializer.Meta):
        fields = PCRScoreSerializer.Meta.fields  # same fields, already includes shap_values


class ScoreDistributionSerializer(serializers.Serializer):
    bins   = serializers.ListField(child=serializers.FloatField())
    counts = serializers.ListField(child=serializers.IntegerField())
    total  = serializers.IntegerField()
    mean   = serializers.FloatField()
    median = serializers.FloatField()

