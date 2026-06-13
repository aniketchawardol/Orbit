"""Smoke test: end-to-end async return grading through the REAL Celery chord.

Unlike the unit tests (which run eager), this enqueues the assessment via
Redis so the running `worker` service executes the parallel
group(vlm, similarity, metadata, history) -> aggregate chord and writes the
blended scores back to the DB. The VLM resolves to the mock provider when no
API key is configured, so this needs no network.

Run with the stack up (db, redis, worker, backend):
    docker compose cp smoke_grading.py backend:/app/
    docker compose exec backend python /app/smoke_grading.py
"""
import io
import os
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.core.files.base import ContentFile  # noqa: E402
from django.core.files.storage import default_storage  # noqa: E402
from django.utils import timezone  # noqa: E402
from PIL import Image  # noqa: E402

from catalog.models import ItemUnit, Product, UnitStates  # noqa: E402
from core.models import User  # noqa: E402
from grading.models import AssessmentStatus, GradingAssessment  # noqa: E402
from grading.services import create_return_assessment  # noqa: E402
from marketplace.models import (  # noqa: E402
    Listing,
    ListingSources,
    Order,
    OrderStates,
)


def _png(color, size=(96, 96)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def main():
    stamp = timezone.now().strftime("%H%M%S%f")
    seller = User.objects.create_user(f"smoke_seller_{stamp}", password="x")
    buyer = User.objects.create_user(f"smoke_buyer_{stamp}", password="x")

    product = Product.objects.create(
        title="Smoke Earbuds",
        category="electronics",
        mrp=4999,
        seller=seller,
        attributes={"brand": "Acme", "color": "black"},
    )
    unit = ItemUnit.objects.create(
        product=product, owner=buyer, state=UnitStates.SOLD
    )

    ref_path = default_storage.save(
        f"listings/smoke_ref_{stamp}.png", ContentFile(_png((120, 120, 120)))
    )
    listing = Listing.objects.create(
        unit=unit,
        source=ListingSources.NEW,
        price=4999,
        photos=[ref_path],
        lister=seller,
    )
    order = Order.objects.create(
        buyer=buyer,
        listing=listing,
        state=OrderStates.DELIVERED,
        delivered_at=timezone.now(),
        return_reason="DEFECTIVE",
    )

    up_path = default_storage.save(
        f"returns/smoke_up_{stamp}.jpg", ContentFile(_png((118, 122, 119)))
    )
    order.photos = [up_path]
    order.save(update_fields=["photos"])

    meta = [{"Make": "Apple", "Model": "iPhone", "originalWidth": 96, "originalHeight": 96}]
    assessment = create_return_assessment(order, [up_path], client_metadatas=meta)
    print(f"[1] enqueued assessment #{assessment.id} status={assessment.status}")

    # Poll the DB while the worker processes the chord (no network; mock VLM).
    deadline = time.time() + 60
    a = assessment
    while time.time() < deadline:
        a = GradingAssessment.objects.get(pk=assessment.id)
        if a.status in (AssessmentStatus.DONE, AssessmentStatus.FAILED):
            break
        time.sleep(1)

    print(f"[2] final status={a.status} provider={a.vlm_provider}/{a.embedding_provider}")
    assert a.status == AssessmentStatus.DONE, f"assessment did not finish: {a.error}"
    assert a.fraud_score is not None, "fraud_score missing"
    assert a.quality_score is not None, "quality_score missing"
    assert a.suggested_grade in ("A", "B", "C", "D"), a.suggested_grade
    assert "fraud" in a.scores, "scores breakdown missing"

    print(
        f"    fraud={a.fraud_score} quality={a.quality_score} "
        f"confidence={a.confidence} grade={a.suggested_grade}"
    )
    print(f"    images: {a.images.count()} (uploaded+reference)")
    print(f"    fraud signals: {a.scores['fraud'].get('signals')}")
    print("OK")


if __name__ == "__main__":
    main()
