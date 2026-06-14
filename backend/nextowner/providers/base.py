"""Text-embedding provider interface for the matching engine.

Two providers, resolved from settings (config, not call sites):
- mock  : deterministic hash -> unit vector. No torch; used in tests / offline.
- local : sentence-transformers MiniLM on CPU (in the Celery worker).

A provider turns text into a list[float] unit vector. Everything downstream
(profiles, matching) works on plain Python lists, so no provider leaks numpy or
torch types into the ORM or the request path.
"""

from abc import ABC, abstractmethod


class TextEmbeddingProvider(ABC):
    name = "base"
    dim = 0

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into unit-norm vectors (list[list[float]])."""
        raise NotImplementedError

    def embed_one(self, text: str) -> list[float]:
        out = self.embed([text or ""])
        return out[0] if out else []
