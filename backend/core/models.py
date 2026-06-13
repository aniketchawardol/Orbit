from django.contrib.auth.models import AbstractUser
from django.db import models


class Roles(models.TextChoices):
    BUYER = "BUYER", "Buyer"
    SELLER = "SELLER", "Seller"
    FACILITY = "FACILITY", "Facility"


class User(AbstractUser):
    role = models.CharField(max_length=10, choices=Roles.choices, default=Roles.BUYER)
    # Buyers also resell; no extra role needed.
    # Open-ended buyer/seller profile (JSONB): size chart, current devices,
    # preferences, etc. Used by AI grading and future personalization.
    profile = models.JSONField(default=dict, blank=True)


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class StatefulItem(TimeStamped):
    """Base for anything with a lifecycle. transition() writes the audit event."""

    state = models.CharField(max_length=30)
    state_changed_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def unit_ref(self):
        """Subclasses return the ItemUnit this object concerns (or None)."""
        return None

    def transition(self, new_state, actor=None, **payload):
        from catalog.models import UnitEvent

        old = self.state
        self.state = new_state
        self.save()
        unit = self.unit_ref()
        if unit is not None:
            UnitEvent.objects.create(
                unit=unit,
                type=new_state,
                actor=actor,
                payload={"from": old, "model": type(self).__name__, **payload},
            )
        return self
