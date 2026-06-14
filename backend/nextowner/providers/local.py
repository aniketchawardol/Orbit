"""Local sentence-transformers embedder (CPU).

Loads a MiniLM model once per process (lazy singleton) and encodes text to
normalized vectors. Intended to run in the Celery worker, where vectors are
precomputed in parallel — never in the web request path. Importing
sentence-transformers is deferred to construction time so the web process and
the mock path never pull in torch.
"""

import logging
import threading

from django.conf import settings

from .base import TextEmbeddingProvider

log = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()


def _load():
    """Load (once) and cache the SentenceTransformer model. Raises on failure so
    the registry can fall back to the mock provider."""
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer  # heavy: lazy

            name = getattr(
                settings, "NEXTOWNER_EMBEDDING_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2",
            )
            log.info("loading local embedding model %s", name)
            _model = SentenceTransformer(name)
    return _model


class LocalTextEmbedding(TextEmbeddingProvider):
    name = "local"

    def __init__(self):
        model = _load()
        self.dim = 384  # MiniLM default
        for attr in ("get_embedding_dimension", "get_sentence_embedding_dimension"):
            fn = getattr(model, attr, None)
            if callable(fn):
                try:
                    self.dim = int(fn())
                    break
                except Exception:  # noqa: BLE001
                    continue

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = _load()
        vecs = model.encode(
            [t or "" for t in texts],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [v.tolist() for v in vecs]
