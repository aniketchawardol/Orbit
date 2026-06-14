"""Return-window policy.

The window is anchored on delivery (Order.delivered_at, set when an order is
marked DELIVERED) and falls back to order creation if delivery wasn't recorded.
Length is per-category with a global default. Used both to gate request_return
and to tell the UI up front whether to offer Return vs Resell.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def return_window_days(category) -> int:
    by_cat = getattr(settings, "RETURN_WINDOW_DAYS_BY_CATEGORY", {}) or {}
    default = getattr(settings, "RETURN_WINDOW_DAYS", 7)
    return int(by_cat.get((category or "").lower(), default))


def _anchor(order):
    return order.delivered_at or order.created_at


def return_deadline(order):
    anchor = _anchor(order)
    if not anchor:
        return None
    category = order.listing.unit.product.category
    return anchor + timedelta(days=return_window_days(category))


def buyer_started_resale(order) -> bool:
    """True once the buyer has handed this unit to resale.

    Keyed on a ResaleRequest filed by *this* buyer for *this* unit, so it stays
    correct even after the unit is later re-bought by someone else (its state
    cycles back to SOLD under a new owner). Authoritative even if the order row
    is still DELIVERED — e.g. orders resold before resale started settling the
    originating order.
    """
    from nextowner.models import ResaleRequest

    return ResaleRequest.objects.filter(
        unit_id=order.listing.unit_id, seller_id=order.buyer_id
    ).exists()


def is_return_eligible(order) -> bool:
    # Once the buyer has resold the unit, it's no longer theirs to return.
    if buyer_started_resale(order):
        return False
    deadline = return_deadline(order)
    if deadline is None:
        return True
    return timezone.now() <= deadline
