"""Build and cache a buyer's DemandProfile from their order + credit history.

The profile lives in the same embedding space as products, so a product<->buyer
cosine is meaningful. It blends:
- taste_vector     : recency-weighted average of bought-product embeddings,
- category/brand   : recency-weighted, normalized affinity histograms,
- price_mean/std   : the buyer's budget,
- green_propensity : 0..1 appetite for pre-loved goods (from credit history).

Cold-start buyers get a neutral profile (empty taste -> 0.5 semantic in matching),
so they still receive late-tier alerts rather than being excluded.
"""

import math

from django.conf import settings
from django.utils import timezone

from greencredits.models import CreditTransaction
from marketplace.models import Order

from .embeddings import provider_name, weighted_mean
from .models import DemandProfile
from .products import get_product_vector

# Credit-transaction types that signal a taste for buying pre-loved / resold goods.
_GREEN_BUY_TYPES = {"BUY_USER_RESALE", "BUY_FACILITY_RELIST", "RESALE_INCENTIVE"}


def _recency_weight(when, half_life_days) -> float:
    if not when:
        return 1.0
    age_days = max(0.0, (timezone.now() - when).total_seconds() / 86400.0)
    return 0.5 ** (age_days / max(1.0, half_life_days))


def _normalize(hist: dict) -> dict:
    total = sum(hist.values())
    if total <= 0:
        return {}
    return {k: round(v / total, 4) for k, v in hist.items()}


def _std(values, mean) -> float:
    if len(values) < 2:
        return 0.0
    var = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(var)


def _green_propensity(user, n_orders) -> float:
    txns = list(
        CreditTransaction.objects.filter(account__user=user).values_list("type", "amount")
    )
    if not txns and n_orders == 0:
        return 0.0
    preloved = sum(1 for t, _ in txns if t in _GREEN_BUY_TYPES)
    earned = sum(a for _, a in txns if a > 0)
    preloved_ratio = preloved / n_orders if n_orders else 0.0
    engagement = min(1.0, earned / 200.0)
    return max(0.0, min(1.0, 0.6 * preloved_ratio + 0.4 * engagement))


def build_demand_profile(user, force=False) -> DemandProfile:
    half_life = float(getattr(settings, "NEXTOWNER_RECENCY_HALFLIFE_DAYS", 45))

    orders = list(
        Order.objects.filter(buyer=user)
        .select_related("listing__unit__product")
        .order_by("-created_at")
    )

    vectors, weights = [], []
    cat_affinity, brand_affinity, prices = {}, {}, []
    for order in orders:
        product = order.listing.unit.product
        w = _recency_weight(order.created_at, half_life)
        vec = get_product_vector(product)
        if vec:
            vectors.append(vec)
            weights.append(w)
        cat = (product.category or "").strip().lower()
        if cat:
            cat_affinity[cat] = cat_affinity.get(cat, 0.0) + w
        brand = str((product.attributes or {}).get("brand", "")).strip().lower()
        if brand:
            brand_affinity[brand] = brand_affinity.get(brand, 0.0) + w
        prices.append(float(order.listing.price))

    taste = weighted_mean(vectors, weights)
    price_mean = sum(prices) / len(prices) if prices else 0.0
    n_orders = len(orders)

    obj, _ = DemandProfile.objects.update_or_create(
        user=user,
        defaults={
            "taste_vector": taste,
            "dim": len(taste),
            "category_affinity": _normalize(cat_affinity),
            "brand_affinity": _normalize(brand_affinity),
            "price_mean": price_mean,
            "price_std": _std(prices, price_mean),
            "green_propensity": _green_propensity(user, n_orders),
            "n_orders": n_orders,
            "provider": provider_name(),
        },
    )
    return obj


def get_demand_profile(user, build_if_missing=True):
    """Cached profile for a buyer, building it on demand if missing/stale."""
    dp = DemandProfile.objects.filter(user=user).first()
    if dp is not None and dp.provider == provider_name():
        return dp
    if build_if_missing:
        return build_demand_profile(user)
    return dp
