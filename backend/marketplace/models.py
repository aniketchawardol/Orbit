from django.conf import settings
from django.db import models

from catalog.models import ItemUnit
from core.models import StatefulItem


class ListingSources(models.TextChoices):
    NEW = "NEW", "New"
    FACILITY_RELIST = "FACILITY_RELIST", "Facility relist"
    USER_RESALE = "USER_RESALE", "User resale"
    SELLER_RETURN = "SELLER_RETURN", "Seller return relist"


class ListingStates(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    RESERVED = "RESERVED", "Reserved"
    SOLD = "SOLD", "Sold"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class Listing(StatefulItem):
    # FK (not OneToOne): the same physical unit is relisted across owners over
    # its life. Invariant enforced in code: at most ONE ACTIVE/RESERVED
    # listing per unit at any time.
    unit = models.ForeignKey(
        ItemUnit, on_delete=models.CASCADE, related_name="listings"
    )
    source = models.CharField(max_length=20, choices=ListingSources.choices)
    price = models.PositiveIntegerField(help_text="₹")
    band_lo = models.PositiveIntegerField(blank=True, null=True)
    band_hi = models.PositiveIntegerField(blank=True, null=True)
    photos = models.JSONField(default=list, blank=True)  # media paths
    lister = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="listings_created",
    )

    class Meta:
        indexes = [models.Index(fields=["state", "source"])]

    def save(self, *args, **kwargs):
        if not self.state:
            self.state = ListingStates.ACTIVE
        super().save(*args, **kwargs)

    def unit_ref(self):
        return self.unit


class OrderStates(models.TextChoices):
    PLACED = "PLACED", "Placed"
    DELIVERED = "DELIVERED", "Delivered"
    RETURN_REQUESTED = "RETURN_REQUESTED", "Return requested"
    RETURN_RECEIVED = "RETURN_RECEIVED", "Return received"
    REFUNDED = "REFUNDED", "Refunded"
    SETTLED = "SETTLED", "Settled"


class ReturnReasons(models.TextChoices):
    DIDNT_MATCH = "DIDNT_MATCH", "Didn't match description"
    WRONG_SIZE = "WRONG_SIZE", "Wrong size / fit"
    CHANGED_MIND = "CHANGED_MIND", "Changed my mind"
    DEFECTIVE = "DEFECTIVE", "Damaged / defective"
    OTHER = "OTHER", "Other"


class Order(StatefulItem):
    """Return data folded in — no separate ReturnRequest model."""

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders"
    )
    listing = models.ForeignKey(
        Listing, on_delete=models.CASCADE, related_name="orders"
    )
    return_reason = models.CharField(
        max_length=20, choices=ReturnReasons.choices, blank=True
    )
    claimed_untouched = models.BooleanField(default=False)
    photos = models.JSONField(default=list, blank=True)  # return-time photos (buyer)

    class Meta:
        indexes = [models.Index(fields=["state"])]

    def save(self, *args, **kwargs):
        if not self.state:
            self.state = OrderStates.PLACED
        super().save(*args, **kwargs)

    def unit_ref(self):
        return self.listing.unit
