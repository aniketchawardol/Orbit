"""Resale pricing.

Turns the grader's quality/fraud/confidence verdict plus the item's original
price into an estimated value and a price band, via:

    est_value = P0 * [rho_min + (rho_max - rho_min) * quality^gamma]   (quality)
                   * (1 - d_category)^months                           (depreciation)
                   * (1 - lambda * fraud)                              (fraud penalty)

    band = est_value * (1 +/- band_width * (1 - confidence))

The band ceiling seeds the Dutch auction's starting price; the floor doubles as
the seller's reserve. All knobs live in settings (NEXTOWNER_PRICE_*).
"""

from django.conf import settings


def _clamp01(x) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, x))


def depreciation_factor(category, months) -> float:
    rates = settings.NEXTOWNER_DEPRECIATION_BY_CATEGORY
    d = rates.get((category or "").strip().lower(), settings.NEXTOWNER_DEPRECIATION_DEFAULT)
    months = max(0.0, float(months or 0))
    return (1.0 - d) ** months


def auction_bounds(est_value) -> dict:
    """Descending-auction range around the fair value: the opening ask sits a
    premium ABOVE est_value and the reserve a discount BELOW it. Deliberately
    wider than the pricing band so the Dutch price can step down several times
    instead of snapping straight to the reserve."""
    est = max(0, int(est_value or 0))
    premium = settings.NEXTOWNER_AUCTION_START_PREMIUM
    discount = settings.NEXTOWNER_AUCTION_RESERVE_DISCOUNT
    ceiling = int(round(est * (1.0 + premium)))
    floor = int(round(est * (1.0 - discount)))
    floor = max(0, min(floor, ceiling))
    return {"ceiling": ceiling, "floor": floor}



def price_resale(*, original_price, quality, fraud, confidence, category, age_months) -> dict:
    """Return {est_value, band_lo, band_hi, ceiling, floor, factors}."""
    p0 = max(0.0, float(original_price or 0))
    q = _clamp01(quality if quality is not None else 0.5)
    f = _clamp01(fraud or 0.0)
    c = _clamp01(confidence if confidence is not None else 0.6)

    rho_min = settings.NEXTOWNER_PRICE_RHO_MIN
    rho_max = settings.NEXTOWNER_PRICE_RHO_MAX
    gamma = settings.NEXTOWNER_PRICE_GAMMA
    lam = settings.NEXTOWNER_PRICE_FRAUD_LAMBDA
    band_w = settings.NEXTOWNER_PRICE_BAND_WIDTH

    quality_realization = rho_min + (rho_max - rho_min) * (q ** gamma)
    delta = depreciation_factor(category, age_months)
    fraud_penalty = max(0.0, 1.0 - lam * f)
    est_value = int(round(p0 * quality_realization * delta * fraud_penalty))

    spread = band_w * (1.0 - c)
    band_lo = max(0, min(int(round(est_value * (1.0 - spread))), est_value))
    band_hi = max(int(round(est_value * (1.0 + spread))), est_value)
    return {
        "est_value": est_value,
        "band_lo": band_lo,
        "band_hi": band_hi,
        "ceiling": band_hi,
        "floor": band_lo,
        "factors": {
            "p0": p0,
            "quality": round(q, 4),
            "quality_realization": round(quality_realization, 4),
            "depreciation": round(delta, 4),
            "fraud_penalty": round(fraud_penalty, 4),
            "confidence": round(c, 4),
            "category": category,
            "age_months": age_months,
        },
    }
