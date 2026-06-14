"""Next Best Owner API.

Seller/buyer endpoints (resell, alerts, buy) plus a small demo surface
(/demo/products, /demo/match, /demo/results) that powers the judge-facing
"Start matching" page: product cards whose top buyers stream in after matching,
with a live Dutch-auction price the frontend polls.
"""

import logging

from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.uploads import save_photos
from marketplace.models import ListingStates, Order, OrderStates

from . import auction as auction_mod
from .models import AuctionStatus, MatchEdge, MatchStatus, ResaleAuction
from .serializers import AuctionDetailSerializer, AuctionSerializer, MatchEdgeSerializer
from .services import start_resale_external, start_resale_from_order

log = logging.getLogger(__name__)


def _auction_for_request(rr):
    """Return the auction tied to a (possibly already-priced) resale request."""
    if rr.listing_id:
        return ResaleAuction.objects.filter(listing_id=rr.listing_id).first()
    return None


def _resale_response(rr, assessment):
    """Shape the resell response. If pricing already finished (eager mode), return
    the live auction; otherwise return the pending request so the UI can poll."""
    auction = _auction_for_request(rr)
    if auction is not None:
        return {
            "resale_request_id": rr.id,
            "status": rr.status,
            "auction": AuctionDetailSerializer(auction).data,
        }
    return {
        "resale_request_id": rr.id,
        "status": rr.status,
        "assessment_id": getattr(assessment, "id", None),
        "assessment_status": getattr(assessment, "status", None),
        "detail": "Grading in progress; poll the resale request for the auction.",
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def resell(request):
    """GET: my resale auctions. POST: list an item for resale.

    POST is multipart with photos[] plus EITHER:
      - order_id            -> resell a past platform purchase (linked, has a
                               reference image for grading), or
      - title, category, mrp, original_price [, brand, description, age_months]
                            -> resell a brand-new external item (no reference; the
                               grader runs in anomaly/quality mode).
    """
    if request.method == "GET":
        qs = (
            ResaleAuction.objects.filter(seller=request.user)
            .select_related("unit__product", "listing", "seller")
            .order_by("-created_at")
        )
        return Response(AuctionSerializer(qs, many=True).data)

    photos = request.FILES.getlist("photos")
    if not photos:
        return Response(
            {"detail": "At least one photo is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        photo_paths = save_photos(photos, "resale")
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    order_id = request.data.get("order_id")
    if order_id:
        try:
            order = Order.objects.select_related("listing__unit__product").get(
                pk=order_id, buyer=request.user
            )
        except Order.DoesNotExist:
            return Response(
                {"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )
        unit = order.listing.unit
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
        rr, assessment = start_resale_from_order(request.user, order, photo_paths)
        return Response(_resale_response(rr, assessment), status=status.HTTP_201_CREATED)

    # External (brand-new) item.
    try:
        title = (request.data.get("title") or "").strip()
        category = (request.data.get("category") or "").strip()
        mrp = int(request.data.get("mrp") or 0)
        original_price = int(request.data.get("original_price") or 0)
    except (TypeError, ValueError):
        return Response(
            {"detail": "mrp and original_price must be numbers."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not title or not category or mrp <= 0 or original_price <= 0:
        return Response(
            {"detail": "title, category, mrp and original_price are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        age_months = float(request.data.get("age_months") or 0)
    except (TypeError, ValueError):
        age_months = 0.0

    rr, assessment = start_resale_external(
        request.user,
        title=title,
        category=category,
        mrp=mrp,
        original_price=original_price,
        photo_paths=photo_paths,
        brand=(request.data.get("brand") or "").strip(),
        description=(request.data.get("description") or "").strip(),
        age_months=age_months,
    )
    return Response(_resale_response(rr, assessment), status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def alerts(request):
    """Resale alerts addressed to the current buyer (active auctions only), best
    fit first. Each carries the price + green-credit bonus at alert time."""
    edges = (
        MatchEdge.objects.filter(
            buyer=request.user,
            alerted=True,
            auction__status=AuctionStatus.ACTIVE,
        )
        .select_related("auction__unit__product", "auction__listing", "auction__seller")
        .order_by("tier", "rank")
    )
    out = []
    for edge in edges:
        out.append(
            {
                "match": MatchEdgeSerializer(edge).data,
                "auction": AuctionSerializer(edge.auction).data,
                "current_price": edge.auction.current_price,
                "green_credit_bonus": auction_mod.credit_bonus_at(
                    edge.auction, edge.auction.current_price
                ),
            }
        )
    # Mark SENT alerts as VIEWED (best-effort).
    edges.filter(status=MatchStatus.SENT).update(status=MatchStatus.VIEWED)
    return Response(out)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def auction_detail(request, pk):
    try:
        auction = ResaleAuction.objects.select_related(
            "unit__product", "listing", "seller", "buyer"
        ).get(pk=pk)
    except ResaleAuction.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    return Response(
        AuctionDetailSerializer(auction, context={"edge_limit": 25}).data
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def buy(request, pk):
    """Buy the item at the current Dutch price. Awards green credits (base + the
    price-drop bonus) and releases the seller payout."""
    result = auction_mod.buy(pk, request.user)
    if not result.get("ok"):
        return Response(
            {"detail": result.get("detail", "Could not complete purchase.")},
            status=status.HTTP_409_CONFLICT,
        )
    return Response(result, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def step(request, pk):
    """Demo control: force one descending price step (widens the buyer tier and
    raises the green bonus). Normally the Celery beat/worker does this on a timer."""
    from .tasks import step_auction

    step_auction(pk, force=True)
    try:
        auction = ResaleAuction.objects.select_related("unit__product", "listing").get(pk=pk)
    except ResaleAuction.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)
    return Response(AuctionDetailSerializer(auction).data)


# --------------------------------------------------------------------------- #
# Demo surface for the "Start matching" page
# --------------------------------------------------------------------------- #
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def demo_products(request):
    """Product cards for the demo grid: every resale auction, newest first."""
    qs = (
        ResaleAuction.objects.select_related("unit__product", "listing", "seller", "buyer")
        .order_by("-created_at")[:50]
    )
    return Response(AuctionSerializer(qs, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def demo_match(request):
    """'Start matching': precompute embeddings in parallel and (re)match auctions.
    Body (optional): {"auction_ids": [...]} — defaults to all active auctions."""
    from .tasks import run_demo_match

    ids = request.data.get("auction_ids") or []
    qs = ResaleAuction.objects.filter(status=AuctionStatus.ACTIVE)
    if ids:
        qs = qs.filter(pk__in=ids)
    target_ids = list(qs.values_list("id", flat=True))
    if not target_ids:
        return Response({"matching": [], "detail": "No active auctions to match."})
    run_demo_match(target_ids)  # eager: matches inline; worker: dispatches chord
    return Response({"matching": target_ids})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def demo_results(request):
    """Poll target for the demo page: every auction with its top buyers and the
    live Dutch price/tier. Frontend polls this every few seconds."""
    qs = (
        ResaleAuction.objects.select_related("unit__product", "listing", "seller", "buyer")
        .filter(Q(status=AuctionStatus.ACTIVE) | Q(status=AuctionStatus.SOLD))
        .order_by("-created_at")[:50]
    )
    data = AuctionDetailSerializer(qs, many=True, context={"edge_limit": 8}).data
    return Response(data)
