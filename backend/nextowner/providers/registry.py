"""Resolve the text-embedding provider from settings (never raises).

NEXTOWNER_EMBEDDING_PROVIDER in {local, mock}. "local" needs sentence-transformers;
if it can't be imported/loaded we log and fall back to the deterministic mock so
matching always works (a degraded similarity beats a 500). The resolved provider
is cached per-process.
"""

import logging

from django.conf import settings

from . import mock
from .base import TextEmbeddingProvider

log = logging.getLogger(__name__)

_provider: TextEmbeddingProvider | None = None
_provider_key: str | None = None


def get_text_embedding_provider() -> TextEmbeddingProvider:
    global _provider, _provider_key
    choice = (getattr(settings, "NEXTOWNER_EMBEDDING_PROVIDER", "local") or "local").lower()
    if _provider is not None and _provider_key == choice:
        return _provider

    provider: TextEmbeddingProvider
    if choice == "local":
        try:
            from . import local

            provider = local.LocalTextEmbedding()
        except Exception:  # noqa: BLE001 — model/torch missing -> deterministic mock
            log.warning(
                "local embedding provider unavailable; falling back to mock", exc_info=True
            )
            provider = mock.MockTextEmbedding()
    else:
        provider = mock.MockTextEmbedding()

    _provider, _provider_key = provider, choice
    return provider


def reset_cache() -> None:
    """Drop the cached provider (used by tests that flip the setting)."""
    global _provider, _provider_key
    _provider, _provider_key = None, None
