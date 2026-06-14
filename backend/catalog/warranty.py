"""Warranty math for the Product Health Card.

Catalog products carry a free-text warranty in `attributes["warranty"]`
(e.g. "1 year", "2 years", "6 months", "90 days"). Combined with the unit's
original purchase date (`ItemUnit.purchased_at`), we work out how much
manufacturer warranty is still left and render it the way a shopper expects:

    >= 1 year remaining  -> floored to whole years  ("2 years")
    <  1 year remaining  -> floored to whole months ("4 months")

We never surface a 0-month result or a warranty we can't parse/anchor — those
return None so the caller simply omits the field. Calendar-accurate arithmetic
(relativedelta) is used so "6 months from 15 Apr" lands on 15 Oct, not 180 days
later, keeping the floored remainder correct.
"""

import re
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.utils import timezone


def warranty_expiry(purchased_at, text):
    """When the warranty runs out (purchase date + parsed period), or None when
    there's no purchase date or nothing meaningful to parse."""
    if purchased_at is None or not text or not isinstance(text, str):
        return None
    match = re.search(r"(\d+)\s*(year|month|week|day)", text.lower())
    if not match:
        return None
    qty = int(match.group(1))
    if qty <= 0:
        return None
    unit = match.group(2)
    if unit == "year":
        return purchased_at + relativedelta(years=qty)
    if unit == "month":
        return purchased_at + relativedelta(months=qty)
    if unit == "week":
        return purchased_at + timedelta(weeks=qty)
    return purchased_at + timedelta(days=qty)


def warranty_remaining_label(product, purchased_at):
    """Human label for warranty still left ("2 years" / "4 months"), or None
    when it's expired, unknown, or can't be anchored to a purchase date."""
    attributes = getattr(product, "attributes", None) or {}
    expires = warranty_expiry(purchased_at, attributes.get("warranty"))
    if expires is None:
        return None

    now = timezone.now()
    if expires <= now:
        return None

    left = relativedelta(expires, now)
    if left.years >= 1:
        return f"{left.years} year{'s' if left.years != 1 else ''}"
    if left.months <= 0:
        return None
    return f"{left.months} month{'s' if left.months != 1 else ''}"
