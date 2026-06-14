from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from catalog.models import ItemUnit, Product, UnitStates
from catalog.serializers import ItemUnitSerializer, ProductSerializer
from core.permissions import IsSeller
from core.uploads import validate_image
from marketplace.models import Listing, ListingSources
from services import ai
from greencredits.logic import award_credits

from .models import RuleActions, SellerRule
from .serializers import SellerRuleSerializer


@api_view(["GET", "POST"])
@permission_classes([IsSeller])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def products(request):
    """GET: my catalog. POST (multipart): create product with image + initial
    stock — each stock unit gets a NEW listing immediately."""
    if request.method == "GET":
        qs = Product.objects.filter(seller=request.user).order_by("-created_at")
        return Response(ProductSerializer(qs, many=True).data)

    title = (request.data.get("title") or "").strip()
    category = (request.data.get("category") or "").strip().lower()
    try:
        mrp = int(request.data.get("mrp") or 0)
        stock = max(1, min(int(request.data.get("stock") or 1), 50))
    except ValueError:
        return Response({"detail": "Bad mrp/stock."}, status=status.HTTP_400_BAD_REQUEST)
    if not title or not category or mrp <= 0:
        return Response(
            {"detail": "title, category and positive mrp required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    image = request.FILES.get("image")
    if image is not None:
        try:
            validate_image(image)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    product = Product.objects.create(
        title=title,
        description=request.data.get("description", ""),
        category=category,
        mrp=mrp,
        image=image,  # ImageField handles storage under products/
        seller=request.user,
    )
    for _ in range(stock):
        unit = ItemUnit.objects.create(product=product, state=UnitStates.NEW)
        Listing.objects.create(
            unit=unit,
            source=ListingSources.NEW,
            price=mrp,
            lister=request.user,
        )
    data = ProductSerializer(product).data
    data["stock_listed"] = stock
    return Response(data, status=status.HTTP_201_CREATED)


def _relist_unit(unit, actor, source=ListingSources.SELLER_RETURN):
    priced = ai.price(unit.product.id, unit.product.mrp, unit.grade or "B")
    # Every pre-loved item flows through the Next Best Owner engine: open a Dutch
    # auction + match buyers. The relisting seller becomes owner + lister, so the
    # sale payout/credit lands on them.
    from nextowner.services import open_relist_auction

    auction = open_relist_auction(
        unit,
        actor,
        source=source,
        est_value=priced["est_value"],
        band_lo=priced["band_lo"],
        band_hi=priced["band_hi"],
        grade=unit.grade or "B",
        pricing_extra={"source": "seller_relist"},
    )
    return auction.listing


APPLY_ACTION = {
    RuleActions.AUTO_RELIST: lambda unit, actor: _relist_unit(unit, actor),
    RuleActions.LIQUIDATE: lambda unit, actor: unit.transition(
        UnitStates.LIQUIDATE, actor=actor
    ),
    RuleActions.DONATE: lambda unit, actor: unit.transition(
        UnitStates.DONATED, actor=actor
    ),
}


@api_view(["GET"])
@permission_classes([IsSeller])
def returns_inbox(request):
    """Seller's returned units at facility + rule suggestion for each."""
    units = (
        ItemUnit.objects.filter(
            product__seller=request.user, state=UnitStates.AT_FACILITY
        )
        .select_related("product")
        .order_by("-updated_at")
    )
    rules = list(SellerRule.objects.filter(seller=request.user, active=True))
    data = []
    for unit in units:
        matched = next((r for r in rules if r.matches(unit)), None)
        row = ItemUnitSerializer(unit).data
        row["suggested_action"] = matched.action if matched else None
        row["matched_rule_id"] = matched.id if matched else None
        data.append(row)
    return Response(data)


@api_view(["POST"])
@permission_classes([IsSeller])
def apply_action(request):
    """Apply an action to one unit (or rule suggestion)."""
    unit_id = request.data.get("unit_id")
    action = request.data.get("action")
    if action not in RuleActions.values:
        return Response({"detail": "Bad action."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        unit = ItemUnit.objects.select_related("product").get(
            pk=unit_id, product__seller=request.user, state=UnitStates.AT_FACILITY
        )
    except ItemUnit.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    APPLY_ACTION[action](unit, request.user)
    # Green credits: if seller donates the unit, award credits
    if action == RuleActions.DONATE:
        award_credits(request.user, 15, "SELLER_DONATE", f"Donated {unit.product.title}", unit.id)
    return Response(ItemUnitSerializer(unit).data)


@api_view(["POST"])
@permission_classes([IsSeller])
def bulk_apply(request):
    """Run all active rules across the inbox; returns counts."""
    rules = list(
        SellerRule.objects.filter(seller=request.user, active=True).order_by("id")
    )
    units = ItemUnit.objects.filter(
        product__seller=request.user, state=UnitStates.AT_FACILITY
    ).select_related("product")
    handled = 0
    for unit in units:
        matched = next((r for r in rules if r.matches(unit)), None)
        if matched:
            APPLY_ACTION[matched.action](unit, request.user)
            handled += 1
    return Response({"handled": handled, "remaining": units.count() - handled})


@api_view(["GET", "POST"])
@permission_classes([IsSeller])
def rules(request):
    if request.method == "GET":
        qs = SellerRule.objects.filter(seller=request.user).order_by("id")
        return Response(SellerRuleSerializer(qs, many=True).data)
    ser = SellerRuleSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    ser.save(seller=request.user)
    return Response(ser.data, status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsSeller])
def rule_detail(request, pk):
    try:
        rule = SellerRule.objects.get(pk=pk, seller=request.user)
    except SellerRule.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    if request.method == "DELETE":
        rule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    ser = SellerRuleSerializer(rule, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    return Response(ser.data)
