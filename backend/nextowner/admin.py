from django.contrib import admin

from .models import DemandProfile, MatchEdge, ProductVector, ResaleAuction


@admin.register(ResaleAuction)
class ResaleAuctionAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "current_price", "ceiling", "floor", "tier", "seller")
    list_filter = ("status",)


@admin.register(MatchEdge)
class MatchEdgeAdmin(admin.ModelAdmin):
    list_display = ("id", "auction", "buyer", "score", "tier", "rank", "status", "alerted")
    list_filter = ("status", "tier", "alerted")


@admin.register(DemandProfile)
class DemandProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "n_orders", "price_mean", "green_propensity", "provider")


@admin.register(ProductVector)
class ProductVectorAdmin(admin.ModelAdmin):
    list_display = ("product", "dim", "provider", "updated_at")
