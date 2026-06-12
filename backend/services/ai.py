"""AI grading/pricing client.

AI_MOCK=1  → deterministic local fakes (no network; uploaded photos accepted
             but unused beyond presence checks).
AI_MOCK=0  → real HTTP calls to AI_SERVICE_URL with base64-encoded images;
             on any failure we fall back to the mock so the site never
             breaks mid-demo.

Views/commands import grade() and price() only — never requests directly.
"""

import base64
import hashlib
import logging

import requests
from django.conf import settings
from django.core.files.storage import default_storage

log = logging.getLogger(__name__)

GRADES = ["A", "B", "C", "D"]
# resale value as % of MRP by grade
GRADE_VALUE_PCT = {"A": 70, "B": 55, "C": 35, "D": 15}


def _stable_int(seed: str) -> int:
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16)


def _encode_images(image_paths, limit=6):
    """Read stored media files → base64 strings for the AI payload."""
    encoded = []
    for rel in (image_paths or [])[:limit]:
        try:
            with default_storage.open(rel, "rb") as fh:
                encoded.append(base64.b64encode(fh.read()).decode())
        except Exception:  # noqa: BLE001 — skip unreadable files, AI gets the rest
            log.warning("Could not read media file %s for AI payload", rel)
    return encoded


def _mock_grade(product_id, untouched=False, image_paths=None):
    if untouched:
        return {"grade": "A", "confidence": 0.99, "source": "mock"}
    # Photos sharpen mock confidence a little — visible feedback in the demo.
    n_photos = len(image_paths or [])
    g = GRADES[_stable_int(f"grade:{product_id}") % 3]  # A/B/C; D only via real AI
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
    if settings.AI_MOCK or not settings.AI_SERVICE_URL:
        return _mock_grade(product_id, untouched, image_paths)
    try:
        resp = requests.post(
            f"{settings.AI_SERVICE_URL}/v1/grade",
            json={
                "product_id": product_id,
                "untouched": untouched,
                "images": _encode_images(image_paths),
            },
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}"},
            timeout=settings.AI_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "grade": data["grade"],
            "confidence": data["confidence"],
            "source": "ai",
        }
    except Exception:  # noqa: BLE001 — any failure → safe fallback
        log.exception("AI grade call failed; using mock fallback")
        return _mock_grade(product_id, untouched, image_paths)


def price(product_id, mrp, grade_letter):
    """→ {est_value, band_lo, band_hi, source}"""
    if settings.AI_MOCK or not settings.AI_SERVICE_URL:
        return _mock_price(mrp, grade_letter)
    try:
        resp = requests.post(
            f"{settings.AI_SERVICE_URL}/v1/price",
            json={"product_id": product_id, "mrp": mrp, "grade": grade_letter},
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}"},
            timeout=settings.AI_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "est_value": data["est_value"],
            "band_lo": data["band_lo"],
            "band_hi": data["band_hi"],
            "source": "ai",
        }
    except Exception:  # noqa: BLE001
        log.exception("AI price call failed; using mock fallback")
        return _mock_price(mrp, grade_letter)
