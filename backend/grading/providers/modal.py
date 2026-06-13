"""Modal-hosted model stubs (future work).

When you deploy your own VLM on Modal it will speak the OpenAI protocol, so the
VLM side reuses `openai_compat.OpenAICompatVLM` with the "modal" entry in
settings.LLM_PROVIDERS — no code here needed. This module is the home for a
future Modal-hosted CLIP embedding provider (real cosine similarity on GPU),
which would replace `phash.PHashEmbedding` behind the same interface.
"""

from . import base


class ModalCLIPEmbedding(base.EmbeddingProvider):
    """Placeholder for serverless-GPU CLIP similarity. Not wired up yet."""

    name = "modal-clip"

    def compare(self, uploaded: list, reference: list) -> dict:
        raise NotImplementedError(
            "Modal CLIP embedding is not implemented yet; use the 'phash' provider."
        )
