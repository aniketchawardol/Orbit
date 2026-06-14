from django.core.files.storage import default_storage
from rest_framework import serializers

from catalog.serializers import ProductSerializer

from .models import Listing, Order, OrderStates


def photo_urls(paths):
    """Relative media paths → URLs that work on local volume AND S3."""
    out = []
    for p in paths or []:
        try:
            out.append(default_storage.url(p))
        except Exception:  # noqa: BLE001 — never let a bad path break a list page
            continue
    return out


class ListingSerializer(serializers.ModelSerializer):
    product = ProductSerializer(source="unit.product", read_only=True)
    unit_id = serializers.IntegerField(source="unit.id", read_only=True)
    grade = serializers.CharField(source="unit.grade", read_only=True)
    untouched = serializers.BooleanField(source="unit.untouched", read_only=True)
    photo_urls = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = [
            "id", "unit_id", "product", "source", "price", "band_lo", "band_hi",
            "state", "photos", "photo_urls", "grade", "untouched", "created_at",
        ]

    def get_photo_urls(self, obj):
        return photo_urls(obj.photos)


class OrderSerializer(serializers.ModelSerializer):
    listing = ListingSerializer(read_only=True)
    photo_urls = serializers.SerializerMethodField()
    return_eligible = serializers.SerializerMethodField()
    return_deadline = serializers.SerializerMethodField()
    prevention_offer = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "listing", "state", "chosen_size", "return_reason", "claimed_untouched",
            "return_comment", "photos", "photo_urls", "delivered_at",
            "return_eligible", "return_deadline", "prevention_offer", "created_at",
        ]

    def get_photo_urls(self, obj):
        return photo_urls(obj.photos)

    def get_return_eligible(self, obj):
        from .returns import is_return_eligible

        return obj.state == OrderStates.DELIVERED and is_return_eligible(obj)

    def get_return_deadline(self, obj):
        from .returns import return_deadline

        return return_deadline(obj)

    def get_prevention_offer(self, obj):
        """Pending keep-it offer for this order, if the rerouting engine made one."""
        from rerouting.services import latest_offer

        offer = latest_offer(obj)
        if not offer:
            return None
        return {
            "id": offer.id,
            "cash_refund": offer.cash_refund,
            "green_credits": offer.green_credits,
            "message": offer.message,
        }
