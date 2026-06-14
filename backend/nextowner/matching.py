"""Bipartite buyer <-> product matching.

We score every candidate buyer against the resale product, build a weighted
bipartite graph (networkx), then rank buyers and bucket them into alert tiers for
the Dutch auction. The edge weight blends five demand signals (weights in
settings.NEXTOWNER_MATCH_WEIGHTS):

    w(u, p) = a * semantic(taste_u, vec_p)      # learned taste (cosine -> [0,1])
            + b * category_affinity_u(p)        # revealed category preference
            + c * price_fit(price_p; budget_u)  # Gaussian budget kernel
            + d * quality_fit(grade_p)          # condition acceptability
            + e * green_propensity_u            # appetite for pre-loved goods

This goes beyond naive text similarity: it encodes budget, condition tolerance,
and sustainability appetite (revealed preference), not just "similar description".
"""

import logging
import math

from django.conf import settings
from django.contrib.auth import get_user_model

from core.models import Roles

from .embeddings import cosine01
from .products import get_product_vector
from .profiles import get_demand_profile

log = logging.getLogger(__name__)
User = get_user_model()

# Everyone prefers better condition; weight it so grade still matters per item.
_GRADE_FIT = {"A": 1.0, "B": 0.8, "C": 0.55, "D": 0.3}


def _price_fit(profile, price) -> float:
    mean = getattr(profile, "price_mean", 0.0) or 0.0
    if mean <= 0:
        return 0.5  # cold start: no budget signal -> neutral
    std = getattr(profile, "price_std", 0.0) or 0.0
    scale = std if std > 1.0 else max(1.0, 0.5 * mean)  # widen if std tiny/zero
    z = (float(price) - mean) / scale
    return math.exp(-0.5 * z * z)


def score_edge(profile, product, product_vec, price, grade) -> tuple[float, dict]:
    """Return (score, components) for one buyer<->product pair. `profile` may be a
    cold-start/neutral DemandProfile."""
    weights = settings.NEXTOWNER_MATCH_WEIGHTS
    taste = getattr(profile, "taste_vector", None) or []
    semantic = cosine01(taste, product_vec) if taste else 0.5  # neutral for cold start
    cat = (product.category or "").strip().lower()
    category = (getattr(profile, "category_affinity", {}) or {}).get(cat, 0.0)
    price_fit = _price_fit(profile, price)
    quality = _GRADE_FIT.get((grade or "").upper(), 0.6)
    green = getattr(profile, "green_propensity", 0.0) or 0.0

    components = {
        "semantic": round(semantic, 4),
        "category": round(category, 4),
        "price": round(price_fit, 4),
        "quality": round(quality, 4),
        "green": round(green, 4),
    }
    score = (
        weights["semantic"] * semantic
        + weights["category"] * category
        + weights["price"] * price_fit
        + weights["quality"] * quality
        + weights["green"] * green
    )
    return round(score, 6), components


def candidate_buyers_for(seller_id, owner_id, city=None) -> list:
    """Eligible buyers given the seller/owner to exclude and an optional city
    filter. Used both from a listing and from the pre-listing precompute step."""
    qs = User.objects.filter(role=Roles.BUYER)
    if seller_id:
        qs = qs.exclude(pk=seller_id)
    if owner_id:
        qs = qs.exclude(pk=owner_id)
    if city:
        qs = qs.filter(city__iexact=city)
    return list(qs)


def candidate_buyers(listing) -> list:
    """Buyers eligible to be matched: role=BUYER, excluding the seller and the
    current owner. For the demo, all buyers count as same-locality; otherwise we
    restrict to the seller's city (NEXTOWNER_SAME_LOCALITY_DEMO=0)."""
    city = None
    if not getattr(settings, "NEXTOWNER_SAME_LOCALITY_DEMO", True):
        city = (getattr(listing.lister, "city", "") or "").strip() or None
    return candidate_buyers_for(listing.lister_id, listing.unit.owner_id, city)


def build_match_graph(listing, buyers=None):
    """Build the weighted bipartite graph (one product node, N buyer nodes) and
    return (graph, ranked_edges). Ranked edges are dicts sorted by score desc."""
    import networkx as nx

    product = listing.unit.product
    product_vec = get_product_vector(product)
    grade = listing.unit.grade
    price = listing.price
    buyers = candidate_buyers(listing) if buyers is None else buyers

    graph = nx.Graph()
    pnode = f"p:{product.id}"
    graph.add_node(pnode, kind="product", title=product.title)

    ranked = []
    for buyer in buyers:
        profile = get_demand_profile(buyer)
        score, components = score_edge(profile, product, product_vec, price, grade)
        unode = f"u:{buyer.id}"
        graph.add_node(unode, kind="buyer", username=buyer.username)
        graph.add_edge(pnode, unode, weight=score, components=components)
        ranked.append({"buyer": buyer, "score": score, "components": components})

    ranked.sort(key=lambda e: e["score"], reverse=True)
    return graph, ranked


def top_buyers(listing, k=None) -> list:
    """Top-k matched buyers for a listing, each tagged with a 0-based rank and an
    alert `tier` (tier size from settings). k defaults to tier_size * max_tier."""
    tier_size = settings.NEXTOWNER_AUCTION_TIER_SIZE
    max_tier = settings.NEXTOWNER_AUCTION_MAX_TIER
    if k is None:
        k = tier_size * max_tier

    _, ranked = build_match_graph(listing)
    out = []
    for rank, edge in enumerate(ranked[:k]):
        edge["rank"] = rank
        edge["tier"] = min(rank // tier_size, max_tier - 1)
        out.append(edge)
    return out
