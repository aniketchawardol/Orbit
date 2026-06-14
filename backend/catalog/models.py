from django.conf import settings
from django.db import models

from core.models import StatefulItem, TimeStamped


class ProductOrigin(models.TextChoices):
    PLATFORM = "PLATFORM", "Platform catalog"
    EXTERNAL = "EXTERNAL", "User-listed (brought from outside)"


class Product(TimeStamped):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50)
    mrp = models.PositiveIntegerField(help_text="₹")
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    # Where the product came from. PLATFORM = seller-listed catalog item (has a
    # reference image for grading). EXTERNAL = a brand-new item a user brought
    # from outside to resell — no reference photo, so grading runs in VLM
    # anomaly/quality mode instead of image comparison.
    origin = models.CharField(
        max_length=10, choices=ProductOrigin.choices, default=ProductOrigin.PLATFORM
    )
    # Open-ended catalog attributes (JSONB): per-category fields such as
    # {"brand": "...", "material": "...", "size": "...", "compatible_model": "..."}.
    # Fed to the AI grader so inspection criteria adapt to the product.
    attributes = models.JSONField(default=dict, blank=True)
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="products"
    )

    def __str__(self):
        return self.title


class UnitStates(models.TextChoices):
    NEW = "NEW", "New stock"
    SOLD = "SOLD", "Sold"
    RETURN_PENDING = "RETURN_PENDING", "Return initiated"
    AT_FACILITY = "AT_FACILITY", "At facility"
    RELISTED = "RELISTED", "Relisted"
    LIQUIDATE = "LIQUIDATE", "Storage cost exceeded"
    DONATED = "DONATED", "Donated"


class ItemUnit(StatefulItem):
    """One physical unit — the central model."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="units"
    )
    grade = models.CharField(max_length=1, blank=True, null=True)
    grade_confidence = models.FloatField(blank=True, null=True)
    untouched = models.BooleanField(default=False)
    est_value = models.PositiveIntegerField(blank=True, null=True, help_text="₹")
    arrived_at_facility = models.DateTimeField(blank=True, null=True)
    storage_cost_accrued = models.PositiveIntegerField(default=0, help_text="₹")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="owned_units",
    )

    class Meta:
        indexes = [models.Index(fields=["state"])]

    def save(self, *args, **kwargs):
        if not self.state:
            self.state = UnitStates.NEW
        super().save(*args, **kwargs)

    def unit_ref(self):
        return self

    def __str__(self):
        return f"{self.product.title} #{self.pk} [{self.state}]"


class UnitEvent(TimeStamped):
    """Append-only audit trail; powers the Health Card screen."""

    unit = models.ForeignKey(ItemUnit, on_delete=models.CASCADE, related_name="events")
    type = models.CharField(max_length=40)
    payload = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True
    )

    class Meta:
        ordering = ["created_at"]
