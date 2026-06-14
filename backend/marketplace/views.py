import json
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog.models import UnitStates
from core.uploads import save_photos
from greencredits.logic import award_credits

from .models import (
    Listing,
    ListingSources,
    ListingStates,
    Order,
    OrderStates,
    ReturnReasons,
)
from .returns import is_return_eligible, return_deadline
from .serializers import OrderSerializer

log = logging.getLogger(__name__)

# Demo helper: which forward transitions are allowed via /advance
ADVANCE = {
    OrderStates.PLACED: OrderStates.DELIVERED,
    OrderStates.RETURN_REQUESTED: OrderStates.RETURN_RECEIVED,
}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def place_order(request):
    """Buy a listing. Row-lock prevents double-sell.

    Pre-loved items are auction-backed (Next Best Owner): if the listing has an
    associated Dutch auction we delegate to that engine so the buyer pays the
    current descending price and earns the green-credit bonus, and the auction is
    closed atomically. Plain (NEW) listings keep the simple flow below.
    """
    listing_id = request.data.get("listing_id")

    # Auction-backed? Hand off to the Next Best Owner buy (price-drop bonus +
    # payout + auction close, all row-locked there).
    from nextowner.models import ResaleAuction

    auction = (
        ResaleAuction.objects.filter(listing_id=listing_id)
        .only("id")
        .first()
    )
    if auction is not None:
        from nextowner import auction as auction_mod

        result = auction_mod.buy(auction.id, request.user)
        if not result.get("ok"):
            return Response(
                {"detail": result.get("detail", "Could not complete purchase.")},
                status=status.HTTP_409_CONFLICT,
            )
        order = Order.objects.select_related("listing__unit__product").get(
            pk=result["order_id"]
        )
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    with transaction.atomic():
        listing = (
            Listing.objects.select_for_update()
            .filter(pk=listing_id, state=ListingStates.ACTIVE)
            .first()
        )
        if listing is None:
            return Response(
                {"detail": "Listing not available."},
                status=status.HTTP_409_CONFLICT,
            )
        if listing.unit.owner_id == request.user.id:
            return Response(
                {"detail": "You already own this item."},
                status=status.HTTP_409_CONFLICT,
            )
        listing.transition(ListingStates.SOLD, actor=request.user)
        unit = listing.unit
        unit.owner = request.user
        unit.transition(UnitStates.SOLD, actor=request.user)
        order = Order.objects.create(buyer=request.user, listing=listing)
        # Green credits: award for pre-loved purchase
        if listing.source == ListingSources.USER_RESALE:
            award_credits(request.user, 20, "BUY_USER_RESALE", "Bought pre-loved (user resale)", order.id)
            # Emit a pickup scheduled event for USER_RESALE orders
            from catalog.models import UnitEvent

            UnitEvent.objects.create(
                unit=unit,
                type="PICKUP_SCHEDULED",
                actor=request.user,
                payload={"eta": "tomorrow 9am", "note": "Pickup scheduled for resale order"},
            )
        elif listing.source == ListingSources.FACILITY_RELIST:
            award_credits(request.user, 25, "BUY_FACILITY_RELIST", "Bought pre-loved (facility relist)", order.id)
    return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders(request):
    qs = (
        Order.objects.filter(buyer=request.user)
        .select_related("listing__unit__product")
        .order_by("-created_at")
    )
    return Response(OrderSerializer(qs, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def request_return(request, pk):
    try:
        order = Order.objects.select_related("listing__unit__product").get(
            pk=pk, buyer=request.user
        )
    except Order.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    if order.state != OrderStates.DELIVERED:
        return Response(
            {"detail": f"Cannot return from state {order.state}."},
            status=status.HTTP_409_CONFLICT,
        )
    # Return window closed -> no return, but the item can still be resold.
    if not is_return_eligible(order):
        return Response(
            {
                "detail": "Return window has closed for this order.",
                "resell_available": True,
                "return_deadline": return_deadline(order),
            },
            status=status.HTTP_409_CONFLICT,
        )
    reason = request.data.get("reason", ReturnReasons.OTHER)
    if reason not in ReturnReasons.values:
        reason = ReturnReasons.OTHER

    try:
        photo_paths = save_photos(request.FILES.getlist("photos"), "returns")
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Per-photo client EXIF metadata, JSON-encoded and index-aligned to photos[].
    metadatas = []
    raw_meta = request.data.get("metadata")
    if raw_meta:
        try:
            parsed = json.loads(raw_meta)
            if isinstance(parsed, list):
                metadatas = parsed
        except (ValueError, TypeError):
            metadatas = []

    claimed = request.data.get("claimed_untouched") in (True, "true", "True", "1", 1)
    comment = (request.data.get("comment") or "").strip()
    order.return_reason = reason
    order.claimed_untouched = claimed
    order.return_comment = comment
    order.photos = photo_paths
    order.transition(
        OrderStates.RETURN_REQUESTED,
        actor=request.user,
        reason=reason,
        photos=photo_paths,
    )
    order.listing.unit.transition(UnitStates.RETURN_PENDING, actor=request.user)
    # Kick off async multi-source grading (VLM + similarity + metadata + history).
    # A grading/setup failure must never fail the buyer's return — log and move on.
    try:
        from grading.services import create_return_assessment

        create_return_assessment(order, photo_paths, client_metadatas=metadatas)
    except Exception:  # noqa: BLE001
        log.exception("could not start grading for order %s", order.id)
    # Green credits: untouched return (non-critical — never block the return).
    if claimed:
        try:
            award_credits(request.user, 5, "UNTOUCHED_RETURN", "Untouched return", order.id)
        except Exception:  # noqa: BLE001
            log.exception("could not award untouched-return credits for order %s", order.id)
    return Response(OrderSerializer(order).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def advance_order(request, pk):
    """Demo helper: move an order one step forward (e.g. PLACED→DELIVERED)."""
    try:
        order = Order.objects.get(pk=pk, buyer=request.user)
    except Order.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    nxt = ADVANCE.get(order.state)
    if nxt is None:
        return Response(
            {"detail": f"No demo advance from {order.state}."},
            status=status.HTTP_409_CONFLICT,
        )
    # Record delivery time so the return window can be measured from it.
    if nxt == OrderStates.DELIVERED:
        order.delivered_at = timezone.now()
        order.save(update_fields=["delivered_at"])
    order.transition(nxt, actor=request.user, demo=True)
    return Response(OrderSerializer(order).data)

