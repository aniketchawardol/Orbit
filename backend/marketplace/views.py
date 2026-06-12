from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog.models import ItemUnit, UnitStates
from core.uploads import save_photos
from services import ai

from .models import (
    Listing,
    ListingSources,
    ListingStates,
    Order,
    OrderStates,
    ReturnReasons,
)
from .serializers import ListingSerializer, OrderSerializer

# Demo helper: which forward transitions are allowed via /advance
ADVANCE = {
    OrderStates.PLACED: OrderStates.DELIVERED,
    OrderStates.RETURN_REQUESTED: OrderStates.RETURN_RECEIVED,
}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def place_order(request):
    """Buy a listing. Row-lock prevents double-sell."""
    listing_id = request.data.get("listing_id")
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
        order = Order.objects.select_related("listing__unit").get(
            pk=pk, buyer=request.user
        )
    except Order.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    if order.state != OrderStates.DELIVERED:
        return Response(
            {"detail": f"Cannot return from state {order.state}."},
            status=status.HTTP_409_CONFLICT,
        )
    reason = request.data.get("reason", ReturnReasons.OTHER)
    if reason not in ReturnReasons.values:
        reason = ReturnReasons.OTHER

    try:
        photo_paths = save_photos(request.FILES.getlist("photos"), "returns")
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    claimed = request.data.get("claimed_untouched") in (True, "true", "True", "1", 1)
    order.return_reason = reason
    order.claimed_untouched = claimed
    order.photos = photo_paths
    order.transition(
        OrderStates.RETURN_REQUESTED,
        actor=request.user,
        reason=reason,
        photos=photo_paths,
    )
    order.listing.unit.transition(UnitStates.RETURN_PENDING, actor=request.user)
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
    order.transition(nxt, actor=request.user, demo=True)
    return Response(OrderSerializer(order).data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def resale(request):
    """GET: my resale listings. POST: create one from a delivered order
    (multipart: order_id, photos[], optional price)."""
    if request.method == "GET":
        qs = (
            Listing.objects.filter(
                lister=request.user, source=ListingSources.USER_RESALE
            )
            .select_related("unit__product")
            .order_by("-created_at")
        )
        return Response(ListingSerializer(qs, many=True).data)

    order_id = request.data.get("order_id")
    try:
        order = Order.objects.select_related("listing__unit__product").get(
            pk=order_id, buyer=request.user, state=OrderStates.DELIVERED
        )
    except Order.DoesNotExist:
        return Response(
            {"detail": "Order not found or not delivered."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # The SAME physical unit re-enters the marketplace (history preserved).
    unit = order.listing.unit
    product = unit.product

    if unit.owner_id != request.user.id:
        return Response(
            {"detail": "You no longer own this item."},
            status=status.HTTP_409_CONFLICT,
        )
    if unit.listings.filter(
        state__in=[ListingStates.ACTIVE, ListingStates.RESERVED]
    ).exists():
        return Response(
            {"detail": "This item is already listed."},
            status=status.HTTP_409_CONFLICT,
        )

    try:
        photo_paths = save_photos(request.FILES.getlist("photos"), "resale")
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    graded = ai.grade(product.id, untouched=False, image_paths=photo_paths)
    priced = ai.price(product.id, product.mrp, graded["grade"])

    chosen = int(request.data.get("price") or priced["est_value"])
    chosen = max(min(chosen, priced["band_hi"]), priced["band_lo"])  # clamp to band

    unit.grade = graded["grade"]
    unit.grade_confidence = graded["confidence"]
    unit.est_value = priced["est_value"]
    unit.save()

    listing = Listing.objects.create(
        unit=unit,
        source=ListingSources.USER_RESALE,
        price=chosen,
        band_lo=priced["band_lo"],
        band_hi=priced["band_hi"],
        photos=photo_paths,
        lister=request.user,
    )
    unit.transition(UnitStates.RELISTED, actor=request.user, listing_id=listing.id)
    # Order is now final: can't be returned or resold a second time.
    order.transition(OrderStates.SETTLED, actor=request.user, resold=True)
    return Response(ListingSerializer(listing).data, status=status.HTTP_201_CREATED)
