"""Celery tasks for the Next Best Owner engine.

Three jobs:
1. Parallel embedding precompute (`precompute_vectors`, the per-item tasks) so
   product/demand vectors are warm before matching — fanned out with a group.
2. The grading -> pricing handoff (`price_and_match`), which precomputes the
   candidate buyers' profiles IN PARALLEL via a chord, then finalizes pricing +
   matching + the first alert.
3. The self-rescheduling Dutch stepper (`step_auction`).

Eager mode (CELERY_TASK_ALWAYS_EAGER, used by tests / no-broker demos) runs
everything inline and does NOT auto-advance the auction — the demo/test drives
each price step explicitly.
"""

import logging

from celery import chord, group, shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import auction as auction_mod
from .models import AuctionStatus, ResaleAuction, ResaleRequest, ResaleStatus

log = logging.getLogger(__name__)


def _eager() -> bool:
    return bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False))


# --------------------------------------------------------------------------- #
# Embedding precompute (parallel fan-out)
# --------------------------------------------------------------------------- #
@shared_task(name="nextowner.build_product_vector")
def build_product_vector_task(product_id):
    from catalog.models import Product

    from .products import build_product_vector

    try:
        build_product_vector(Product.objects.get(pk=product_id), force=True)
    except Exception:  # noqa: BLE001
        log.exception("build_product_vector failed for product %s", product_id)
    return product_id


@shared_task(name="nextowner.build_demand_profile")
def build_demand_profile_task(user_id):
    from django.contrib.auth import get_user_model

    from .profiles import build_demand_profile

    try:
        build_demand_profile(get_user_model().objects.get(pk=user_id), force=True)
    except Exception:  # noqa: BLE001
        log.exception("build_demand_profile failed for user %s", user_id)
    return user_id


@shared_task(name="nextowner.precompute_vectors")
def precompute_vectors(product_ids=None, user_ids=None):
    """Precompute product vectors + demand profiles in PARALLEL (one task each).
    Used to warm the cache before a matching run (e.g. the demo page)."""
    product_ids = list(product_ids or [])
    user_ids = list(user_ids or [])
    if _eager():
        for pid in product_ids:
            build_product_vector_task(pid)
        for uid in user_ids:
            build_demand_profile_task(uid)
        return
    sigs = [build_product_vector_task.s(pid) for pid in product_ids]
    sigs += [build_demand_profile_task.s(uid) for uid in user_ids]
    if sigs:
        group(sigs).apply_async()


# --------------------------------------------------------------------------- #
# Grading -> pricing + matching handoff
# --------------------------------------------------------------------------- #
def _city_for(rr):
    if getattr(settings, "NEXTOWNER_SAME_LOCALITY_DEMO", True):
        return None
    return (getattr(rr.seller, "city", "") or "").strip() or None


@shared_task(name="nextowner.price_and_match")
def price_and_match(assessment_id):
    """Entry point from grading. Precomputes the product vector + every candidate
    buyer's demand profile in parallel (chord), then finalizes pricing/matching."""
    from grading.models import GradingAssessment

    from . import matching

    try:
        assessment = GradingAssessment.objects.select_related("unit__product").get(pk=assessment_id)
    except GradingAssessment.DoesNotExist:
        log.warning("price_and_match: assessment %s gone", assessment_id)
        return

    rr = (
        ResaleRequest.objects.select_related("seller")
        .filter(unit=assessment.unit, status=ResaleStatus.PENDING)
        .order_by("-id")
        .first()
    )
    if rr is None:
        log.info("price_and_match: no pending resale request for unit %s", assessment.unit_id)
        return

    product_id = assessment.unit.product_id
    buyer_ids = [
        b.id for b in matching.candidate_buyers_for(rr.seller_id, assessment.unit.owner_id, _city_for(rr))
    ]

    if _eager():
        build_product_vector_task(product_id)
        for uid in buyer_ids:
            build_demand_profile_task(uid)
        finalize_match(None, assessment_id)
        return

    # Parallel precompute, then finalize once all embeddings are warm.
    header = group(
        build_product_vector_task.s(product_id),
        *[build_demand_profile_task.s(uid) for uid in buyer_ids],
    )
    chord(header)(finalize_match.s(assessment_id))


@shared_task(name="nextowner.finalize_match")
def finalize_match(_precomputed, assessment_id):
    """Callback after parallel precompute: price, list, match, alert tier 0, and
    schedule the first price step."""
    from grading.models import GradingAssessment

    try:
        assessment = GradingAssessment.objects.select_related("unit__product").get(pk=assessment_id)
    except GradingAssessment.DoesNotExist:
        return
    auction = auction_mod.start_auction_for_assessment(assessment)
    if auction is not None:
        _schedule_step(auction)
    return getattr(auction, "id", None)


# --------------------------------------------------------------------------- #
# Dutch auction stepper (self-rescheduling)
# --------------------------------------------------------------------------- #
def _schedule_step(auction):
    """Schedule the next descending step. Eager mode does NOT auto-advance (the
    demo/test triggers each step) to avoid unbounded inline recursion."""
    if _eager():
        return
    try:
        step_auction.apply_async((auction.id,), countdown=auction.interval_seconds)
    except Exception:  # noqa: BLE001
        log.exception("could not schedule step for auction %s", auction.id)


@shared_task(name="nextowner.step_auction")
def step_auction(auction_id, force=False):
    """Lower the auction price one notch and reschedule until sold / floor reached.
    `force` skips the next_step_at guard (used by the demo's manual step button)."""
    with transaction.atomic():
        try:
            auction = ResaleAuction.objects.select_for_update().get(pk=auction_id)
        except ResaleAuction.DoesNotExist:
            return
        if auction.status != AuctionStatus.ACTIVE:
            return
        if not force and auction.next_step_at and timezone.now() < auction.next_step_at:
            _schedule_step(auction)  # early/duplicate trigger — reschedule to due time
            return
        auction_mod.step(auction)
        still_active = auction.status == AuctionStatus.ACTIVE

    if still_active:
        _schedule_step(auction)


# --------------------------------------------------------------------------- #
# Demo "Start matching" orchestration
# --------------------------------------------------------------------------- #
@shared_task(name="nextowner.rematch_auctions")
def rematch_auctions(_precomputed, auction_ids):
    """Rebuild matches for a set of auctions (chord callback after precompute)."""
    for aid in auction_ids:
        try:
            auction = ResaleAuction.objects.select_related("listing__unit__product").get(pk=aid)
        except ResaleAuction.DoesNotExist:
            continue
        if auction.status == AuctionStatus.ACTIVE:
            auction_mod.rematch(auction)
    return auction_ids


@shared_task(name="nextowner.run_demo_match")
def run_demo_match(auction_ids):
    """Demo 'Start matching': precompute product + buyer embeddings in PARALLEL,
    then (re)match each auction so buyers populate the cards. Eager runs inline."""
    from . import matching

    auctions = list(
        ResaleAuction.objects.select_related("unit", "seller").filter(
            pk__in=auction_ids, status=AuctionStatus.ACTIVE
        )
    )
    if not auctions:
        return []

    ids = [a.id for a in auctions]
    product_ids = sorted({a.unit.product_id for a in auctions})
    buyer_ids = set()
    for a in auctions:
        city = None
        if not getattr(settings, "NEXTOWNER_SAME_LOCALITY_DEMO", True):
            city = (getattr(a.seller, "city", "") or "").strip() or None
        for b in matching.candidate_buyers_for(a.seller_id, a.unit.owner_id, city):
            buyer_ids.add(b.id)
    buyer_ids = sorted(buyer_ids)

    if _eager():
        for pid in product_ids:
            build_product_vector_task(pid)
        for uid in buyer_ids:
            build_demand_profile_task(uid)
        rematch_auctions(None, ids)
        return ids

    header = group(
        *[build_product_vector_task.s(pid) for pid in product_ids],
        *[build_demand_profile_task.s(uid) for uid in buyer_ids],
    )
    chord(header)(rematch_auctions.s(ids))
    return ids
