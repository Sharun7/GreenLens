"""pricing_analysis/serializers.py"""
from rest_framework import serializers
from .models import PricingGap


class PricingGapSerializer(serializers.ModelSerializer):
    bond_id = serializers.CharField(source="bond.bond_id", read_only=True)
    issuer_name = serializers.CharField(source="bond.issuer_name", read_only=True)

    class Meta:
        model = PricingGap
        fields = "__all__"
