from django.core.files.storage import default_storage
from rest_framework import serializers

from catalog.serializers import ProductSerializer

from .models import Listing, Order


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

    class Meta:
        model = Order
        fields = [
            "id", "listing", "state", "return_reason", "claimed_untouched",
            "photos", "photo_urls", "created_at",
        ]

    def get_photo_urls(self, obj):
        return photo_urls(obj.photos)
