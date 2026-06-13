"""Public entry points for kicking off grading from views.

Keeps views thin: build the assessment + its image rows (buyer uploads as
UPLOADED, the listing/product photos as REFERENCE) and enqueue the async run.
Reference photos are what we compare uploads against for similarity/fraud.
"""

import logging

from .models import AssessmentContext, AssessmentStatus, GradingAssessment, GradingImage, ImageRole

log = logging.getLogger(__name__)


def _reference_paths(order) -> list:
    """Listed photos for this unit: the listing's photos + the product image."""
    paths = list(order.listing.photos or [])
    product = order.listing.unit.product
    if product.image:
        try:
            name = product.image.name
            if name and name not in paths:
                paths.append(name)
        except Exception:  # noqa: BLE001
            pass
    return paths


def create_return_assessment(order, uploaded_paths, client_metadatas=None):
    """Create a PENDING assessment for a return and enqueue async grading.

    `uploaded_paths`     : list of stored buyer photo paths.
    `client_metadatas`   : optional list of per-photo EXIF dicts, index-aligned.
    Returns the GradingAssessment (or None if it could not be created/enqueued).
    """
    client_metadatas = client_metadatas or []
    unit = order.listing.unit

    assessment = GradingAssessment.objects.create(
        unit=unit,
        order=order,
        triggered_by=order.buyer,
        context=AssessmentContext.RETURN,
        status=AssessmentStatus.PENDING,
    )

    images = []
    for i, path in enumerate(uploaded_paths):
        meta = client_metadatas[i] if i < len(client_metadatas) else {}
        images.append(
            GradingImage(
                assessment=assessment,
                path=path,
                role=ImageRole.UPLOADED,
                client_metadata=meta if isinstance(meta, dict) else {},
            )
        )
    for path in _reference_paths(order):
        images.append(
            GradingImage(assessment=assessment, path=path, role=ImageRole.REFERENCE)
        )
    if images:
        GradingImage.objects.bulk_create(images)

    # Import here to avoid importing Celery at module import time in code paths
    # (e.g. migrations) that only need the service helpers.
    from .tasks import run_assessment

    try:
        run_assessment.delay(assessment.id)
    except Exception:  # noqa: BLE001 — broker down shouldn't break the return
        log.exception("could not enqueue grading for assessment %s", assessment.id)

    return assessment
