"""Perceptual-hash image similarity (active embedding provider).

A cheap, dependency-free fraud signal: compare buyer-uploaded photos against the
original listing/reference photos. Low similarity can mean a wrong/substituted
item or doctored images; near-identical uploads can mean a reused photo. Real
CLIP/embedding similarity can be slotted in later behind the same interface.

dHash (difference hash) is robust to mild resize/compression — exactly what our
frontend does — while staying sensitive to content changes.
"""

import logging
from io import BytesIO

from django.conf import settings
from django.core.cache import cache

from . import base

log = logging.getLogger(__name__)

_HASH_W, _HASH_H = 9, 8  # 8x8 = 64-bit dHash
_BITS = _HASH_H * (_HASH_W - 1)
_DUP_THRESHOLD = 0.96  # uploads this similar to each other look reused


def _dhash(data: bytes) -> str:
    """Return a 64-bit difference hash as a 16-char hex string, or "" on failure."""
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as im:
            im = im.convert("L").resize((_HASH_W, _HASH_H))
            px = list(im.getdata())
    except Exception:  # noqa: BLE001 — unreadable image -> no signature
        log.warning("dHash failed for an image; skipping", exc_info=True)
        return ""

    bits = 0
    i = 0
    for row in range(_HASH_H):
        base_idx = row * _HASH_W
        for col in range(_HASH_W - 1):
            left = px[base_idx + col]
            right = px[base_idx + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
            i += 1
    return f"{bits:0{_BITS // 4}x}"


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    dist = bin(int(a, 16) ^ int(b, 16)).count("1")
    return 1.0 - dist / _BITS


def phash_bytes(data: bytes) -> str:
    return _dhash(data)


class PHashEmbedding(base.EmbeddingProvider):
    name = "phash"

    def _ref_phash(self, img: base.GradingImageData) -> str:
        key = f"grading:phash:{img.path}"
        cached = cache.get(key)
        if cached is not None:
            return cached
        h = _dhash(img.data)
        if h:
            cache.set(key, h, getattr(settings, "GRADING_REFERENCE_CACHE_TTL", 86400))
        return h

    def compare(self, uploaded: list, reference: list) -> dict:
        up_hashes = [(u.path, _dhash(u.data)) for u in uploaded]
        ref_hashes = [self._ref_phash(r) for r in reference]
        ref_hashes = [h for h in ref_hashes if h]

        per_image = []
        best_values = []
        for path, h in up_hashes:
            best = None
            if h and ref_hashes:
                best = max(_similarity(h, rh) for rh in ref_hashes)
                best_values.append(best)
            per_image.append(
                {"path": path, "best_similarity": best, "phash": h}
            )

        # Near-duplicate uploads (possible reused photo).
        duplicate_pairs = []
        for i in range(len(up_hashes)):
            for j in range(i + 1, len(up_hashes)):
                hi, hj = up_hashes[i][1], up_hashes[j][1]
                if hi and hj and _similarity(hi, hj) >= _DUP_THRESHOLD:
                    duplicate_pairs.append([up_hashes[i][0], up_hashes[j][0]])

        overall = sum(best_values) / len(best_values) if best_values else None
        return {
            "overall": overall,
            "per_image": per_image,
            "reference_phashes": ref_hashes,
            "duplicate_pairs": duplicate_pairs,
            "source": self.name,
        }
