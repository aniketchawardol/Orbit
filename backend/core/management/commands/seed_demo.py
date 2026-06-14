"""Seed demo data: 4 users, products across categories, units in every
lifecycle state so all three portals look alive immediately.

Idempotent: running twice is a no-op (guards on username existence).
"""

import io
import os
import random
from datetime import timedelta
from pathlib import Path

from django.conf import settings
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
from rerouting.geo import CITY_COORDS
from greencredits.logic import award_credits, seed_rewards
from nextowner.services import open_relist_auction

# Rich catalog seed. Each product carries an extensive marketing description and
# a structured `attributes` map (brand/material/specs...). The attributes are
# fed verbatim to the AI grader so per-category inspection criteria adapt to the
# real product, and they make the storefront/health-card pages look complete.
#
# NOTE: downstream seeding slices this list by index (products[:6], [6:10], ...),
# so keep the ordering stable when editing.
PRODUCTS = [
    {
        "title": "boAt Rockerz 450 Headphones",
        "category": "electronics",
        "mrp": 1999,
        "image": "boat_rockerz_450.jpg",
        "description": (
            "On-ear Bluetooth headphones with 40mm dynamic drivers tuned for "
            "boAt's signature bass. Enjoy up to 15 hours of playback on a single "
            "charge, dual connectivity (Bluetooth v5.0 + 3.5mm AUX), plush "
            "padded ear cushions for all-day comfort, and easy access controls "
            "for music, calls and your voice assistant. The lightweight foldable "
            "frame folds flat to slip into any bag for travel."
        ),
        "attributes": {
            "brand": "boAt",
            "color": "Luscious Black",
            "type": "On-ear wireless",
            "connectivity": "Bluetooth 5.0 + 3.5mm AUX",
            "driver": "40mm dynamic",
            "battery_life": "15 hours",
            "charging": "micro-USB",
            "weight": "170 g",
            "warranty": "1 year",
        },
    },
    {
        "title": "Noise ColorFit Pro 4 Smartwatch",
        "category": "electronics",
        "mrp": 2499,
        "image": "noise_colorfit_pro_4.jpg",
        "description": (
            "A 1.72\" TruView display smartwatch with a 60Hz refresh rate, "
            "Bluetooth calling and 100+ sports modes. Tracks heart rate, SpO2, "
            "sleep and stress around the clock, and lasts up to 7 days on a "
            "typical charge. IP68 water resistance, hundreds of customizable "
            "watch faces and a premium metallic build make it a do-it-all "
            "wellness companion."
        ),
        "attributes": {
            "brand": "Noise",
            "color": "Jet Black",
            "display": "1.72\" TFT LCD, 60Hz",
            "bluetooth_calling": "Yes",
            "water_resistance": "IP68",
            "battery_life": "7 days",
            "sensors": "Heart rate, SpO2, sleep, stress",
            "strap_material": "Silicone",
            "compatibility": "Android & iOS",
            "warranty": "1 year",
        },
    },
    {
        "title": "Mi Power Bank 3i 20000mAh",
        "category": "electronics",
        "mrp": 1699,
        "image": "mi_power_bank.jpg",
        "description": (
            "A high-capacity 20000mAh power bank with 18W fast charging and "
            "triple input ports (USB-C, Micro-USB and Lightning). Charges two "
            "devices at once, includes 12-layer advanced circuit protection for "
            "safety, and packs enough power for 4-5 full smartphone charges. The "
            "matte-finish metal-look body resists fingerprints and scuffs."
        ),
        "attributes": {
            "brand": "Xiaomi",
            "color": "Black",
            "capacity": "20000mAh",
            "output": "18W fast charge",
            "ports": "Dual USB-A out + USB-C",
            "input": "USB-C / Micro-USB",
            "weight": "434 g",
            "protection": "12-layer circuit protection",
            "warranty": "6 months",
        },
    },
    {
        "title": "JBL Go 3 Bluetooth Speaker",
        "category": "electronics",
        "mrp": 2299,
        "image": "jbl_go_3.jpg",
        "description": (
            "An ultra-portable wireless speaker delivering bold JBL Pro Sound in "
            "a pocket-sized body. Rated IP67 dust- and water-proof, it survives "
            "spills, sand and rain, runs up to 5 hours on a charge and connects "
            "instantly over Bluetooth 5.1. The vibrant fabric finish and "
            "integrated loop make it the perfect companion for adventures indoors "
            "and out."
        ),
        "attributes": {
            "brand": "JBL",
            "color": "Blue",
            "water_resistance": "IP67 dust & waterproof",
            "battery_life": "5 hours",
            "connectivity": "Bluetooth 5.1",
            "output_power": "4.2W",
            "charging": "USB-C",
            "weight": "209 g",
            "warranty": "1 year",
        },
    },
    {
        "title": "Philips Beard Trimmer BT3211",
        "category": "electronics",
        "mrp": 1295,
        "image": "phillips_beard_trimmer.jpg",
        "description": (
            "A cordless beard trimmer with 20 precise length settings from 0.5 "
            "to 10mm and self-sharpening stainless steel blades that stay sharp "
            "for life. Get up to 60 minutes of cordless runtime after a one-hour "
            "charge, a fully washable head for easy cleaning, and a skin-friendly "
            "rounded comb. The Lift & Trim system guides longer hairs to the "
            "blades for a fast, even cut."
        ),
        "attributes": {
            "brand": "Philips",
            "color": "Black/Lime",
            "length_settings": "20 (0.5-10mm)",
            "runtime": "60 minutes cordless",
            "charging_time": "1 hour",
            "blade": "Self-sharpening stainless steel",
            "washable": "Yes",
            "power": "Rechargeable / cordless",
            "warranty": "2 years",
        },
    },
    {
        "title": "Puma Smashic Sneakers",
        "category": "footwear",
        "mrp": 2999,
        "image": "puma_smashic_sneakers.jpg",
        "description": (
            "Classic court-style sneakers with a clean synthetic-leather upper "
            "and the signature Puma formstrip. A cushioned footbed and durable "
            "rubber outsole keep you comfortable from morning to night, while the "
            "lace-up closure locks in a secure fit. A versatile everyday "
            "silhouette that pairs effortlessly with casual and smart-casual looks."
        ),
        "attributes": {
            "brand": "Puma",
            "color": "White / Black",
            "upper_material": "Synthetic leather",
            "sole": "Rubber",
            "closure": "Lace-up",
            "gender": "Unisex",
            "available_sizes": "UK 6-11",
            "size_type": "shoe_uk",
            "size_options": ["6", "7", "8", "9", "10", "11"],
            "warranty": "90 days",
        },
    },
    {
        "title": "Campus Running Shoes",
        "category": "footwear",
        "mrp": 1499,
        "image": "campus_running_shoes.jpg",
        "description": (
            "Lightweight running shoes built for daily miles, with a breathable "
            "mesh upper that keeps feet cool and an EVA-cushioned midsole that "
            "soaks up impact. The anti-skid patterned outsole grips wet and dry "
            "surfaces, while the padded collar and flexible sole deliver a "
            "natural stride on runs and gym sessions alike."
        ),
        "attributes": {
            "brand": "Campus",
            "color": "Grey / Orange",
            "upper_material": "Breathable mesh",
            "midsole": "EVA cushioning",
            "sole": "Anti-skid rubber",
            "closure": "Lace-up",
            "gender": "Men",
            "available_sizes": "UK 6-10",
            "size_type": "shoe_uk",
            "size_options": ["6", "7", "8", "9", "10"],
            "use": "Running / training",
        },
    },
    {
        "title": "Bata Formal Derby Shoes",
        "category": "footwear",
        "mrp": 1899,
        "image": "bata_formal_derby_shoes.jpg",
        "description": (
            "Timeless formal derby shoes with a polished finish and classic "
            "lace-up closure. A cushioned insole keeps you comfortable through "
            "long workdays, the durable TPR sole adds quiet grip, and the elegant "
            "almond toe completes a refined profile. The ideal companion for "
            "office wear, interviews and formal occasions."
        ),
        "attributes": {
            "brand": "Bata",
            "color": "Black",
            "upper_material": "Synthetic leather",
            "sole": "TPR",
            "closure": "Lace-up",
            "style": "Derby",
            "gender": "Men",
            "available_sizes": "UK 6-11",
            "size_type": "shoe_uk",
            "size_options": ["6", "7", "8", "9", "10", "11"],
            "occasion": "Formal",
        },
    },
    {
        "title": "Sparx Slip-on Casuals",
        "category": "footwear",
        "mrp": 1099,
        "image": "sparx_slip_on_casuals.jpg",
        "description": (
            "Easy slip-on casual shoes with a soft fabric upper and a cushioned "
            "insole that feels great straight out of the box. The lightweight, "
            "flexible sole and elasticated side panels give a snug, secure fit "
            "without laces, so you can simply slip them on and go. A relaxed, "
            "go-anywhere look for everyday wear."
        ),
        "attributes": {
            "brand": "Sparx",
            "color": "Navy",
            "upper_material": "Fabric",
            "sole": "EVA",
            "closure": "Slip-on",
            "gender": "Men",
            "available_sizes": "UK 6-10",
            "size_type": "shoe_uk",
            "size_options": ["6", "7", "8", "9", "10"],
            "use": "Casual",
        },
    },
    {
        "title": "Levi's 511 Slim Jeans",
        "category": "apparel",
        "mrp": 2799,
        "image": "levis_511_slim_jeans.jpg",
        "description": (
            "The iconic 511 slim-fit jeans, cut from premium stretch denim that "
            "sits just below the waist with a slim line from hip to ankle. "
            "Five-pocket styling, the signature leather patch and Levi's "
            "legendary craftsmanship deliver all-day comfort and a modern "
            "silhouette. A true wardrobe staple that works with everything from "
            "tees to blazers."
        ),
        "attributes": {
            "brand": "Levi's",
            "color": "Dark Indigo",
            "fit": "Slim (511)",
            "material": "98% cotton, 2% elastane",
            "rise": "Mid-rise",
            "closure": "Button & zip fly",
            "gender": "Men",
            "available_sizes": "28-38 waist",
            "size_type": "waist",
            "size_options": ["28", "30", "32", "34", "36", "38"],
            "care": "Machine wash cold",
        },
    },
    {
        "title": "Allen Solly Polo T-shirt",
        "category": "apparel",
        "mrp": 999,
        "image": "allen_solly_polo_tshirt.jpg",
        "description": (
            "A smart-casual polo in soft, breathable cotton pique with a classic "
            "ribbed collar and two-button placket. The regular fit, tipped sleeve "
            "cuffs and neat embroidered logo give it a refined finish that's "
            "equally at home at the office or on a weekend outing. Holds its "
            "shape and colour wash after wash."
        ),
        "attributes": {
            "brand": "Allen Solly",
            "color": "Navy Blue",
            "material": "100% cotton pique",
            "fit": "Regular",
            "collar": "Ribbed polo",
            "sleeve": "Half",
            "gender": "Men",
            "available_sizes": "S-XXL",
            "size_type": "top",
            "size_options": ["S", "M", "L", "XL", "XXL"],
            "care": "Machine wash cold",
        },
    },
    {
        "title": "Jockey Track Pants",
        "category": "apparel",
        "mrp": 899,
        "image": "jockey_track_pants.jpg",
        "description": (
            "Comfort-first track pants in a soft cotton-rich blend with a smooth "
            "inner finish that feels gentle on skin. An elasticated waistband "
            "with drawcord dials in the fit, secure zippered side pockets keep "
            "essentials safe, and the lightly tapered leg gives a clean, modern "
            "line. Perfect for workouts, lounging and casual errands."
        ),
        "attributes": {
            "brand": "Jockey",
            "color": "Charcoal Melange",
            "material": "Cotton-rich blend",
            "fit": "Slim tapered",
            "waist": "Elastic + drawcord",
            "pockets": "Zippered side",
            "gender": "Men",
            "available_sizes": "S-XXL",
            "size_type": "top",
            "size_options": ["S", "M", "L", "XL", "XXL"],
            "care": "Machine wash",
        },
    },
    {
        "title": "Van Heusen Cotton Shirt",
        "category": "apparel",
        "mrp": 1599,
        "image": "van_heusen_shirt.jpg",
        "description": (
            "A tailored formal shirt in 100% premium cotton with a "
            "wrinkle-resistant finish and a classic spread collar. The slim fit, "
            "single-button cuffs and clean solid weave transition effortlessly "
            "from the boardroom to dinner. Breathable, easy to iron and built to "
            "look crisp all day."
        ),
        "attributes": {
            "brand": "Van Heusen",
            "color": "Sky Blue",
            "material": "100% cotton",
            "fit": "Slim",
            "collar": "Spread",
            "sleeve": "Full",
            "gender": "Men",
            "available_sizes": "38-44",
            "size_type": "shirt",
            "size_options": ["38", "40", "42", "44"],
            "finish": "Wrinkle-resistant",
            "care": "Machine wash",
        },
    },
    {
        "title": "Wildcraft 44L Rucksack",
        "category": "apparel",
        "mrp": 2199,
        "image": "wildcraft_44L_rucksack.jpg",
        "description": (
            "A rugged 44L rucksack built for travel and trekking, with a roomy "
            "main compartment, multiple utility pockets and padded, adjustable "
            "shoulder straps that spread the load. Water-resistant fabric and a "
            "reinforced base shrug off rough handling, while the ventilated back "
            "panel keeps you cool on long hauls. Cabin-friendly dimensions make "
            "it a great carry-on."
        ),
        "attributes": {
            "brand": "Wildcraft",
            "color": "Black",
            "capacity": "44 litres",
            "material": "Water-resistant polyester",
            "compartments": "Multiple",
            "straps": "Padded, adjustable",
            "use": "Travel / trekking",
            "warranty": "1 year",
        },
    },
    {
        "title": "Prestige Iris 750W Mixer Grinder",
        "category": "electronics",
        "mrp": 3199,
        "image": "prestige_mixer.jpg",
        "description": (
            "A powerful 750W mixer grinder with three stainless steel jars for "
            "wet grinding, dry grinding and chutney, plus overload protection "
            "that guards the motor. Sharp stainless steel blades make light work "
            "of everyday Indian cooking, while anti-skid feet and an ergonomic "
            "handle design keep things stable and safe. A sleek body that suits "
            "any modern kitchen."
        ),
        "attributes": {
            "brand": "Prestige",
            "color": "White / Black",
            "power": "750W",
            "jars": "3 stainless steel",
            "speed_settings": "3 + pulse",
            "blade": "Stainless steel",
            "overload_protection": "Yes",
            "warranty": "2 years",
            "use": "Kitchen",
        },
    },
    {
        "title": "Milton Thermosteel Flask 1L",
        "category": "general",
        "mrp": 745,
        "image": "milton_thermosteel_flask.jpg",
        "description": (
            "A double-walled vacuum-insulated stainless steel flask that keeps "
            "beverages piping hot or refreshingly cold for up to 24 hours. The "
            "leak-proof threaded lid travels safely in any bag, the rust-proof "
            "18/8 food-grade steel interior is hygienic and odour-free, and the "
            "sturdy easy-grip body resists dents. A generous 1-litre capacity "
            "makes it perfect for travel, office and home."
        ),
        "attributes": {
            "brand": "Milton",
            "color": "Steel",
            "type": "Vacuum flask / bottle",
            "capacity": "1 litre",
            "material": "18/8 stainless steel",
            "insulation": "Double-wall vacuum",
            "retention": "24 hours hot/cold",
            "leak_proof": "Yes",
            "warranty": "1 year",
        },
    },
    {
        "title": "Fastrack Analog Watch",
        "category": "electronics",
        "mrp": 1495,
        "image": "fastrack_analog_watch.jpg",
        "description": (
            "A minimalist analog wristwatch with a clean dial, durable "
            "mineral-glass face and a comfortable strap. Precise quartz movement "
            "keeps reliable time, while 30m water resistance handles splashes and "
            "rain during daily wear. The versatile design complements both casual "
            "and formal outfits — an everyday timepiece with attitude."
        ),
        "attributes": {
            "brand": "Fastrack",
            "color": "Black",
            "movement": "Quartz analog",
            "glass": "Mineral",
            "strap_material": "Leather",
            "water_resistance": "30 m",
            "dial_shape": "Round",
            "gender": "Unisex",
            "warranty": "1 year",
        },
    },
    {
        "title": "Skybags Cabin Trolley",
        "category": "apparel",
        "mrp": 3499,
        "image": "skybags_cabin_trolley.jpg",
        "description": (
            "A cabin-sized hard-shell trolley with smooth 360° spinner wheels, a "
            "scratch-resistant textured shell and a sturdy telescopic handle. The "
            "spacious interior includes a divider and zip pockets to keep packing "
            "tidy, and a built-in combination lock secures your belongings. "
            "Lightweight and airline cabin-friendly for hassle-free travel."
        ),
        "attributes": {
            "brand": "Skybags",
            "color": "Teal",
            "capacity": "Cabin (~35L)",
            "material": "Polycarbonate hard shell",
            "wheels": "360° spinner",
            "lock": "Combination",
            "handle": "Telescopic",
            "warranty": "3 years",
            "use": "Travel",
        },
    },
    {
        "title": "Boldfit Yoga Mat 6mm",
        "category": "apparel",
        "mrp": 699,
        "image": "boldfit_yoga_mat.jpg",
        "description": (
            "A cushioned 6mm yoga mat with a textured anti-slip surface that "
            "grips firmly during yoga, pilates and floor workouts. The "
            "lightweight, tear-resistant NBR foam is easy on knees, wrists and "
            "elbows, and the included carrying strap makes it effortless to roll "
            "up and go. Moisture-resistant and simple to wipe clean after every "
            "session."
        ),
        "attributes": {
            "brand": "Boldfit",
            "color": "Purple",
            "thickness": "6 mm",
            "material": "NBR foam",
            "dimensions": "183 x 61 cm",
            "anti_slip": "Yes",
            "carry_strap": "Included",
            "use": "Yoga / exercise",
            "warranty": "6 months",
        },
    },
    {
        "title": "Butterfly Gas Stove 2 Burner",
        "category": "general",
        "mrp": 2899,
        "image": "butterfly_gas_stove_2_burner.jpg",
        "description": (
            "A two-burner manual-ignition gas stove with a toughened glass top "
            "that resists scratches and is a breeze to wipe clean. "
            "High-efficiency brass burners deliver an even, powerful flame, the "
            "spill-proof drip tray catches splatters, and sturdy pan supports "
            "hold cookware of every size securely. Ergonomic knobs and a sleek "
            "black finish elevate any modern kitchen. Designed for LPG use."
        ),
        "attributes": {
            "brand": "Butterfly",
            "color": "Black",
            "burners": "2",
            "top_material": "Toughened glass",
            "burner_material": "Brass",
            "ignition": "Manual",
            "gas_type": "LPG",
            "warranty": "2 years",
            "use": "Kitchen",
        },
    },
    # --- Phone + cases: order-history compatibility demo (appended last so the
    #     index-based order slices above stay valid). ---
    {
        "title": "Apple iPhone 15",
        "category": "electronics",
        "mrp": 79999,
        "image": "iphone15.jpg",
        "stock": 5,
        "description": (
            "The iPhone 15 with the Dynamic Island, a 48MP main camera and USB-C. "
            "A durable colour-infused glass and aluminium design, the A16 Bionic "
            "chip for all-day performance, and a Super Retina XDR display that's "
            "brilliant indoors and out."
        ),
        "attributes": {
            "brand": "Apple",
            "model": "iPhone 15",
            "color": "Black",
            "storage": "128 GB",
            "display": "6.1\" Super Retina XDR",
            "chip": "A16 Bionic",
            "port": "USB-C",
            "warranty": "1 year",
        },
    },
    {
        "title": "iPhone 14 Silicone Case",
        "category": "accessories",
        "mrp": 1299,
        "image": "iphone14_cover.jpg",
        "stock": 5,
        "description": (
            "A soft-touch silicone back case precision-moulded for the iPhone 14. "
            "A microfibre lining protects the finish, raised edges guard the "
            "screen and camera, and all buttons and ports stay easy to reach."
        ),
        "attributes": {
            "brand": "Apple",
            "type": "Phone case",
            "compatible_model": "iPhone 14",
            "color": "Midnight",
            "material": "Silicone",
        },
    },
    {
        "title": "iPhone 15 Silicone Case",
        "category": "accessories",
        "mrp": 1499,
        "image": "iphone15_cover.jpg",
        "stock": 5,
        "description": (
            "A soft-touch silicone back case precision-moulded for the iPhone 15. "
            "A microfibre lining protects the finish, raised edges guard the "
            "screen and camera, and all buttons and ports stay easy to reach."
        ),
        "attributes": {
            "brand": "Apple",
            "type": "Phone case",
            "compatible_model": "iPhone 15",
            "color": "Storm Blue",
            "material": "Silicone",
        },
    },
    {
        "title": "Samsung Galaxy S23 Clear Case",
        "category": "accessories",
        "mrp": 299,
        "image": "samsungss23_cover.jpg",
        "stock": 5,
        "description": (
            "A slim transparent case tailored for the Samsung Galaxy S23. "
            "Anti-yellowing TPU shows off the phone's colour while raised bezels "
            "protect the screen and rear cameras from scuffs and drops."
        ),
        "attributes": {
            "brand": "Spigen",
            "type": "Phone case",
            "compatible_model": "Galaxy S23",
            "color": "Clear",
            "material": "TPU",
        },
    },
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


def _image_dirs():
    """Candidate directories that may hold the real product photos.

    Resolved in priority order so the same seed works locally and in Docker:
      1. SEED_IMAGES_DIR env override (explicit mount point).
      2. <backend>/images       — when ../images is mounted/copied into the image.
      3. <repo>/images          — local dev (backend's parent is the repo root).
    """
    candidates = []
    env_dir = os.environ.get("SEED_IMAGES_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path(settings.BASE_DIR) / "images")
    candidates.append(Path(settings.BASE_DIR).parent / "images")
    return candidates


def product_image(title, filename, color):
    """Load the real catalog photo for a product, else a branded placeholder.

    Keeps the seed idempotent and resilient: a missing file never breaks the
    boot-time seed, it just falls back to the generated placeholder.
    """
    for base in _image_dirs():
        path = base / filename
        if path.is_file():
            with open(path, "rb") as fh:
                data = fh.read()
            return SimpleUploadedFile(filename, data, content_type="image/jpeg")
    return placeholder_image(title, color)


class Command(BaseCommand):
    help = "Load demo data (idempotent)."

    def handle(self, *args, **options):
        # Rewards Store catalog is seeded unconditionally (idempotent) so it is
        # present even on databases seeded before rewards were wired in here.
        seed_rewards()

        if User.objects.filter(username="seller1").exists():
            self.stdout.write("Seed data already present; skipping.")
            return

        rng = random.Random(42)

        # --- users (with coarse locations for return-logistics distance) ---
        cities = list(CITY_COORDS)

        def _locate(user, city):
            user.city = city
            user.lat, user.lng = CITY_COORDS[city]
            user.save(update_fields=["city", "lat", "lng"])
            return user

        buyer = _locate(
            User.objects.create_user("buyer1", password="demo1234", role=Roles.BUYER),
            "Delhi",
        )
        reseller = _locate(
            User.objects.create_user("rahul", password="demo1234", role=Roles.BUYER),
            "Mumbai",
        )
        # Starting green-credit balances so the Rewards Store is usable on day one.
        award_credits(buyer, 80, "SEED", "Welcome bonus")
        award_credits(reseller, 50, "SEED", "Welcome bonus")
        seller = _locate(
            User.objects.create_user("seller1", password="demo1234", role=Roles.SELLER),
            "Bengaluru",
        )
        facility = _locate(
            User.objects.create_user(
                "facility1", password="demo1234", role=Roles.FACILITY
            ),
            "Bengaluru",
        )
        User.objects.create_superuser("admin", password="admin1234")
        extra_buyers = [
            _locate(
                User.objects.create_user(n, password="demo1234", role=Roles.BUYER),
                cities[i % len(cities)],
            )
            for i, n in enumerate(FIRST_NAMES)
        ]

        # --- size profiles (powers the apparel/footwear fit guide) ---
        # User.profile["sizes"] keyed by size dimension: waist (jeans), top
        # (S-XXL garments), shirt (collar), shoe_uk. The fit guide reads these to
        # recommend a size and warn on a mismatched pick.
        buyer.profile = {"sizes": {"waist": "32", "top": "M", "shirt": "40", "shoe_uk": "9"}}
        buyer.save(update_fields=["profile"])
        reseller.profile = {"sizes": {"waist": "34", "top": "L", "shirt": "42", "shoe_uk": "10"}}
        reseller.save(update_fields=["profile"])
        _SIZE_CHARTS = [
            {"waist": "30", "top": "S", "shirt": "38", "shoe_uk": "7"},
            {"waist": "36", "top": "XL", "shirt": "44", "shoe_uk": "11"},
            {"waist": "32", "top": "M", "shirt": "40", "shoe_uk": "8"},
            {"waist": "34", "top": "L", "shirt": "42", "shoe_uk": "9"},
        ]
        for i, b in enumerate(extra_buyers):
            b.profile = {"sizes": _SIZE_CHARTS[i % len(_SIZE_CHARTS)]}
            b.save(update_fields=["profile"])

        # --- products + NEW listings ---
        products = []
        for idx, item in enumerate(PRODUCTS):
            p = Product.objects.create(
                title=item["title"],
                description=item["description"],
                category=item["category"],
                mrp=item["mrp"],
                seller=seller,
                attributes=item.get("attributes", {}),
                image=product_image(
                    item["title"], item["image"], PALETTE[idx % len(PALETTE)]
                ),
            )
            products.append(p)
            # Stock = `stock` NEW listings (default 1). Bump it for products we
            # want comfortably in stock for the demo (e.g. the phone + cases).
            for _ in range(item.get("stock", 1)):
                unit = ItemUnit.objects.create(product=p, state=UnitStates.NEW)
                Listing.objects.create(
                    unit=unit,
                    source=ListingSources.NEW,
                    price=p.mrp,
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

        # --- buyer1 already owns an iPhone 15 (drives accessory-compatibility:
        #     an iPhone 14 case is incompatible, an iPhone 15 case fits). ---
        iphone = next((p for p in products if p.title == "Apple iPhone 15"), None)
        if iphone is not None:
            unit = ItemUnit.objects.create(
                product=iphone, state=UnitStates.SOLD, owner=buyer
            )
            listing = Listing.objects.create(
                unit=unit,
                source=ListingSources.NEW,
                price=iphone.mrp,
                state=ListingStates.SOLD,
            )
            Order.objects.create(
                buyer=buyer, listing=listing, state=OrderStates.DELIVERED
            )

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

        # --- one active USER_RESALE auction (Next Best Owner) ---
        p = products[10]
        graded = ai.grade(p.id)
        priced = ai.price(p.id, p.mrp, graded["grade"])
        unit = ItemUnit.objects.create(
            product=p,
            state=UnitStates.SOLD,
            owner=reseller,
            grade=graded["grade"],
            grade_confidence=graded["confidence"],
            est_value=priced["est_value"],
            purchased_at=timezone.now() - timedelta(days=300),
        )
        open_relist_auction(
            unit,
            reseller,
            source=ListingSources.USER_RESALE,
            est_value=priced["est_value"],
            band_lo=priced["band_lo"],
            band_hi=priced["band_hi"],
            grade=graded["grade"],
            pricing_extra={"source": "seed_user_resale"},
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

        # --- one unit near liquidation (watchlist drama) -> facility auction ---
        p = products[18]
        graded = ai.grade(p.id)
        priced = ai.price(p.id, p.mrp, graded["grade"])
        unit = ItemUnit.objects.create(
            product=p,
            state=UnitStates.AT_FACILITY,
            grade=graded["grade"],
            grade_confidence=graded["confidence"],
            est_value=priced["est_value"],
            arrived_at_facility=now,
            storage_cost_accrued=int(priced["est_value"] * 0.9),
            purchased_at=now - timedelta(days=60),
        )
        open_relist_auction(
            unit,
            facility,
            source=ListingSources.FACILITY_RELIST,
            est_value=priced["est_value"],
            band_lo=priced["band_lo"],
            band_hi=priced["band_hi"],
            grade=graded["grade"],
            pricing_extra={"source": "seed_facility_relist"},
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
