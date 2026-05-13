# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""greenwash_detector/serializers.py"""
from rest_framework import serializers
from .models import GreenwashFlag


class GreenwashFlagSerializer(serializers.ModelSerializer):
    bond_id = serializers.CharField(source="bond.bond_id", read_only=True)
    issuer_name = serializers.CharField(source="bond.issuer_name", read_only=True)

    class Meta:
        model = GreenwashFlag
        fields = "__all__"
