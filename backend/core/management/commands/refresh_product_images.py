"""Re-import product images from the images/ folder into existing products.

`seed_demo` copies each catalog photo into media storage once and is idempotent,
so swapping a file in images/ afterwards has no effect — the product still points
at the originally-seeded copy. Run this to push updated photos into the database:

    python manage.py refresh_product_images            # refresh every product
    python manage.py refresh_product_images boldfit    # only matching titles

Only products whose source file actually exists are touched, so a missing photo
never replaces a real image with a placeholder.
"""

from django.core.management.base import BaseCommand

from catalog.models import Product
from core.management.commands.seed_demo import (
    PALETTE,
    PRODUCTS,
    _image_dirs,
    product_image,
)


class Command(BaseCommand):
    help = "Re-import product images from the images/ folder (updates existing products)."

    def add_arguments(self, parser):
        parser.add_argument(
            "titles",
            nargs="*",
            help="Optional title substrings; only matching products are refreshed.",
        )

    def handle(self, *args, **options):
        filters = [t.lower() for t in options["titles"]]
        updated = 0
        skipped_missing = 0

        for idx, item in enumerate(PRODUCTS):
            title = item["title"]
            filename = item["image"]
            if filters and not any(f in title.lower() for f in filters):
                continue

            # Only refresh from a real source file — never clobber a product with
            # a generated placeholder.
            if not any((base / filename).is_file() for base in _image_dirs()):
                skipped_missing += 1
                continue

            products = list(Product.objects.filter(title=title))
            if not products:
                continue

            color = PALETTE[idx % len(PALETTE)]
            for p in products:
                # Fresh upload per product so the file pointer starts at zero.
                upload = product_image(title, filename, color)
                p.image.save(filename, upload, save=True)
                updated += 1
                self.stdout.write(f"Updated image for {title} (#{p.id})")

        if skipped_missing:
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped {skipped_missing} product(s) with no source file."
                )
            )
        self.stdout.write(
            self.style.SUCCESS(f"Refreshed {updated} product image(s).")
        )
