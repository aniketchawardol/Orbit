"""Celery tasks for return prevention.

Precompute accessory-compatibility verdicts in PARALLEL when a user logs in, so
the result is warm in the cache before they open a product. Each task reads what
it needs off ids (tiny broker payloads) and writes the verdict into the shared
Redis cache via ``services.get_compat(..., force=True)``.

Eager mode (CELERY_TASK_ALWAYS_EAGER, used by tests / no-broker demos) runs
everything inline as plain function calls.
"""

import logging

from celery import group, shared_task
from django.conf import settings

log = logging.getLogger(__name__)


def _eager() -> bool:
    return bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False))


@shared_task(name="returnprevention.compute_compat")
def compute_compat_task(user_id, product_id):
    """Compute + cache one (user, product) compatibility verdict."""
    from django.contrib.auth import get_user_model
    from catalog.models import Product

    from . import services

    try:
        user = get_user_model().objects.get(pk=user_id)
        product = Product.objects.get(pk=product_id)
        services.get_compat(user, product, force=True)
    except Exception:  # noqa: BLE001 — a single failure must not sink the group
        log.exception("compute_compat failed for user %s product %s", user_id, product_id)
    return product_id


@shared_task(name="returnprevention.precompute_for_user")
def precompute_for_user(user_id):
    """Fan out a compatibility precompute for every purchasable accessory.

    Called best-effort right after login so verdicts are cached before the user
    browses. Bounded to accessories only, so the fan-out stays small."""
    from . import services

    product_ids = services.accessory_product_ids()
    if not product_ids:
        return
    if _eager():
        for pid in product_ids:
            compute_compat_task(user_id, pid)
        return
    group(compute_compat_task.s(user_id, pid) for pid in product_ids).apply_async()
