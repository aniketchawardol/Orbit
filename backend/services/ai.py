"""Deterministic mock grading/pricing helpers.

These are intentionally network-free, stable fakes used for lightweight
estimates (legacy grade/price) and the fit-check hint. The real, image-aware
AI grading + routing lives in the `grading` and `rerouting` apps (Gemini via
`LLM_PROVIDERS`/`GEMINI_API_KEY`); this module is never the place to add a
real provider.

Views/commands import grade(), price() and fit_check() only.
"""

import hashlib
import logging

log = logging.getLogger(__name__)

GRADES = ["A", "B", "C", "D"]
# resale value as % of MRP by grade
GRADE_VALUE_PCT = {"A": 70, "B": 55, "C": 35, "D": 15}


def _stable_int(seed: str) -> int:
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16)


def _mock_grade(product_id, untouched=False, image_paths=None):
    if untouched:
        return {"grade": "A", "confidence": 0.99, "source": "mock"}
    # Photos sharpen mock confidence a little — visible feedback in the demo.
    n_photos = len(image_paths or [])
    g = GRADES[_stable_int(f"grade:{product_id}") % 3]  # A/B/C; D reserved for the grading app
    conf = 0.80 + (_stable_int(f"conf:{product_id}") % 13) / 100 + min(n_photos, 5) * 0.01
    return {"grade": g, "confidence": round(min(conf, 0.99), 2), "source": "mock"}


def _mock_price(mrp, grade):
    value = mrp * GRADE_VALUE_PCT.get(grade, 30) // 100
    return {
        "est_value": value,
        "band_lo": int(value * 0.85),
        "band_hi": int(value * 1.10),
        "source": "mock",
    }


def grade(product_id, untouched=False, image_paths=None):
    """→ {grade, confidence, source}"""
    return _mock_grade(product_id, untouched, image_paths)


def price(product_id, mrp, grade_letter):
    """→ {est_value, band_lo, band_hi, source}"""
    return _mock_price(mrp, grade_letter)


def fit_check(product_id, category):
    """Return a fit hint for product categories where fit matters.
    Deterministic mock based on product_id hash so results are stable.
    Returns {hint, confidence} or {hint: None}.
    """
    if category is None:
        return {"hint": None}
    h = _stable_int(f"fit:{product_id}") % 100
    if category.lower() == "footwear":
        # Runs small / big depending on hash
        if h % 2 == 0:
            return {"hint": "Runs small — 78% of buyers with similar profiles chose one size up.", "confidence": 0.78, "source": "mock"}
        else:
            return {"hint": "Comfortable on average — most buyers reported true-to-size fit.", "confidence": 0.65, "source": "mock"}
    if category.lower() in ("apparel", "clothing"):
        if h % 3 == 0:
            return {"hint": "Slim fit — consider sizing up if you prefer a relaxed fit.", "confidence": 0.72, "source": "mock"}
        return {"hint": None}
    # Electronics and others: no fit hint
    return {"hint": None}
