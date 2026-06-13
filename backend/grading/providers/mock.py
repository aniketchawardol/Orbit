"""Deterministic, dependency-free fallback VLM.

Used when no LLM key is configured or a real provider errors out, so the grader
(and the whole return flow) never breaks mid-demo. Output is stable per product
+ reason and is reason-aware so the demo shows believable variation.
"""

import hashlib

from . import base
from .. import prompts

# Defect vocabulary by broad category family.
_DEFECTS = {
    "electronics": ["minor surface scratch", "scuff near port", "light wear on edges"],
    "apparel": ["slight fading", "loose thread", "faint mark"],
    "footwear": ["sole wear", "crease on toe", "minor scuff"],
    "default": ["light cosmetic wear", "minor handling marks"],
}


def _h(seed: str) -> int:
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16)


def _family(category: str) -> str:
    c = (category or "").lower()
    if c in _DEFECTS:
        return c
    if c in ("clothing", "apparel"):
        return "apparel"
    return "default"


class MockVLM(base.VLMProvider):
    name = "mock"

    def grade(self, req: base.VLMRequest) -> dict:
        product = req.product or {}
        claim = req.claim or {}
        category = product.get("category", "")
        reason = str(claim.get("reason", "OTHER")).upper()
        seed = f"{product.get('title','')}:{product.get('id','')}:{reason}"
        h = _h(seed)

        family = _family(category)
        defects_pool = _DEFECTS[family]

        if claim.get("claimed_untouched"):
            grade, quality = "A", 0.95
            defects = []
        elif reason in ("DEFECTIVE",):
            grade = "C" if h % 2 == 0 else "D"
            quality = 0.35 if grade == "C" else 0.2
            defects = defects_pool[: 1 + (h % len(defects_pool))]
        elif reason in ("DIDNT_MATCH", "WRONG_SIZE"):
            grade, quality = "A" if h % 3 else "B", 0.85
            defects = [] if h % 3 else defects_pool[:1]
        else:  # CHANGED_MIND / OTHER
            grade = "A" if h % 2 == 0 else "B"
            quality = 0.9 if grade == "A" else 0.75
            defects = [] if grade == "A" else defects_pool[:1]

        n_up = len(req.uploaded or [])
        per_image = [
            {
                "index": i,
                "visible_defects": defects if i == 0 else [],
                "quality": round(min(0.99, quality + 0.02 * i), 2),
                "notes": "mock inspection",
            }
            for i in range(n_up)
        ]

        # Mock can't truly detect mismatch; assume match unless reason says so.
        matches = reason != "DIDNT_MATCH"

        return prompts.normalize_vlm_output(
            {
                "criteria": _criteria(family),
                "per_image": per_image,
                "defects": defects,
                "item_matches_reference": matches,
                "match_confidence": 0.6 if matches else 0.4,
                "condition_summary": f"Mock grade {grade} for {category or 'item'}.",
                "suggested_grade": grade,
                "quality_estimate": quality,
                "fraud_flags": [] if matches else ["wrong_item"],
                "confidence": 0.6,
                "source": self.name,
            },
            n_uploaded=n_up,
        )


def _criteria(family: str):
    return {
        "electronics": ["scratches", "dents", "cracks", "missing parts"],
        "apparel": ["holes", "stains", "tears", "missing tags"],
        "footwear": ["sole wear", "creasing", "scuffs", "odor"],
        "default": ["cosmetic wear", "functional damage", "completeness"],
    }[family]
