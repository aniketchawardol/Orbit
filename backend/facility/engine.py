"""Storage-cost engine — shared by the management command and the
demo "simulate day" endpoint so both run identical logic."""

from django.conf import settings

from catalog.models import ItemUnit, UnitStates
from marketplace.models import ListingStates


def daily_rate(category: str) -> int:
    return settings.STORAGE_DAILY_RATE_BY_CATEGORY.get(
        category, settings.STORAGE_DAILY_RATE_DEFAULT
    )


def accrue_one_day(actor=None):
    """Advance the storage clock one day for every unit on the facility floor.

    Returns a summary dict for API/CLI output.
    """
    units = ItemUnit.objects.filter(
        state__in=[UnitStates.AT_FACILITY, UnitStates.RELISTED],
        arrived_at_facility__isnull=False,
    ).select_related("product")

    accrued, liquidated, stepped_down = 0, 0, 0

    for unit in units:
        unit.storage_cost_accrued += daily_rate(unit.product.category)
        accrued += 1

        if unit.est_value is not None and unit.storage_cost_accrued >= unit.est_value:
            _withdraw_listing(unit, actor)
            unit.save()
            unit.transition(
                UnitStates.LIQUIDATE,
                actor=actor,
                storage_cost=unit.storage_cost_accrued,
                est_value=unit.est_value,
            )
            liquidated += 1
            continue

        if _maybe_step_down_price(unit, actor):
            stepped_down += 1
        unit.save()

    return {
        "units_accrued": accrued,
        "liquidated": liquidated,
        "price_stepdowns": stepped_down,
    }


def _active_listing(unit):
    return unit.listings.filter(state=ListingStates.ACTIVE).first()


def _withdraw_listing(unit, actor):
    listing = _active_listing(unit)
    if listing:
        listing.transition(ListingStates.WITHDRAWN, actor=actor, reason="storage_exceeded")


def _maybe_step_down_price(unit, actor) -> bool:
    """−PRICE_STEPDOWN_PCT% every PRICE_STEPDOWN_EVERY_DAYS 'days' (days are
    measured in accrued increments so demo fast-forward works naturally)."""
    listing = _active_listing(unit)
    if not listing or not listing.band_lo:
        return False

    rate = daily_rate(unit.product.category)
    days_on_floor = unit.storage_cost_accrued // rate if rate else 0
    if days_on_floor == 0 or days_on_floor % settings.PRICE_STEPDOWN_EVERY_DAYS != 0:
        return False

    new_price = max(
        listing.band_lo,
        listing.price * (100 - settings.PRICE_STEPDOWN_PCT) // 100,
    )
    if new_price >= listing.price:
        return False
    old = listing.price
    listing.price = new_price
    listing.save()
    from catalog.models import UnitEvent

    UnitEvent.objects.create(
        unit=unit,
        type="PRICE_STEPDOWN",
        actor=actor,
        payload={"from": old, "to": new_price},
    )
    return True
