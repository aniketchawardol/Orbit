from django.db.models import F, FloatField
from django.db.models.functions import Cast
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from catalog.models import ItemUnit, UnitStates
from catalog.serializers import ItemUnitSerializer
from core.permissions import IsFacility
from marketplace.models import ListingSources, OrderStates
from services import ai

from .engine import accrue_one_day


@api_view(["GET"])
@permission_classes([IsFacility])
def incoming(request):
    """Units whose owners initiated a return — awaiting physical receipt."""
    units = (
        ItemUnit.objects.filter(state=UnitStates.RETURN_PENDING)
        .select_related("product")
        .order_by("updated_at")
    )
    return Response(ItemUnitSerializer(units, many=True).data)


@api_view(["POST"])
@permission_classes([IsFacility])
def receive(request):
    """Scan-in a returned unit: verify untouched claim, grade, price, start clock."""
    unit_id = request.data.get("unit_id")
    try:
        unit = ItemUnit.objects.select_related("product").get(
            pk=unit_id, state=UnitStates.RETURN_PENDING
        )
    except ItemUnit.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    unit.untouched = bool(request.data.get("untouched", False))
    unit.arrived_at_facility = timezone.now()

    # Grade using the photos the buyer attached at return time (if any).
    from marketplace.models import Order

    return_order = Order.objects.filter(
        listing__unit=unit,
        state__in=[OrderStates.RETURN_REQUESTED, OrderStates.RETURN_RECEIVED],
    ).first()
    return_photos = return_order.photos if return_order else []

    # Prefer the multi-source assessment computed asynchronously at return time;
    # fall back to the single-shot heuristic grader if none completed.
    from grading.models import AssessmentStatus, GradingAssessment

    assessment = (
        GradingAssessment.objects.filter(unit=unit, status=AssessmentStatus.DONE)
        .exclude(suggested_grade="")
        .order_by("-created_at")
        .first()
    )
    if assessment and assessment.suggested_grade:
        graded = {
            "grade": assessment.suggested_grade,
            "confidence": assessment.confidence or 0.0,
            "source": f"grading:{assessment.vlm_provider or 'mock'}",
        }
    else:
        graded = ai.grade(
            unit.product.id, untouched=unit.untouched, image_paths=return_photos
        )
    priced = ai.price(unit.product.id, unit.product.mrp, graded["grade"])
    unit.grade = graded["grade"]
    unit.grade_confidence = graded["confidence"]
    unit.est_value = priced["est_value"]
    unit.save()
    unit.transition(
        UnitStates.AT_FACILITY,
        actor=request.user,
        grade=graded["grade"],
        untouched=unit.untouched,
        ai_source=graded["source"],
    )

    # AI routing recommendation
    try:
        routing = ai.route(
            product_id=unit.product.id,
            grade=unit.grade,
            grade_confidence=unit.grade_confidence or 0.0,
            est_value=unit.est_value or 0,
            mrp=unit.product.mrp or 0,
            untouched=unit.untouched,
            storage_cost=unit.storage_cost_accrued or 0,
            category=unit.product.category,
        )
        # Store the recommendation as a UnitEvent for audit/UI
        from catalog.models import UnitEvent

        UnitEvent.objects.create(
            unit=unit,
            type="ROUTING_RECOMMENDATION",
            actor=request.user,
            payload={"routing": routing},
        )
    except Exception:
        routing = None

    # Mark the originating order refunded (refund-on-receipt).
    if return_order:
        return_order.transition(OrderStates.REFUNDED, actor=request.user)

    data = ItemUnitSerializer(unit).data
    data["routing_recommendation"] = routing
    return Response(data)


@api_view(["POST"])
@permission_classes([IsFacility])
def relist(request, pk):
    """Relist an AT_FACILITY unit (typically untouched / grade A-B)."""
    try:
        unit = ItemUnit.objects.select_related("product").get(
            pk=pk, state=UnitStates.AT_FACILITY
        )
    except ItemUnit.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    from marketplace.models import Listing, ListingStates

    if unit.listings.filter(
        state__in=[ListingStates.ACTIVE, ListingStates.RESERVED]
    ).exists():
        return Response(
            {"detail": "Already listed."}, status=status.HTTP_409_CONFLICT
        )

    priced = ai.price(unit.product.id, unit.product.mrp, unit.grade or "B")
    listing = Listing.objects.create(
        unit=unit,
        source=ListingSources.FACILITY_RELIST,
        price=int(request.data.get("price") or priced["est_value"]),
        band_lo=priced["band_lo"],
        band_hi=priced["band_hi"],
    )
    unit.est_value = priced["est_value"]
    unit.save()
    unit.transition(UnitStates.RELISTED, actor=request.user, listing_id=listing.id)
    return Response(ItemUnitSerializer(unit).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsFacility])
def watchlist(request):
    """Units ranked by storage-cost-vs-value ratio (closest to liquidation first)."""
    units = (
        ItemUnit.objects.filter(
            state__in=[UnitStates.AT_FACILITY, UnitStates.RELISTED],
            est_value__isnull=False,
        )
        .exclude(est_value=0)
        .annotate(
            ratio=Cast(F("storage_cost_accrued"), FloatField())
            / Cast(F("est_value"), FloatField())
        )
        .select_related("product")
        .order_by("-ratio")
    )
    data = []
    for unit in units:
        row = ItemUnitSerializer(unit).data
        row["storage_ratio"] = round(unit.ratio, 3)
        data.append(row)
    return Response(data)


@api_view(["POST"])
@permission_classes([IsFacility])
def dispose(request, pk):
    """Manually liquidate or donate a unit."""
    target = request.data.get("target")
    if target not in (UnitStates.LIQUIDATE, UnitStates.DONATED):
        return Response({"detail": "Bad target."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        unit = ItemUnit.objects.get(
            pk=pk, state__in=[UnitStates.AT_FACILITY, UnitStates.RELISTED]
        )
    except ItemUnit.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    from marketplace.models import ListingStates

    active = unit.listings.filter(state=ListingStates.ACTIVE).first()
    if active:
        active.transition(ListingStates.WITHDRAWN, actor=request.user)
    unit.transition(target, actor=request.user, manual=True)
    return Response(ItemUnitSerializer(unit).data)


@api_view(["POST"])
@permission_classes([IsFacility])
def simulate_day(request):
    """Demo: advance the storage clock one day. Same code as the cron command."""
    summary = accrue_one_day(actor=request.user)
    return Response(summary)
