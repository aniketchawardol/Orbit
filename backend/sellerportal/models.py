from django.conf import settings
from django.db import models

from core.models import TimeStamped


class RuleActions(models.TextChoices):
    AUTO_RELIST = "AUTO_RELIST", "Auto relist"
    LIQUIDATE = "LIQUIDATE", "Liquidate"
    DONATE = "DONATE", "Donate"


class SellerRule(TimeStamped):
    """Rules-lite: one predicate form per rule."""

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rules"
    )
    min_grade = models.CharField(max_length=1, default="B")  # grade ≥ this
    min_recovery_pct = models.PositiveSmallIntegerField(default=60)
    action = models.CharField(
        max_length=15, choices=RuleActions.choices, default=RuleActions.AUTO_RELIST
    )
    active = models.BooleanField(default=True)

    GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}

    def matches(self, unit):
        if not unit.grade or unit.est_value is None or unit.product.mrp == 0:
            return False
        grade_ok = self.GRADE_ORDER.get(unit.grade, 9) <= self.GRADE_ORDER.get(
            self.min_grade, 9
        )
        recovery_pct = unit.est_value * 100 // unit.product.mrp
        return grade_ok and recovery_pct >= self.min_recovery_pct
