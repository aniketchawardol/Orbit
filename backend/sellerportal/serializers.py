from rest_framework import serializers

from .models import SellerRule


class SellerRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerRule
        fields = ["id", "min_grade", "min_recovery_pct", "action", "active", "created_at"]
