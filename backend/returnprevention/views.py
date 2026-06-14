import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog.models import Product

from . import services

log = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def product_fitguide(request, pk):
    """Per-user size recommendation for a sized product.

    Also warms the accessory-compatibility cache in the background (best-effort)
    so a subsequent Buy is instant even if the login precompute hasn't finished.
    """
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return Response(status=404)

    guide = services.fit_guide(request.user, product)

    if str((product.attributes or {}).get("compatible_model", "")).strip():
        try:
            from .tasks import compute_compat_task

            compute_compat_task.delay(request.user.id, product.id)
        except Exception:  # noqa: BLE001 — broker hiccup must not break the page
            log.exception("could not warm compat cache for product %s", product.id)

    return Response(guide)
