"""End-to-end smoke test for the Next Best Owner (P2P resale) engine.

Self-contained: seeds its own seller + buyers (with order history so they get
distinct demand profiles), then exercises the full pipeline with the mock
embedder + mock VLM, all inline (eager Celery):

    resell (linked + external) -> grade -> price -> list -> bipartite match
      -> tiered Dutch auction -> step (price drops, tiers widen, bonus grows)
      -> buy (green credits: base + bonus, seller payout)

Run inside the backend container against the db service:
    docker compose run --rm \
      -e CELERY_TASK_ALWAYS_EAGER=1 -e NEXTOWNER_EMBEDDING_PROVIDER=mock \
      -e GRADING_VLM_PROVIDER=mock -v "$PWD":/app backend \
      python /app/smoke_nextowner.py
"""

import io
import os
import uuid

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "1")
os.environ.setdefault("NEXTOWNER_EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("GRADING_VLM_PROVIDER", "mock")
django.setup()

from django.conf import settings as _settings  # noqa: E402

if "testserver" not in _settings.ALLOWED_HOSTS and "*" not in _settings.ALLOWED_HOSTS:
    _settings.ALLOWED_HOSTS = list(_settings.ALLOWED_HOSTS) + ["testserver"]

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.files.base import ContentFile  # noqa: E402
from django.test import Client  # noqa: E402
from PIL import Image  # noqa: E402

from catalog.models import ItemUnit, Product, UnitStates  # noqa: E402
from core.models import Roles  # noqa: E402
from greencredits.logic import award_credits  # noqa: E402
from greencredits.models import GreenCreditAccount  # noqa: E402
from marketplace.models import (  # noqa: E402
    Listing,
    ListingSources,
    ListingStates,
    Order,
    OrderStates,
)
from nextowner.models import AuctionStatus, MatchEdge, ResaleAuction  # noqa: E402

User = get_user_model()
PASS = "demo1234"
TAG = uuid.uuid4().hex[:6]  # unique suffix so re-runs don't collide

# Distinct product themes so buyers develop different tastes.
THEMES = [
    ("electronics", "wireless noise cancelling headphones audio bluetooth", 6000),
    ("electronics", "mechanical gaming keyboard rgb usb", 4500),
    ("apparel", "cotton running t-shirt breathable sport", 1200),
    ("footwear", "leather formal shoes brogue office", 3500),
    ("electronics", "smart fitness band heart rate tracker", 2500),
    ("apparel", "wool winter jacket insulated outdoor", 5000),
]


def png(color):
    buf = io.BytesIO()
    Image.new("RGB", (48, 48), color).save(buf, "PNG")
    buf.seek(0)
    return buf


def make_product(theme, mrp, seller, with_image=True):
    cat, words, _ = theme
    p = Product.objects.create(
        title=f"{words.split()[0].title()} {TAG}",
        description=words,
        category=cat,
        mrp=mrp,
        seller=seller,
        attributes={"brand": words.split()[1]},
    )
    if with_image:
        p.image.save(f"ref_{p.id}.png", ContentFile(png((40, 120, 200)).read()), save=True)
    return p


def delivered_order(buyer, product, price):
    """Give a buyer a delivered order for `product` (builds purchase history)."""
    unit = ItemUnit.objects.create(product=product, state=UnitStates.SOLD, owner=buyer)
    listing = Listing.objects.create(
        unit=unit, source=ListingSources.NEW, price=price, state=ListingStates.SOLD
    )
    return Order.objects.create(buyer=buyer, listing=listing, state=OrderStates.DELIVERED)


def section(n, msg):
    print(f"\n[{n}] {msg}")


def main():
    # --- seed actors -------------------------------------------------------
    seller = User.objects.create_user(f"seller_{TAG}", password=PASS, role=Roles.SELLER, city="Delhi")
    products = [make_product(t, t[2], seller) for t in THEMES]

    # Six buyers, each with a tilted purchase history so demand profiles differ.
    buyers = []
    for i in range(6):
        b = User.objects.create_user(f"buyer_{TAG}_{i}", password=PASS, role=Roles.BUYER, city="Delhi")
        # buyer i buys mostly from product-theme i and its neighbour.
        for p in (products[i % len(products)], products[(i + 1) % len(products)]):
            delivered_order(b, p, p.mrp)
        award_credits(b, 20 * (i % 3), "BUY_USER_RESALE", "seed", None)
        buyers.append(b)
    print(f"seeded seller + {len(buyers)} buyers + {len(products)} products (tag={TAG})")

    # The seller will resell a headphones-like item; buyer_0 bought that theme.
    resale_product = make_product(THEMES[0], 6000, seller)
    sale_unit = ItemUnit.objects.create(product=resale_product, state=UnitStates.SOLD, owner=seller)
    sale_listing = Listing.objects.create(
        unit=sale_unit, source=ListingSources.NEW, price=6000, state=ListingStates.SOLD
    )
    seller_order = Order.objects.create(buyer=seller, listing=sale_listing, state=OrderStates.DELIVERED)

    sc = Client()
    assert sc.login(username=seller.username, password=PASS)

    # --- 1. LINKED resale (past order, has reference image) ----------------
    section(1, "Resell a linked past order (reference-image grading)")
    img = png((200, 60, 60)); img.name = "u1.png"
    img2 = png((60, 200, 60)); img2.name = "u2.png"
    r = sc.post("/api/nextowner/resell", {"order_id": seller_order.id, "photos": [img, img2]})
    assert r.status_code == 201, r.content[:400]
    body = r.json()
    assert "auction" in body, f"expected eager auction, got {body}"
    auction_id = body["auction"]["id"]
    a = body["auction"]
    print(f"    auction#{auction_id} grade={a['grade']} ceiling={a['ceiling']} floor={a['floor']} price={a['current_price']}")
    assert a["ceiling"] >= a["floor"] > 0
    assert a["current_price"] == a["ceiling"], "Dutch auction must start at ceiling"
    edges = a["edges"]
    assert edges, "expected matched buyer edges"
    scores = [e["score"] for e in edges]
    assert scores == sorted(scores, reverse=True), "edges must be ranked desc"
    tier0 = [e for e in edges if e["tier"] == 0]
    assert all(e["alerted"] for e in tier0), "tier-0 must be alerted at start"
    assert any(not e["alerted"] for e in edges if e["tier"] > 0) or len({e["tier"] for e in edges}) == 1
    print(f"    {len(edges)} ranked buyers; top score={scores[0]:.3f}; tier0 alerted={len(tier0)}")

    # pricing snapshot sanity
    pricing = a["pricing"]
    assert pricing.get("est_value", 0) > 0
    assert pricing.get("depreciation") is not None
    print(f"    pricing: est={pricing['est_value']} quality={pricing.get('quality')} depr={pricing.get('depreciation')}")

    # --- 2. EXTERNAL resale (brand-new, no reference -> anomaly mode) ------
    section(2, "Resell a brand-new EXTERNAL item (anomaly-mode grading)")
    eimg = png((90, 90, 220)); eimg.name = "ext.png"
    r = sc.post("/api/nextowner/resell", {
        "title": f"External Speaker {TAG}", "category": "electronics",
        "mrp": "4000", "original_price": "4000", "brand": "boomx",
        "description": "portable bluetooth speaker bass", "age_months": "3",
        "photos": [eimg],
    })
    assert r.status_code == 201, r.content[:400]
    ebody = r.json()
    assert "auction" in ebody, f"expected eager auction, got {ebody}"
    ext_auction_id = ebody["auction"]["id"]
    ext_product = Product.objects.get(units__auctions__id=ext_auction_id)
    assert ext_product.origin == "EXTERNAL", ext_product.origin
    print(f"    external auction#{ext_auction_id} origin={ext_product.origin} price={ebody['auction']['current_price']}")

    # --- 3. demo surface ---------------------------------------------------
    section(3, "Demo surface: products / match / results")
    r = sc.get("/api/nextowner/demo/products"); assert r.status_code == 200
    print(f"    demo/products -> {len(r.json())} cards")
    r = sc.post("/api/nextowner/demo/match", {}, content_type="application/json")
    assert r.status_code == 200, r.content[:300]
    print(f"    demo/match -> matching {len(r.json().get('matching', []))} auctions")
    r = sc.get("/api/nextowner/demo/results"); assert r.status_code == 200
    results = r.json()
    assert any(c["id"] == auction_id for c in results)
    print(f"    demo/results -> {len(results)} cards, each with top buyers")

    # --- 4. Dutch steps: price falls, tiers widen, green bonus grows -------
    section(4, "Dutch auction steps (price down, tiers widen, bonus up)")
    auction = ResaleAuction.objects.get(pk=auction_id)
    start_price = auction.current_price
    prev_price = start_price
    prev_alerted = MatchEdge.objects.filter(auction=auction, alerted=True).count()
    prev_bonus = -1
    for s in range(auction.max_tier + 1):
        r = sc.post(f"/api/nextowner/auctions/{auction_id}/step")
        assert r.status_code == 200, r.content[:300]
        d = r.json()
        alerted = MatchEdge.objects.filter(auction=auction, alerted=True).count()
        bonus = max((e["green_credit_bonus"] for e in d["edges"]), default=0)
        print(f"    step {s+1}: price {prev_price}->{d['current_price']} tier={d['tier']} alerted={alerted} maxBonus={bonus} status={d['status']}")
        assert d["current_price"] <= prev_price, "price must not rise"
        assert alerted >= prev_alerted, "alert reach must not shrink"
        assert d["current_price"] >= auction.floor, "must not sell below floor/reserve"
        prev_price, prev_alerted, prev_bonus = d["current_price"], alerted, bonus
        if d["status"] != "ACTIVE":
            break
    assert prev_price < start_price, "price should have dropped over the run"

    # --- 5. buyer alerts + buy-now (mid-descent, with green bonus) --------
    section(5, "Buyer sees alert and buys mid-descent at a discounted price")
    # Use the external auction (still active) and step it twice so the price has
    # dropped below the ceiling -> a non-zero green bonus is in play.
    auction = ResaleAuction.objects.get(pk=ext_auction_id)
    for _ in range(2):
        sc.post(f"/api/nextowner/auctions/{auction.id}/step")
    auction.refresh_from_db()
    assert auction.status == AuctionStatus.ACTIVE
    assert auction.current_price < auction.ceiling, "price should have descended"
    top_edge = MatchEdge.objects.filter(auction=auction).order_by("rank").first()
    buyer = top_edge.buyer
    bc = Client(); assert bc.login(username=buyer.username, password=PASS)
    r = bc.get("/api/nextowner/alerts")
    assert r.status_code == 200
    print(f"    buyer {buyer.username} sees {len(r.json())} alert(s)")

    before = GreenCreditAccount.objects.filter(user=buyer).first()
    before_bal = before.balance if before else 0
    seller_before = GreenCreditAccount.objects.filter(user=seller).first()
    seller_before_bal = seller_before.balance if seller_before else 0
    price_now = ResaleAuction.objects.get(pk=auction.id).current_price
    r = bc.post(f"/api/nextowner/auctions/{auction.id}/buy")
    assert r.status_code == 201, r.content[:400]
    buy = r.json()
    print(f"    bought auction#{auction.id} at price={buy['price']} green={buy['green_credits']} (base+bonus, bonus={buy['green_credit_bonus']})")
    assert buy["price"] == price_now
    assert buy["green_credit_bonus"] > 0, "mid-descent buy should earn a green bonus"
    assert buy["green_credits"] == 20 + buy["green_credit_bonus"], "credits = base 20 + bonus"

    after_bal = GreenCreditAccount.objects.get(user=buyer).balance
    seller_after_bal = GreenCreditAccount.objects.get(user=seller).balance
    assert after_bal == before_bal + buy["green_credits"], (after_bal, before_bal, buy)
    assert seller_after_bal == seller_before_bal + 30, "seller RESELL +30 expected"
    print(f"    buyer credits {before_bal}->{after_bal}; seller credits {seller_before_bal}->{seller_after_bal}")

    # auction + unit finalized
    auction.refresh_from_db()
    assert auction.status == AuctionStatus.SOLD
    assert auction.buyer_id == buyer.id
    unit = auction.unit; unit.refresh_from_db()
    assert unit.owner_id == buyer.id, "unit ownership must transfer"
    assert unit.state == UnitStates.SOLD
    # double-buy guard
    r2 = bc.post(f"/api/nextowner/auctions/{auction.id}/buy")
    assert r2.status_code == 409, "second buy must be rejected"
    print("    double-buy correctly rejected (409)")

    print("\nALL NEXTOWNER SMOKE CHECKS PASSED ✅")


if __name__ == "__main__":
    main()
