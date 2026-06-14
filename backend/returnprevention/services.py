"""Return-prevention services: apparel fit guide + accessory compatibility.

Two independent, pre-purchase checks:

1. ``fit_guide`` — INSTANT. Reads the shopper's declared sizes from
   ``User.profile["sizes"]`` and the product's ``size_type``/``size_options``
   attributes to recommend the best size. No LLM, no network.

2. ``get_compat`` — accessory compatibility from order history. Cached per
   (user, product) in Redis; computed by the LLM (``llm.check_compat``) with a
   deterministic ``rules`` fallback so it works offline. Only accessories (a
   product with a ``compatible_model`` attribute) are ever checked; everything
   else is compatible by definition (and never warns).

``purchase_warnings`` combines both into the gate used by ``place_order``.
"""

import logging

from django.conf import settings
from django.core.cache import cache

from . import llm, rules

log = logging.getLogger(__name__)

# Ordered apparel-top sizes, used to pick the closest option when the shopper's
# declared size isn't an exact option for a given garment.
_TOP_ORDER = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]

# Human-friendly label per size dimension (shown in the UI prompt).
SIZE_LABELS = {
    "waist": "waist size",
    "top": "size",
    "shirt": "collar size",
    "shoe_uk": "UK shoe size",
}


# --------------------------------------------------------------------------- #
# Apparel / footwear fit guide (instant, from the user's size profile)
# --------------------------------------------------------------------------- #
def _num(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _closest(value, options, size_type):
    """Pick the option nearest to the shopper's declared size."""
    if not options:
        return None
    if value in options:
        return value
    if size_type == "top":
        if value not in _TOP_ORDER:
            return None
        vi = _TOP_ORDER.index(value)
        ranked = [o for o in options if o in _TOP_ORDER]
        if not ranked:
            return None
        return min(ranked, key=lambda o: abs(_TOP_ORDER.index(o) - vi))
    v = _num(value)
    if v is None:
        return None
    numeric = [(o, _num(o)) for o in options if _num(o) is not None]
    if not numeric:
        return None
    return min(numeric, key=lambda pair: abs(pair[1] - v))[0]


def fit_guide(user, product):
    """Recommend a size for a sized product based on the user's size profile.

    Returns {"sized": False} for products without sizing, else a dict with the
    size dimension, the selectable options, and the recommended size + message.
    """
    attrs = product.attributes or {}
    size_type = str(attrs.get("size_type") or "").strip()
    options = [str(o) for o in (attrs.get("size_options") or [])]
    if not size_type or not options:
        return {"sized": False}

    sizes = {}
    if user is not None and getattr(user, "is_authenticated", False):
        sizes = (getattr(user, "profile", None) or {}).get("sizes", {}) or {}
    declared = sizes.get(size_type)
    recommended = None
    if declared is not None:
        recommended = _closest(str(declared), options, size_type)

    message = f"Size {recommended} will fit you best" if recommended else None
    return {
        "sized": True,
        "size_type": size_type,
        "size_label": SIZE_LABELS.get(size_type, "size"),
        "size_options": options,
        "recommended_size": recommended,
        "message": message,
    }


# --------------------------------------------------------------------------- #
# Accessory compatibility (order-history aware, LLM + cache)
# --------------------------------------------------------------------------- #
def owned_devices(user):
    """Devices (products with a ``model`` attribute) the user has ordered."""
    from marketplace.models import Order

    seen = set()
    out = []
    qs = (
        Order.objects.filter(buyer=user)
        .select_related("listing__unit__product")
        .order_by("-created_at")
    )
    for order in qs:
        product = order.listing.unit.product
        model = str((product.attributes or {}).get("model", "")).strip()
        if not model or model.lower() in seen:
            continue
        seen.add(model.lower())
        out.append(
            {"title": product.title, "model": model, "category": product.category}
        )
    return out


def _compat_key(user_id, product_id):
    return f"returnprev:compat:{user_id}:{product_id}"


def get_compat(user, product, force=False):
    """Compatibility verdict for an accessory, cached per (user, product).

    Returns {"checked": bool, "compatible": bool, "warning": str}. Non-accessory
    products short-circuit to compatible (no LLM, no cache).
    """
    target = str((product.attributes or {}).get("compatible_model", "")).strip()
    if not target:
        return {"checked": False, "compatible": True, "warning": ""}

    key = _compat_key(user.id, product.id)
    if not force:
        cached = cache.get(key)
        if cached is not None:
            return cached

    owned = owned_devices(user)
    verdict = None
    try:
        verdict = llm.check_compat(product, target, owned)
    except Exception:  # noqa: BLE001 — never let the gate raise
        log.exception("compat LLM raised for user %s product %s", user.id, product.id)
        verdict = None
    if verdict is None:
        verdict = rules.check_compat(target, owned)

    compatible = bool(verdict.get("compatible"))
    warning = "" if compatible else (verdict.get("warning") or "").strip()
    # Deterministic guard against false positives: only ever warn when the
    # shopper actually owns a same-line device that does not fit this accessory.
    # This suppresses cross-family warnings (e.g. owning an iPhone while buying a
    # Galaxy case) no matter what the LLM returned — we only flag genuine,
    # user-specific incompatibilities.
    if not compatible and not rules.has_family_conflict(target, owned):
        compatible, warning = True, ""
    payload = {
        "checked": True,
        "compatible": compatible,
        "warning": warning,
    }
    cache.set(key, payload, getattr(settings, "RETURNPREV_CACHE_TTL", 3600))
    return payload


def accessory_product_ids():
    """Product ids of purchasable accessories (have ``compatible_model`` + an
    ACTIVE listing). Bounded fan-out target for the login precompute."""
    from marketplace.models import Listing, ListingStates

    ids = set()
    qs = Listing.objects.filter(state=ListingStates.ACTIVE).select_related(
        "unit__product"
    )
    for listing in qs:
        product = listing.unit.product
        if str((product.attributes or {}).get("compatible_model", "")).strip():
            ids.add(product.id)
    return list(ids)


# --------------------------------------------------------------------------- #
# Combined pre-purchase gate (used by place_order)
# --------------------------------------------------------------------------- #
def purchase_warnings(user, product, chosen_size):
    """Combine the size + compatibility checks for a buy attempt.

    Returns a dict: ``size_required`` (a sized product was bought without a
    size), ``recommended_size``, ``size_options``, and ``warnings`` (a list of
    {kind, message} the buyer must acknowledge to proceed).
    """
    out = {
        "size_required": False,
        "recommended_size": None,
        "size_options": [],
        "warnings": [],
    }

    guide = fit_guide(user, product)
    if guide.get("sized"):
        out["size_options"] = guide.get("size_options", [])
        out["recommended_size"] = guide.get("recommended_size")
        chosen = (chosen_size or "").strip()
        if not chosen:
            out["size_required"] = True
            return out
        rec = guide.get("recommended_size")
        if rec and chosen != str(rec):
            out["warnings"].append(
                {
                    "kind": "size",
                    "message": (
                        f"Size {chosen} may not be your best fit — we recommend {rec}."
                    ),
                }
            )

    compat = get_compat(user, product)
    if not compat.get("compatible"):
        out["warnings"].append(
            {
                "kind": "compat",
                "message": compat.get("warning")
                or "This may not be compatible with items you own.",
            }
        )
    return out
