"""Smoke test: seller creates a new product with an image.

Run inside the backend container:
    docker compose cp .\\smoke_seller_product.py backend:/app/
    docker compose exec backend python /app/smoke_seller_product.py
"""
import io
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client  # noqa: E402
from PIL import Image  # noqa: E402

from catalog.models import Product  # noqa: E402

PASS = "demo1234"


def png_bytes(color):
    img = Image.new("RGB", (64, 64), color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


def main():
    c = Client()
    ok = c.login(username="seller1", password=PASS)
    assert ok, "seller1 login failed"

    # 1. seeded products should already have images
    seeded = Product.objects.filter(seller__username="seller1").exclude(image="")
    print(f"[1] seeded products with images: {seeded.count()}")
    assert seeded.count() >= 20, "expected seeded products to have images"

    # 2. POST a new product with an image
    img = png_bytes((10, 200, 120))
    img.name = "gadget.png"
    r = c.post(
        "/api/seller/products",
        {
            "title": "Smoke Gadget X",
            "category": "electronics",
            "mrp": "1999",
            "stock": "3",
            "description": "smoke test product",
            "image": img,
        },
    )
    print(f"[2] create product -> {r.status_code}")
    assert r.status_code == 201, r.content[:300]
    data = r.json()
    assert data["image_url"], "image_url missing"
    assert data["stock_listed"] == 3, data
    print(f"    image_url={data['image_url']} stock={data['stock_listed']}")

    # 3. it should appear in the public catalog
    r = c.get("/api/products?q=Smoke Gadget")
    found = [p for p in r.json() if p["title"] == "Smoke Gadget X"]
    print(f"[3] public catalog shows it -> {bool(found)} (image_url={found[0]['image_url'] if found else None})")
    assert found and found[0]["image_url"], "not in catalog or image missing"

    # 4. media file is actually served
    r = c.get(found[0]["image_url"])
    print(f"[4] GET {found[0]['image_url']} -> {r.status_code}")
    assert r.status_code == 200

    # 5. bad extension is rejected
    bad = io.BytesIO(b"MZ fake exe")
    bad.name = "virus.exe"
    r = c.post(
        "/api/seller/products",
        {"title": "Bad", "category": "electronics", "mrp": "10", "stock": "1", "image": bad},
    )
    print(f"[5] bad extension -> {r.status_code} (expect 400)")
    assert r.status_code == 400

    # 6. buyer cannot create products
    c2 = Client()
    assert c2.login(username="buyer1", password=PASS)
    r = c2.post("/api/seller/products", {"title": "Nope", "category": "x", "mrp": "10"})
    print(f"[6] buyer blocked -> {r.status_code} (expect 403)")
    assert r.status_code == 403

    print("\nALL SELLER PRODUCT SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
