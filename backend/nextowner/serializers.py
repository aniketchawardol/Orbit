"""DRF serializers for the Next Best Owner API: auctions, matches, alerts."""

from rest_framework import serializers

from marketplace.serializers import photo_urls

from .models import MatchEdge, ResaleAuction


class MatchEdgeSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="buyer.username", read_only=True)

    class Meta:
        model = MatchEdge
        fields = [
            "id", "buyer", "username", "score", "components", "tier", "rank",
            "status", "alerted", "price_at_alert", "green_credit_bonus",
        ]


class AuctionSerializer(serializers.ModelSerializer):
    """Compact auction card for the demo grid and detail views."""

    product = serializers.SerializerMethodField()
    photo_urls = serializers.SerializerMethodField()
    grade = serializers.CharField(source="unit.grade", read_only=True)
    seller_name = serializers.CharField(source="seller.username", read_only=True)
    buyer_name = serializers.CharField(source="buyer.username", read_only=True, default=None)
    n_matches = serializers.SerializerMethodField()

    class Meta:
        model = ResaleAuction
        fields = [
            "id", "status", "ceiling", "floor", "current_price", "tier", "max_tier",
            "step_pct", "interval_seconds", "next_step_at", "pricing", "grade",
            "product", "photo_urls", "seller_name", "buyer_name", "n_matches",
            "created_at",
        ]

    def get_product(self, obj):
        p = obj.unit.product
        return {
            "id": p.id,
            "title": p.title,
            "category": p.category,
            "mrp": p.mrp,
            "origin": p.origin,
        }

    def get_photo_urls(self, obj):
        return photo_urls(obj.listing.photos)

    def get_n_matches(self, obj):
        return obj.edges.count()


class AuctionDetailSerializer(AuctionSerializer):
    """Auction card plus its ranked buyer edges (top matches first)."""

    edges = serializers.SerializerMethodField()

    class Meta(AuctionSerializer.Meta):
        fields = AuctionSerializer.Meta.fields + ["edges"]

    def get_edges(self, obj):
        top = obj.edges.all()[: self.context.get("edge_limit", 12)]
        return MatchEdgeSerializer(top, many=True).data
