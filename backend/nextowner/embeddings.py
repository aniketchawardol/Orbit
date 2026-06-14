"""Embedding facade + vector math.

Thin wrappers over the resolved provider plus pure-Python vector helpers (cosine,
weighted mean). Kept numpy-free so the web process and the mock path stay light;
the only heavy import (torch) lives behind the `local` provider.
"""

import math

from .providers import get_text_embedding_provider


def embed_texts(texts: list[str]) -> list[list[float]]:
    provider = get_text_embedding_provider()
    return provider.embed(texts)


def embed_text(text: str) -> list[float]:
    provider = get_text_embedding_provider()
    return provider.embed_one(text)


def provider_name() -> str:
    return get_text_embedding_provider().name


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]. Returns 0.0 if either side is empty or the
    dims don't match (e.g. a profile built by a different embedder)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def cosine01(a: list[float], b: list[float]) -> float:
    """Cosine remapped to [0, 1] for use as a non-negative match weight."""
    return (cosine(a, b) + 1.0) / 2.0


def weighted_mean(vectors: list[list[float]], weights: list[float]) -> list[float]:
    """Weighted average of equal-length vectors -> a unit vector ([] if empty)."""
    rows = [(v, w) for v, w in zip(vectors, weights) if v and w > 0]
    if not rows:
        return []
    dim = len(rows[0][0])
    acc = [0.0] * dim
    total = 0.0
    for v, w in rows:
        if len(v) != dim:
            continue
        for i in range(dim):
            acc[i] += v[i] * w
        total += w
    if total <= 0.0:
        return []
    acc = [x / total for x in acc]
    norm = math.sqrt(sum(x * x for x in acc)) or 1.0
    return [x / norm for x in acc]
