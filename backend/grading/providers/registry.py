"""Resolve which providers to use from settings.

Adding/swapping a provider is configuration:
- VLM: settings.GRADING_VLM_PROVIDER in {auto, mock, gemini, openai, modal, bedrock}
  plus the matching entry in settings.LLM_PROVIDERS (base_url/api_key/model).
  "auto" -> first OpenAI-compatible provider that has both an api_key (or base_url)
  and a model, else the mock.
- Embedding/similarity: settings.GRADING_EMBEDDING_PROVIDER in {phash, modal-clip}.
"""

import logging

from django.conf import settings

from . import bedrock, mock, modal, openai_compat, phash

log = logging.getLogger(__name__)

# Which configured LLM_PROVIDERS keys are reachable via the OpenAI-compatible client.
_OPENAI_COMPAT = {"gemini", "openai", "modal"}


def _is_usable(cfg: dict) -> bool:
    if not cfg or not cfg.get("model"):
        return False
    if cfg.get("api_key"):
        return True
    # No key: only a self-hosted endpoint (requires_key=False) is usable, so a
    # hosted provider missing its key cleanly falls back to the mock instead of
    # making a doomed network call.
    return bool(cfg.get("base_url")) and not cfg.get("requires_key", True)


def _build_openai_compat(name: str):
    cfg = (settings.LLM_PROVIDERS or {}).get(name) or {}
    if not _is_usable(cfg):
        return None
    return openai_compat.OpenAICompatVLM(
        name=name,
        base_url=cfg.get("base_url", ""),
        api_key=cfg.get("api_key", ""),
        model=cfg.get("model", ""),
        timeout=getattr(settings, "GRADING_VLM_TIMEOUT", 30.0),
    )


def get_vlm_provider():
    """Return a VLMProvider instance based on settings (never raises)."""
    choice = (getattr(settings, "GRADING_VLM_PROVIDER", "auto") or "auto").lower()

    if choice == "mock":
        return mock.MockVLM()
    if choice == "bedrock":
        try:
            return bedrock.BedrockVLM()
        except Exception:  # noqa: BLE001
            return mock.MockVLM()

    if choice in _OPENAI_COMPAT:
        provider = _build_openai_compat(choice)
        if provider:
            return provider
        log.warning("VLM provider %r not usable (missing key/model); using mock", choice)
        return mock.MockVLM()

    if choice == "auto":
        for name in ("gemini", "openai", "modal"):
            provider = _build_openai_compat(name)
            if provider:
                return provider
        return mock.MockVLM()

    log.warning("Unknown GRADING_VLM_PROVIDER %r; using mock", choice)
    return mock.MockVLM()


def get_embedding_provider():
    """Return an EmbeddingProvider instance based on settings (never raises)."""
    choice = (getattr(settings, "GRADING_EMBEDDING_PROVIDER", "phash") or "phash").lower()
    if choice == "modal-clip":
        try:
            return modal.ModalCLIPEmbedding()
        except Exception:  # noqa: BLE001
            return phash.PHashEmbedding()
    return phash.PHashEmbedding()
