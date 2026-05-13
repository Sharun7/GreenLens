# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""risk_scoring/serializers.py"""
from rest_framework import serializers
from data_ingestion.models import GreenBond

from .explainability import build_prediction_explanation, build_shap_factor_table
from .models import ModelFeedback, PCRScore


class PCRScoreSerializer(serializers.ModelSerializer):
    bond_id    = serializers.CharField(source="bond.bond_id", read_only=True)
    issuer_name = serializers.CharField(source="bond.issuer_name", read_only=True)
    risk_band  = serializers.CharField(read_only=True)
    risk_label = serializers.CharField(source="three_band_label", read_only=True)
    confidence_interval = serializers.DictField(read_only=True)
    main_risk_driver = serializers.DictField(read_only=True)
    why_risky = serializers.SerializerMethodField()
    shap_factors = serializers.SerializerMethodField()

    class Meta:
        model  = PCRScore
        fields = [
            "id", "bond_id", "issuer_name", "score", "risk_band",
            "risk_label", "confidence_interval", "main_risk_driver",
            "why_risky", "shap_factors",
            "flood_contribution", "heat_contribution", "drought_contribution",
            "model_version", "scored_at", "shap_values",
        ]

    def get_why_risky(self, obj):
        return build_prediction_explanation(obj.bond, obj).get("popup")

    def get_shap_factors(self, obj):
        return build_shap_factor_table(obj)


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


class ModelFeedbackSerializer(serializers.ModelSerializer):
    bond_id = serializers.CharField(source="bond.bond_id", read_only=True)
    issuer_name = serializers.CharField(source="bond.issuer_name", read_only=True)
    bond_pk = serializers.PrimaryKeyRelatedField(
        queryset=GreenBond.objects.all(),
        source="bond",
        write_only=True,
        required=True,
    )
    review_priority = serializers.CharField(read_only=True)
    is_adverse_outcome = serializers.BooleanField(read_only=True)

    class Meta:
        model = ModelFeedback
        fields = [
            "id",
            "bond_pk",
            "bond_id",
            "issuer_name",
            "decision",
            "outcome",
            "pcr_score_at_decision",
            "pricing_gap_bps_at_decision",
            "location_confidence_at_decision",
            "realized_loss_bps",
            "outcome_date",
            "notes",
            "used_for_retraining",
            "is_adverse_outcome",
            "review_priority",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "pcr_score_at_decision",
            "pricing_gap_bps_at_decision",
            "location_confidence_at_decision",
            "used_for_retraining",
            "created_at",
            "updated_at",
        ]

