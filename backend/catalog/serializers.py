from rest_framework import serializers

from .models import ItemUnit, Product, UnitEvent


class ProductSerializer(serializers.ModelSerializer):
    seller_name = serializers.CharField(source="seller.username", read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "title", "description", "category", "mrp",
            "image_url", "seller_name", "created_at",
        ]

    def get_image_url(self, obj):
        return obj.image.url if obj.image else None


class UnitEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = UnitEvent
        fields = ["id", "type", "payload", "actor_name", "created_at"]


class ItemUnitSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    events = UnitEventSerializer(many=True, read_only=True)

    class Meta:
        model = ItemUnit
        fields = [
            "id", "product", "state", "grade", "grade_confidence", "untouched",
            "est_value", "arrived_at_facility", "storage_cost_accrued",
            "events", "created_at",
        ]
