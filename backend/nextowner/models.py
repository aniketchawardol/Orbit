"""Data model for the Next Best Owner P2P resale engine.

Four durable models:
- DemandProfile : a buyer's learned "what I want" vector plus affinity / budget /
                  green-buying signals, recomputed from their order + credit history.
- ProductVector : a product's cached text embedding (so matching never re-embeds).
- ResaleAuction : a descending-price (Dutch) auction over one resale Listing.
- MatchEdge     : one scored buyer <-> auction match, tiered and tracked from
                  alert -> view -> purchase.

Vectors are stored as plain JSON lists (portable, no pgvector dependency). A
brute-force cosine over same-locality candidates is fine at MVP scale; the scale
path (pgvector/ANN, Redis cache, beat precompute) is noted in settings.
"""

from django.conf import settings
from django.db import models

from catalog.models import ItemUnit, Product
from core.models import TimeStamped
from marketplace.models import Listing


class DemandProfile(TimeStamped):
    """A buyer's demand snapshot in the same embedding space as products, so a
    product<->buyer cosine is meaningful. Recomputed from history; cached here."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="demand_profile"
    )
    # Recency-weighted average of the embeddings of products the user bought
    # ("taste"). Empty for cold-start users (matching treats that as neutral).
    taste_vector = models.JSONField(default=list, blank=True)
    dim = models.PositiveIntegerField(default=0)
    # Normalized {category: weight} and {brand: weight} histograms.
    category_affinity = models.JSONField(default=dict, blank=True)
    brand_affinity = models.JSONField(default=dict, blank=True)
    # Budget: mean / std of prices the user has paid (₹).
    price_mean = models.FloatField(default=0.0)
    price_std = models.FloatField(default=0.0)
    # 0..1 propensity to buy resold / pre-loved goods (from credit + resale history).
    green_propensity = models.FloatField(default=0.0)
    n_orders = models.PositiveIntegerField(default=0)
    provider = models.CharField(max_length=20, blank=True)  # embedder that built it

    def __str__(self):
        return f"DemandProfile<{self.user_id}> n={self.n_orders}"


class ProductVector(TimeStamped):
    """Cached text embedding for a product, so the matcher never re-embeds in the
    request path. Rebuilt when the catalog text changes."""

    product = models.OneToOneField(
        Product, on_delete=models.CASCADE, related_name="vector"
    )
    text_vector = models.JSONField(default=list, blank=True)
    dim = models.PositiveIntegerField(default=0)
    provider = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"ProductVector<{self.product_id}> dim={self.dim}"


class ResaleStatus(models.TextChoices):
    PENDING = "PENDING", "Pending grading"
    PRICED = "PRICED", "Priced & listed"
    FAILED = "FAILED", "Failed"


class ResaleRequest(TimeStamped):
    """A buyer's request to resell one item. Captures the pricing inputs the async
    grader can't derive (declared original price, item age) and links the
    resulting assessment -> listing -> auction once pricing completes. Created
    PENDING; the grading handoff finds the PENDING request for the unit, prices
    it, and flips it to PRICED."""

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="resale_requests"
    )
    unit = models.ForeignKey(
        ItemUnit, on_delete=models.CASCADE, related_name="resale_requests"
    )
    photos = models.JSONField(default=list, blank=True)
    original_price = models.PositiveIntegerField()  # ₹ paid (linked) or declared (external)
    age_months = models.FloatField(default=0.0)
    linked = models.BooleanField(default=True)  # bought on platform (has a reference image)
    assessment = models.ForeignKey(
        "grading.GradingAssessment",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="resale_requests",
    )
    listing = models.ForeignKey(
        Listing,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="resale_requests",
    )
    status = models.CharField(
        max_length=10, choices=ResaleStatus.choices, default=ResaleStatus.PENDING
    )

    class Meta:
        indexes = [
            models.Index(fields=["unit", "status"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"ResaleRequest<{self.pk}> unit={self.unit_id} {self.status}"


class AuctionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACTIVE = "ACTIVE", "Active"
    SOLD = "SOLD", "Sold"
    EXPIRED = "EXPIRED", "Expired"


class ResaleAuction(TimeStamped):
    """A descending-price auction over one resale listing. The price starts at
    `ceiling`, steps down by `step_pct` every `interval_seconds`, and each step
    widens the alert to one more tier of matched buyers — until someone buys or
    the `floor` (reserve) / `max_tier` is reached."""

    listing = models.OneToOneField(
        Listing, on_delete=models.CASCADE, related_name="auction"
    )
    unit = models.ForeignKey(ItemUnit, on_delete=models.CASCADE, related_name="auctions")
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="resale_auctions"
    )
    ceiling = models.PositiveIntegerField()
    floor = models.PositiveIntegerField()  # = reserve; the auction never sells below this
    current_price = models.PositiveIntegerField()
    step_pct = models.FloatField()
    interval_seconds = models.PositiveIntegerField()
    tier = models.PositiveIntegerField(default=0)  # how many tiers have been alerted
    max_tier = models.PositiveIntegerField()
    status = models.CharField(
        max_length=10, choices=AuctionStatus.choices, default=AuctionStatus.PENDING
    )
    next_step_at = models.DateTimeField(blank=True, null=True)
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="won_auctions",
    )
    # Snapshot of grade / quality / fraud / inputs that priced it (display + audit).
    pricing = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "next_step_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"ResaleAuction<{self.pk}> {self.status} ₹{self.current_price} tier={self.tier}"


class MatchStatus(models.TextChoices):
    SENT = "SENT", "Alert sent"
    VIEWED = "VIEWED", "Viewed"
    PURCHASED = "PURCHASED", "Purchased"
    EXPIRED = "EXPIRED", "Expired"


class MatchEdge(TimeStamped):
    """One scored buyer <-> auction match. Persisted so the bipartite graph, the
    tiered alert rollout, and the demo view are all reproducible."""

    auction = models.ForeignKey(
        ResaleAuction, on_delete=models.CASCADE, related_name="edges"
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="resale_matches"
    )
    score = models.FloatField()
    components = models.JSONField(default=dict, blank=True)  # per-term breakdown
    tier = models.PositiveIntegerField(default=0)  # 0 = best fit; alerted first
    rank = models.PositiveIntegerField(default=0)  # global rank within the auction
    status = models.CharField(
        max_length=10, choices=MatchStatus.choices, default=MatchStatus.SENT
    )
    alerted = models.BooleanField(default=False)
    price_at_alert = models.PositiveIntegerField(blank=True, null=True)
    green_credit_bonus = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["auction", "buyer"], name="uniq_auction_buyer")
        ]
        indexes = [
            models.Index(fields=["auction", "tier"]),
            models.Index(fields=["buyer", "status"]),
        ]
        ordering = ["auction_id", "rank"]

    def __str__(self):
        return f"MatchEdge a={self.auction_id} b={self.buyer_id} score={self.score:.3f}"
