"""Smoke test: photo_urls works for local storage (and would for S3).

Run inside the backend container:
    docker compose cp .\\smoke_photo_urls.py backend:/app/
    docker compose exec backend python /app/smoke_photo_urls.py
"""
import io
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.test import Client  # noqa: E402
from PIL import Image  # noqa: E402

from marketplace.models import Listing, Order  # noqa: E402

PASS = "demo1234"


def png(name):
    img = Image.new("RGB", (48, 48), (200, 60, 60))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    buf.name = name
    return buf


def main():
    print(f"USE_S3={settings.USE_S3}  default storage={settings.STORAGES['default']['BACKEND']}")

    c = Client()
    assert c.login(username="rahul", password=PASS), "rahul login failed"

    # find a DELIVERED order owned by rahul to resell with photos
    order = (
        Order.objects.filter(buyer__username="rahul", state="DELIVERED")
        .select_related("listing__unit")
        .first()
    )
    assert order, "no DELIVERED order for rahul — reseed?"

    r = c.post(
        "/api/resale",
        {"order_id": order.id, "photos": [png("a.png"), png("b.png")]},
    )
    print(f"[1] resale with photos -> {r.status_code}")
    assert r.status_code == 201, r.content[:300]
    data = r.json()
    assert len(data["photos"]) == 2, data["photos"]
    assert len(data["photo_urls"]) == 2, data
    assert all(u.startswith(settings.MEDIA_URL) for u in data["photo_urls"]), data["photo_urls"]
    print(f"    photos={data['photos']}")
    print(f"    photo_urls={data['photo_urls']}")

    # each URL must actually serve
    for u in data["photo_urls"]:
        resp = c.get(u)
        print(f"[2] GET {u} -> {resp.status_code}")
        assert resp.status_code == 200

    # the public product page must include photo_urls on the listing
    listing = Listing.objects.get(pk=data["id"])
    r = c.get(f"/api/products/{listing.unit.product_id}")
    pl = [l for l in r.json()["listings"] if l["id"] == listing.id]
    assert pl and pl[0]["photo_urls"] == data["photo_urls"], "photo_urls missing on product page"
    print("[3] product page exposes photo_urls -> True")

    print("\nALL PHOTO URL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
