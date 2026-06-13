"""Provider interfaces for the return grader.

Two pluggable provider kinds:
- VLMProvider:        looks at the images + context, returns a structured verdict.
- EmbeddingProvider:  compares uploaded vs reference images for similarity
                      (tamper / wrong-item / fraud signal).

Concrete providers live alongside this module; `registry` resolves which one to
use from settings so adding a provider is configuration, not new call sites.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class GradingImageData:
    """An image plus the bytes a provider needs to inspect it."""

    path: str
    data: bytes
    mime: str = "image/jpeg"
    role: str = "UPLOADED"  # UPLOADED | REFERENCE


@dataclass
class VLMRequest:
    """Everything the VLM needs to grade one return, from multiple sources."""

    product: dict = field(default_factory=dict)  # title, category, description, attributes, mrp
    claim: dict = field(default_factory=dict)     # reason, comment, claimed_untouched
    uploaded: list = field(default_factory=list)  # list[GradingImageData]
    reference: list = field(default_factory=list)  # list[GradingImageData]


class VLMProvider(ABC):
    name = "base"

    @abstractmethod
    def grade(self, req: VLMRequest) -> dict:
        """Return a normalized VLM verdict dict (see prompts.normalize_vlm_output)."""
        raise NotImplementedError


class EmbeddingProvider(ABC):
    name = "base"

    @abstractmethod
    def compare(self, uploaded: list, reference: list) -> dict:
        """Compare uploaded vs reference images.

        Args take list[GradingImageData]. Returns:
        {
          "overall": float 0..1,            # best-case match of uploads to refs
          "per_image": [{"path", "best_similarity", "phash"}],
          "reference_phashes": [str],
          "duplicate_pairs": [[path, path]],  # near-identical uploads (reuse fraud)
          "source": str,
        }
        """
        raise NotImplementedError
