from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import ItemUnit, Product
from .serializers import ItemUnitSerializer, ProductSerializer
from marketplace.serializers import ListingSerializer
from marketplace.models import Listing
from services import ai


@api_view(["GET"])
@permission_classes([AllowAny])
def product_list(request):
    qs = Product.objects.all().order_by("-created_at")
    q = request.query_params.get("q")
    category = request.query_params.get("category")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if category:
        qs = qs.filter(category=category)
    return Response(ProductSerializer(qs[:60], many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def product_detail(request, pk):
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    listings = Listing.objects.filter(
        unit__product=product, state="ACTIVE"
    ).select_related("unit")
    data = ProductSerializer(product).data
    data["listings"] = ListingSerializer(listings, many=True).data
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def product_related(request, pk):
    """Other products in the same category — powers the "More in <category>"
    carousel on the product page. Excludes the current product."""
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    qs = (
        Product.objects.filter(category=product.category)
        .exclude(pk=product.pk)
        .order_by("-created_at")
    )
    return Response(ProductSerializer(qs[:12], many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def unit_health_card(request, pk):
    """Public Health Card: unit lifecycle + grade + events."""
    try:
        unit = ItemUnit.objects.select_related("product").get(pk=pk)
    except ItemUnit.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    # Buyers must not see the internal AI disposition recommendation — that's
    # a facility-only signal. Opt out so the field is omitted entirely.
    data = ItemUnitSerializer(unit, context={"include_routing": False}).data

    # The price shoppers actually see on the site is the live listing/auction
    # price, NOT the internal `est_value`. Surface it so the card can show the
    # MRP (struck through) next to the current price, like any storefront.
    from nextowner.models import AuctionStatus, ResaleAuction

    auction = (
        ResaleAuction.objects.filter(unit=unit, status=AuctionStatus.ACTIVE)
        .order_by("-created_at")
        .first()
    )
    if auction:
        data["current_price"] = auction.current_price
    else:
        listing = (
            Listing.objects.filter(unit=unit, state="ACTIVE")
            .order_by("-created_at")
            .first()
        )
        data["current_price"] = listing.price if listing else None

    from .warranty import warranty_remaining_label

    data["warranty_remaining"] = warranty_remaining_label(
        unit.product, unit.purchased_at
    )

    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def preloved_list(request):
    """Active pre-loved listings as Next-Best-Owner auctions.

    Every pre-loved item flows through the Dutch-auction engine, so we return
    auction cards (price = current_price, with the grading/match metadata).
    Each card carries `recommended: bool` — true when the signed-in user is an
    alerted (matched) buyer for that auction, so the frontend can surface a
    "Recommended for you" rail. Logged-out users get all cards, none recommended.
    """
    from nextowner.models import AuctionStatus, MatchEdge, ResaleAuction
    from nextowner.serializers import AuctionSerializer

    qs = (
        ResaleAuction.objects.filter(status=AuctionStatus.ACTIVE)
        .select_related("unit__product", "listing", "seller", "buyer")
        .order_by("-created_at")
    )
    category = request.query_params.get("category")
    grade = request.query_params.get("grade")
    q = request.query_params.get("q")
    if category:
        qs = qs.filter(unit__product__category=category)
    if grade:
        qs = qs.filter(unit__grade=grade)
    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(unit__product__title__icontains=q)
            | Q(unit__product__description__icontains=q)
        )
    qs = list(qs[:60])

    # Which of these is the current buyer alerted (matched) to?
    recommended_ids = set()
    user = request.user
    if user.is_authenticated and qs:
        recommended_ids = set(
            MatchEdge.objects.filter(
                buyer=user,
                alerted=True,
                auction__in=qs,
            ).values_list("auction_id", flat=True)
        )

    data = AuctionSerializer(qs, many=True).data
    for row in data:
        row["recommended"] = row["id"] in recommended_ids
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def product_fitcheck(request, pk):
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    try:
        res = ai.fit_check(product.id, product.category)
        return Response(res)
    except Exception:
        return Response({"hint": None})
