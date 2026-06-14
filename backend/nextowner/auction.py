"""Dutch-auction core for the Next Best Owner engine.

Pure domain logic (no Celery imports) so it runs identically inline (eager/tests)
or under the worker; `tasks.py` adds the scheduling layer on top. Flow:

    grading verdict ->  price_resale()  ->  Listing (USER_RESALE)
                    ->  match buyers (bipartite) -> persist MatchEdges
                    ->  alert tier 0  ->  [step() lowers price + widens tiers]*
                    ->  buy() finalizes the sale + green credits + payout

The price starts at the band ceiling and steps down toward the floor (reserve);
each drop both alerts one more tier of buyers AND raises the green-credit bonus,
so hesitant buyers are nudged exactly when the deal gets better.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import UnitEvent, UnitStates
from greencredits.logic import award_credits
from marketplace.models import (
    Listing,
    ListingSources,
    ListingStates,
    Order,
)

from . import matching, pricing
from .models import (
    AuctionStatus,
    MatchEdge,
    MatchStatus,
    ResaleAuction,
    ResaleRequest,
    ResaleStatus,
)

log = logging.getLogger(__name__)


def credit_bonus_at(auction, price) -> int:
    """Green-credit bonus offered at a given price: 0 at the ceiling, growing to
    NEXTOWNER_CREDIT_MAX_BONUS at the floor. The cheaper it gets, the bigger the
    sustainability reward — the gamified nudge."""
    ceiling, floor = auction.ceiling, auction.floor
    drop = 0.0 if ceiling <= floor else (ceiling - price) / (ceiling - floor)
    drop = max(0.0, min(1.0, drop))
    return int(round(drop * settings.NEXTOWNER_CREDIT_MAX_BONUS))


def _persist_edges(auction, ranked) -> None:
    """Bulk-insert the ranked buyer matches for an auction."""
    edges = [
        MatchEdge(
            auction=auction,
            buyer=e["buyer"],
            score=e["score"],
            components=e["components"],
            tier=e["tier"],
            rank=e["rank"],
            status=MatchStatus.SENT,
        )
        for e in ranked
    ]
    if edges:
        MatchEdge.objects.bulk_create(edges)


def _alert_tier(auction, tier) -> list:
    """Mark every not-yet-alerted edge in `tier` as alerted at the current price,
    stamping the green bonus, and emit one RESALE_ALERT audit event."""
    bonus = credit_bonus_at(auction, auction.current_price)
    edges = list(auction.edges.filter(tier=tier, alerted=False))
    for edge in edges:
        edge.alerted = True
        edge.price_at_alert = auction.current_price
        edge.green_credit_bonus = bonus
        edge.save(
            update_fields=["alerted", "price_at_alert", "green_credit_bonus", "updated_at"]
        )
    if edges:
        UnitEvent.objects.create(
            unit=auction.unit,
            type="RESALE_ALERT",
            actor=auction.seller,
            payload={
                "auction_id": auction.id,
                "tier": tier,
                "price": auction.current_price,
                "green_credit_bonus": bonus,
                "buyers": [e.buyer_id for e in edges],
            },
        )
    return edges


def start_auction_for_assessment(assessment):
    """Price + list + match a graded resale, then start its auction at tier 0.

    Finds the PENDING ResaleRequest by unit (the request is created before the
    async grader runs, so we can't rely on a back-link). Idempotent-ish: if no
    pending request exists (already priced), it no-ops.
    """
    rr = (
        ResaleRequest.objects.select_related("unit__product", "seller")
        .filter(unit=assessment.unit, status=ResaleStatus.PENDING)
        .order_by("-id")
        .first()
    )
    if rr is None:
        log.info("no pending resale request for unit %s; skipping", assessment.unit_id)
        return None

    unit = rr.unit
    product = unit.product
    seller = rr.seller

    priced = pricing.price_resale(
        original_price=rr.original_price,
        quality=assessment.quality_score,
        fraud=assessment.fraud_score,
        confidence=assessment.confidence,
        category=product.category,
        age_months=rr.age_months,
    )
    bounds = pricing.auction_bounds(priced["est_value"])
    ceiling, floor = bounds["ceiling"], bounds["floor"]
    grade = assessment.suggested_grade or unit.grade or "C"

    with transaction.atomic():
        unit.grade = grade
        unit.grade_confidence = assessment.confidence
        unit.est_value = priced["est_value"]
        unit.save(update_fields=["grade", "grade_confidence", "est_value", "updated_at"])

        listing = Listing.objects.create(
            unit=unit,
            source=ListingSources.USER_RESALE,
            price=ceiling,  # current ask; descends with the auction
            band_lo=priced["band_lo"],  # fair-value band (informational)
            band_hi=priced["band_hi"],
            photos=rr.photos,
            lister=seller,
            state=ListingStates.ACTIVE,
        )
        unit.transition(UnitStates.RELISTED, actor=seller, listing_id=listing.id)

        interval = settings.NEXTOWNER_AUCTION_INTERVAL_SECONDS
        auction = ResaleAuction.objects.create(
            listing=listing,
            unit=unit,
            seller=seller,
            ceiling=ceiling,
            floor=floor,
            current_price=ceiling,
            step_pct=settings.NEXTOWNER_AUCTION_STEP_PCT,
            interval_seconds=interval,
            tier=0,
            max_tier=settings.NEXTOWNER_AUCTION_MAX_TIER,
            status=AuctionStatus.ACTIVE,
            next_step_at=timezone.now() + timedelta(seconds=interval),
            pricing={
                "grade": grade,
                "est_value": priced["est_value"],
                "fair_low": priced["band_lo"],
                "fair_high": priced["band_hi"],
                **priced["factors"],
            },
        )

        _persist_edges(auction, matching.top_buyers(listing))
        _alert_tier(auction, tier=0)

        rr.assessment = assessment
        rr.listing = listing
        rr.status = ResaleStatus.PRICED
        rr.save(update_fields=["assessment", "listing", "status", "updated_at"])

    log.info(
        "resale auction %s started: grade=%s ceiling=%s floor=%s buyers=%s",
        auction.id,
        grade,
        auction.ceiling,
        auction.floor,
        auction.edges.count(),
    )
    return auction


def step(auction):
    """Lower the price one notch and widen the alert to the next buyer tier.

    Expires the auction only once it has reached BOTH the floor and the last
    tier. Mutates + saves `auction` (callers under the worker hold a row lock).
    """
    if auction.status != AuctionStatus.ACTIVE:
        return auction

    at_last_tier = auction.tier >= auction.max_tier - 1
    stepped = int(round(auction.current_price * (1.0 - auction.step_pct / 100.0)))
    new_price = max(stepped, auction.floor)
    at_floor = new_price <= auction.floor

    auction.current_price = new_price
    auction.tier = min(auction.tier + 1, auction.max_tier - 1)
    Listing.objects.filter(pk=auction.listing_id).update(price=new_price)
    _alert_tier(auction, tier=auction.tier)
    # Refresh the offered bonus on every already-alerted buyer: it tracks the
    # current price, so it rises toward the max as the auction descends.
    auction.edges.filter(alerted=True).update(
        green_credit_bonus=credit_bonus_at(auction, new_price)
    )

    if at_floor and at_last_tier:
        auction.status = AuctionStatus.EXPIRED
        auction.next_step_at = None
    else:
        auction.next_step_at = timezone.now() + timedelta(seconds=auction.interval_seconds)
    auction.save(update_fields=["current_price", "tier", "status", "next_step_at", "updated_at"])
    return auction


def buy(auction_id, buyer) -> dict:
    """Finalize a sale at the current price: transfer the unit, create the order,
    award green credits (base + the price-drop bonus), and release the seller
    payout. Row-locked so two buyers can't win the same unit."""
    with transaction.atomic():
        auction = (
            ResaleAuction.objects.select_for_update()
            .select_related("listing__unit__product", "seller", "unit__product")
            .get(pk=auction_id)
        )
        if auction.status != AuctionStatus.ACTIVE:
            return {"ok": False, "detail": "Auction is not active."}

        listing = Listing.objects.select_for_update().get(pk=auction.listing_id)
        if listing.state != ListingStates.ACTIVE:
            return {"ok": False, "detail": "Listing is no longer available."}

        unit = listing.unit
        if unit.owner_id == buyer.id:
            return {"ok": False, "detail": "You already own this item."}

        price = auction.current_price
        bonus = credit_bonus_at(auction, price)

        listing.transition(ListingStates.SOLD, actor=buyer)
        unit.owner = buyer
        unit.transition(UnitStates.SOLD, actor=buyer)
        order = Order.objects.create(buyer=buyer, listing=listing)

        auction.status = AuctionStatus.SOLD
        auction.buyer = buyer
        auction.current_price = price
        auction.next_step_at = None
        auction.save(update_fields=["status", "buyer", "current_price", "next_step_at", "updated_at"])

        auction.edges.filter(buyer=buyer).update(status=MatchStatus.PURCHASED)
        auction.edges.exclude(buyer=buyer).update(status=MatchStatus.EXPIRED)

        product_title = unit.product.title
        base = settings.NEXTOWNER_CREDIT_BASE
        award_credits(buyer, base, "BUY_USER_RESALE", f"Bought resold {product_title}", order.id)
        if bonus > 0:
            award_credits(
                buyer, bonus, "RESALE_INCENTIVE",
                f"Dutch-auction green bonus ({product_title})", order.id,
            )

        seller = auction.seller
        award_credits(
            seller, settings.NEXTOWNER_SELLER_RESELL_CREDIT, "RESELL",
            f"Resold {product_title}", listing.id,
        )
        payout = int(price * 0.92)
        UnitEvent.objects.create(
            unit=unit,
            type="PAYOUT_RELEASED",
            actor=seller,
            payload={"amount": payout, "fee": price - payout, "via": "next_best_owner"},
        )

    return {
        "ok": True,
        "order_id": order.id,
        "price": price,
        "green_credits": base + bonus,
        "green_credit_bonus": bonus,
    }


def rematch(auction):
    """Recompute the auction's buyer matches from scratch (demo / refresh): drop
    existing edges, rebuild the ranked set, and re-alert tiers up to the current
    one at the current price."""
    auction.edges.all().delete()
    _persist_edges(auction, matching.top_buyers(auction.listing))
    for tier in range(auction.tier + 1):
        _alert_tier(auction, tier=tier)
    return auction
