"""Deterministic mock embedder — no torch, no network.

Hashes the text into a fixed-dim unit vector. The same text always maps to the
same vector, and lexically-overlapping texts share tokens (so they land closer
together than unrelated texts). Good enough to exercise the whole matching +
auction pipeline in tests and offline demos without downloading a model.
"""

import hashlib
import math
import re

from django.conf import settings

from .base import TextEmbeddingProvider

_TOKEN = re.compile(r"[a-z0-9]+")


def _dim() -> int:
    return int(getattr(settings, "NEXTOWNER_MOCK_EMBEDDING_DIM", 64))


class MockTextEmbedding(TextEmbeddingProvider):
    name = "mock"

    def __init__(self):
        self.dim = _dim()

    def _vec(self, text: str) -> list[float]:
        dim = self.dim
        v = [0.0] * dim
        tokens = _TOKEN.findall((text or "").lower()) or ["∅"]
        for tok in tokens:
            # Hash each token to a slot + sign; accumulating tokens makes texts
            # that share words point in similar directions (a crude bag-of-words
            # embedding) while staying fully deterministic.
            h = hashlib.sha1(tok.encode("utf-8")).digest()
            slot = int.from_bytes(h[:4], "big") % dim
            sign = 1.0 if h[4] & 1 else -1.0
            weight = 1.0 + (h[5] / 255.0)
            v[slot] += sign * weight
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]
