"""Seed demo data: 4 users, products across categories, units in every
lifecycle state so all three portals look alive immediately.

Idempotent: running twice is a no-op (guards on username existence).
"""

import io
import random

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from PIL import Image, ImageDraw

from catalog.models import ItemUnit, Product, UnitStates
from core.models import Roles, User
from marketplace.models import (
    Listing,
    ListingSources,
    ListingStates,
    Order,
    OrderStates,
    ReturnReasons,
)
from sellerportal.models import RuleActions, SellerRule
from services import ai

PRODUCTS = [
    ("boAt Rockerz 450 Headphones", "electronics", 1999),
    ("Noise ColorFit Pro 4 Smartwatch", "electronics", 2499),
    ("Mi Power Bank 3i 20000mAh", "electronics", 1699),
    ("JBL Go 3 Bluetooth Speaker", "electronics", 2299),
    ("Philips Beard Trimmer BT3211", "electronics", 1295),
    ("Puma Smashic Sneakers", "footwear", 2999),
    ("Campus Running Shoes", "footwear", 1499),
    ("Bata Formal Derby Shoes", "footwear", 1899),
    ("Sparx Slip-on Casuals", "footwear", 1099),
    ("Levi's 511 Slim Jeans", "apparel", 2799),
    ("Allen Solly Polo T-shirt", "apparel", 999),
    ("Jockey Track Pants", "apparel", 899),
    ("Van Heusen Cotton Shirt", "apparel", 1599),
    ("Wildcraft 44L Rucksack", "apparel", 2199),
    ("Prestige Iris 750W Mixer Grinder", "electronics", 3199),
    ("Milton Thermosteel Flask 1L", "apparel", 745),
    ("Fastrack Analog Watch", "electronics", 1495),
    ("Skybags Cabin Trolley", "apparel", 3499),
    ("Boldfit Yoga Mat 6mm", "apparel", 699),
    ("Butterfly Gas Stove 2 Burner", "electronics", 2899),
]

FIRST_NAMES = ["aarav", "diya", "kabir", "meera", "rohan", "sana", "vivaan", "zara"]

PALETTE = [
    (244, 114, 22), (45, 212, 191), (99, 102, 241), (236, 72, 153),
    (132, 204, 22), (250, 204, 21), (14, 165, 233), (248, 113, 113),
]


def placeholder_image(title, color):
    """Generate a simple branded placeholder JPEG for seeded products."""
    img = Image.new("RGB", (480, 360), color)
    d = ImageDraw.Draw(img)
    initials = "".join(w[0] for w in title.split()[:3]).upper()
    d.text((24, 150), initials, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return SimpleUploadedFile(
        f"{initials.lower()}.jpg", buf.getvalue(), content_type="image/jpeg"
    )


class Command(BaseCommand):
    help = "Load demo data (idempotent)."

    def handle(self, *args, **options):
        if User.objects.filter(username="seller1").exists():
            self.stdout.write("Seed data already present; skipping.")
            return

        rng = random.Random(42)

        # --- users ---
        buyer = User.objects.create_user(
            "buyer1", password="demo1234", role=Roles.BUYER
        )
        reseller = User.objects.create_user(
            "rahul", password="demo1234", role=Roles.BUYER
        )
        seller = User.objects.create_user(
            "seller1", password="demo1234", role=Roles.SELLER
        )
        User.objects.create_user(
            "facility1", password="demo1234", role=Roles.FACILITY
        )
        User.objects.create_superuser("admin", password="admin1234")
        extra_buyers = [
            User.objects.create_user(n, password="demo1234", role=Roles.BUYER)
            for n in FIRST_NAMES
        ]

        # --- products + NEW listings ---
        products = []
        for idx, (title, category, mrp) in enumerate(PRODUCTS):
            p = Product.objects.create(
                title=title,
                description=f"{title} — demo catalog item.",
                category=category,
                mrp=mrp,
                seller=seller,
                image=placeholder_image(title, PALETTE[idx % len(PALETTE)]),
            )
            products.append(p)
            unit = ItemUnit.objects.create(product=p, state=UnitStates.NEW)
            Listing.objects.create(
                unit=unit,
                source=ListingSources.NEW,
                price=mrp,
                state=ListingStates.ACTIVE,
            )

        # --- orders in various states for buyer1 ---
        for i, p in enumerate(products[:6]):
            unit = ItemUnit.objects.create(product=p, state=UnitStates.SOLD, owner=buyer)
            listing = Listing.objects.create(
                unit=unit,
                source=ListingSources.NEW,
                price=p.mrp,
                state=ListingStates.SOLD,
            )
            state = [OrderStates.PLACED, OrderStates.DELIVERED, OrderStates.DELIVERED][
                i % 3
            ]
            Order.objects.create(buyer=buyer, listing=listing, state=state)

        # --- delivered orders for rahul (resale candidates) ---
        for p in products[6:10]:
            unit = ItemUnit.objects.create(
                product=p, state=UnitStates.SOLD, owner=reseller
            )
            listing = Listing.objects.create(
                unit=unit,
                source=ListingSources.NEW,
                price=p.mrp,
                state=ListingStates.SOLD,
            )
            Order.objects.create(
                buyer=reseller, listing=listing, state=OrderStates.DELIVERED
            )

        # --- one active USER_RESALE listing ---
        p = products[10]
        graded = ai.grade(p.id)
        priced = ai.price(p.id, p.mrp, graded["grade"])
        unit = ItemUnit.objects.create(
            product=p,
            state=UnitStates.RELISTED,
            owner=reseller,
            grade=graded["grade"],
            grade_confidence=graded["confidence"],
            est_value=priced["est_value"],
        )
        Listing.objects.create(
            unit=unit,
            source=ListingSources.USER_RESALE,
            price=priced["est_value"],
            band_lo=priced["band_lo"],
            band_hi=priced["band_hi"],
            state=ListingStates.ACTIVE,
            lister=reseller,
        )

        # --- units pending return pickup (facility incoming queue) ---
        for p in products[11:14]:
            owner = rng.choice(extra_buyers)
            unit = ItemUnit.objects.create(
                product=p, state=UnitStates.RETURN_PENDING, owner=owner
            )
            listing = Listing.objects.create(
                unit=unit,
                source=ListingSources.NEW,
                price=p.mrp,
                state=ListingStates.SOLD,
            )
            Order.objects.create(
                buyer=owner,
                listing=listing,
                state=OrderStates.RETURN_REQUESTED,
                return_reason=rng.choice(ReturnReasons.values),
                claimed_untouched=rng.random() > 0.5,
            )

        # --- units already at facility (seller inbox) ---
        now = timezone.now()
        for i, p in enumerate(products[14:18]):
            graded = ai.grade(p.id, untouched=(i % 2 == 0))
            priced = ai.price(p.id, p.mrp, graded["grade"])
            ItemUnit.objects.create(
                product=p,
                state=UnitStates.AT_FACILITY,
                untouched=(i % 2 == 0),
                grade=graded["grade"],
                grade_confidence=graded["confidence"],
                est_value=priced["est_value"],
                arrived_at_facility=now,
                storage_cost_accrued=rng.randint(0, 60),
            )

        # --- one unit near liquidation (watchlist drama) ---
        p = products[18]
        graded = ai.grade(p.id)
        priced = ai.price(p.id, p.mrp, graded["grade"])
        unit = ItemUnit.objects.create(
            product=p,
            state=UnitStates.RELISTED,
            grade=graded["grade"],
            grade_confidence=graded["confidence"],
            est_value=priced["est_value"],
            arrived_at_facility=now,
            storage_cost_accrued=int(priced["est_value"] * 0.9),
        )
        Listing.objects.create(
            unit=unit,
            source=ListingSources.FACILITY_RELIST,
            price=priced["est_value"],
            band_lo=priced["band_lo"],
            band_hi=priced["band_hi"],
            state=ListingStates.ACTIVE,
        )

        # --- seller rule ---
        SellerRule.objects.create(
            seller=seller,
            min_grade="B",
            min_recovery_pct=60,
            action=RuleActions.AUTO_RELIST,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded. Logins (password demo1234): buyer1, rahul, seller1, "
                "facility1 · admin/admin1234"
            )
        )
