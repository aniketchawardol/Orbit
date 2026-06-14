"""Build and cache a product's text embedding (the supply side of matching)."""

import logging

from .embeddings import embed_text, provider_name
from .models import ProductVector

log = logging.getLogger(__name__)


def product_text(product) -> str:
    """Compose the text we embed for a product: title, category, brand, then the
    description and any remaining structured attributes."""
    attrs = product.attributes or {}
    brand = str(attrs.get("brand", "")).strip()
    parts = [product.title or "", product.category or "", brand, product.description or ""]
    for key, value in attrs.items():
        if key == "brand":
            continue
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            parts.append(f"{key} {value}")
    return " ".join(p for p in parts if p).strip()


def build_product_vector(product, force=False) -> ProductVector:
    """Embed the product text and upsert its ProductVector cache."""
    name = provider_name()
    existing = ProductVector.objects.filter(product=product).first()
    if existing and not force and existing.provider == name and existing.text_vector:
        return existing
    vector = embed_text(product_text(product))
    obj, _ = ProductVector.objects.update_or_create(
        product=product,
        defaults={"text_vector": vector, "dim": len(vector), "provider": name},
    )
    return obj


def get_product_vector(product) -> list:
    """Cached vector for a product, building it on demand if missing."""
    pv = ProductVector.objects.filter(product=product).first()
    if pv and pv.text_vector and pv.provider == provider_name():
        return pv.text_vector
    return build_product_vector(product).text_vector
