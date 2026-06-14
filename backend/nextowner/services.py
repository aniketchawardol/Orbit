"""Resale entry points used by the views.

Turns either a past order (linked item — we have the original catalog image, so
the grader compares photos normally) or a brand-new external item (no reference —
the grader runs in VLM anomaly/quality mode) into a graded ResaleRequest. The
grading completion hook (grading.orchestrator.aggregate -> nextowner.price_and_match)
prices it, lists it, matches buyers, and starts the Dutch auction.
"""

import logging

from django.utils import timezone

from catalog.models import ItemUnit, Product, ProductOrigin, UnitStates

from .models import ResaleRequest

log = logging.getLogger(__name__)


def _reference_paths(product) -> list:
    """The catalog reference image for a linked product, if any (empty for
    external items, which forces the grader into anomaly/quality mode)."""
    if product.image:
        try:
            name = product.image.name
            if name:
                return [name]
        except Exception:  # noqa: BLE001
            return []
    return []


def start_resale_from_order(user, order, photo_paths, age_months=None):
    """Resell an item bought on the platform. We already have its unit, original
    price (what the user paid) and a reference image for grading."""
    from grading.services import create_resale_assessment
    from marketplace.models import OrderStates

    unit = order.listing.unit
    product = unit.product
    if age_months is None:
        anchor = order.delivered_at or order.created_at
        age_months = max(0.0, (timezone.now() - anchor).days / 30.0) if anchor else 0.0

    # Anchor the warranty clock to when the seller originally received the item,
    # so the Health Card can show how much manufacturer warranty is still left.
    purchased_at = order.delivered_at or order.created_at
    if purchased_at and unit.purchased_at != purchased_at:
        unit.purchased_at = purchased_at
        unit.save(update_fields=["purchased_at"])

    rr = ResaleRequest.objects.create(
        seller=user,
        unit=unit,
        photos=photo_paths,
        original_price=order.listing.price,
        age_months=age_months,
        linked=True,
    )
    # Once an item is handed to resale it's no longer the buyer's to return:
    # settle the originating order so it drops off the returnable Orders list
    # (and the resale-candidates list), mirroring the old synchronous flow.
    if order.state == OrderStates.DELIVERED:
        order.transition(OrderStates.SETTLED, actor=user, resold=True)
    assessment = create_resale_assessment(
        unit, photo_paths, _reference_paths(product), triggered_by=user
    )
    rr.refresh_from_db()  # eager mode: pricing may already have completed
    return rr, assessment


def start_resale_external(
    user,
    *,
    title,
    category,
    mrp,
    original_price,
    photo_paths,
    brand="",
    description="",
    age_months=0.0,
):
    """Resell a brand-new item a user brought from outside. We create an EXTERNAL
    product + unit on the fly; there's no reference image, so grading runs in
    anomaly/quality mode (hash comparison is skipped)."""
    from grading.services import create_resale_assessment

    attributes = {"brand": brand} if brand else {}
    product = Product.objects.create(
        title=title,
        description=description,
        category=category,
        mrp=mrp,
        attributes=attributes,
        seller=user,
        origin=ProductOrigin.EXTERNAL,
    )
    unit = ItemUnit.objects.create(product=product, owner=user, state=UnitStates.NEW)

    rr = ResaleRequest.objects.create(
        seller=user,
        unit=unit,
        photos=photo_paths,
        original_price=original_price,
        age_months=age_months or 0.0,
        linked=False,
    )
    assessment = create_resale_assessment(unit, photo_paths, [], triggered_by=user)
    rr.refresh_from_db()
    return rr, assessment


def open_relist_auction(unit, actor, *, source, photos=None, est_value=None,
                        band_lo=None, band_hi=None, grade=None, pricing_extra=None):
    """Open a Dutch auction for an already-graded relisted unit (facility relist /
    seller auto-relist), with `actor` as both owner and lister. Returns the
    ResaleAuction. Under the worker, also schedules the descending price stepper;
    in eager mode the auction simply waits for manual/no steps. Never raises into
    the caller's flow — a matching/embedding hiccup must not break a relist."""
    from . import auction as auction_mod

    auction = auction_mod.open_auction_for_unit(
        unit,
        actor,
        source=source,
        photos=photos,
        est_value=est_value,
        band_lo=band_lo,
        band_hi=band_hi,
        grade=grade,
        pricing_extra=pricing_extra,
    )
    try:
        from .tasks import _schedule_step

        _schedule_step(auction)
    except Exception:  # noqa: BLE001 — scheduling is best-effort
        log.exception("could not schedule steps for relist auction %s", getattr(auction, "id", None))
    return auction

