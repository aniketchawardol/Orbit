"""AI return-grading data model.

A GradingAssessment is the durable, multi-source verdict for one return (or,
later, resale/facility) event. It deliberately keeps every raw signal —
VLM output, image similarity, EXIF findings, buyer-history snapshot — alongside
the blended scores so the (deferred) decision engine and audits can re-reason
over them without re-running the models. Nothing here is shown to the buyer.
"""

from django.conf import settings
from django.db import models

from catalog.models import ItemUnit
from core.models import TimeStamped


class AssessmentContext(models.TextChoices):
    RETURN = "RETURN", "Return"
    RESALE = "RESALE", "Resale"
    FACILITY = "FACILITY", "Facility intake"


class AssessmentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    DONE = "DONE", "Done"
    FAILED = "FAILED", "Failed"


class ImageRole(models.TextChoices):
    UPLOADED = "UPLOADED", "Buyer upload"
    REFERENCE = "REFERENCE", "Reference (listed)"


class GradingAssessment(TimeStamped):
    """One grading run for a unit. Scores are blended from several sources so a
    single deceptive source (doctored photo, false reason) can't dominate."""

    unit = models.ForeignKey(
        ItemUnit, on_delete=models.CASCADE, related_name="assessments"
    )
    # Order is the usual trigger but kept nullable + string-referenced to avoid
    # a hard import cycle (marketplace imports catalog, not the reverse).
    order = models.ForeignKey(
        "marketplace.Order",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="assessments",
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="triggered_assessments",
    )
    context = models.CharField(
        max_length=12, choices=AssessmentContext.choices, default=AssessmentContext.RETURN
    )
    status = models.CharField(
        max_length=10, choices=AssessmentStatus.choices, default=AssessmentStatus.PENDING
    )

    # Which providers actually ran (resolved names, e.g. "gemini"/"mock"/"phash").
    vlm_provider = models.CharField(max_length=30, blank=True)
    embedding_provider = models.CharField(max_length=30, blank=True)

    # Raw per-source signals (kept verbatim for audit / re-scoring).
    vlm_result = models.JSONField(default=dict, blank=True)
    similarity = models.JSONField(default=dict, blank=True)
    metadata_findings = models.JSONField(default=dict, blank=True)
    history_signals = models.JSONField(default=dict, blank=True)

    # Blended verdict (0..1). Higher quality = better condition; higher fraud =
    # more suspicious; confidence = cross-source agreement.
    quality_score = models.FloatField(blank=True, null=True)
    fraud_score = models.FloatField(blank=True, null=True)
    confidence = models.FloatField(blank=True, null=True)
    suggested_grade = models.CharField(max_length=1, blank=True)  # A/B/C/D

    # Extensible, explainable breakdown of how each score was reached.
    scores = models.JSONField(default=dict, blank=True)

    error = models.TextField(blank=True)
    latency_ms = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["unit", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Assessment #{self.pk} unit={self.unit_id} [{self.status}]"


class GradingImage(TimeStamped):
    """One image considered by an assessment — either a buyer upload or a
    reference (listed) photo — with its per-image signals."""

    assessment = models.ForeignKey(
        GradingAssessment, on_delete=models.CASCADE, related_name="images"
    )
    path = models.CharField(max_length=300)  # relative media path
    role = models.CharField(max_length=10, choices=ImageRole.choices)

    # EXIF/device data the client extracted BEFORE compression (fraud signals).
    client_metadata = models.JSONField(default=dict, blank=True)
    # What the server could derive from the stored bytes (dimensions, etc.).
    server_metadata = models.JSONField(default=dict, blank=True)

    phash = models.CharField(max_length=64, blank=True)  # perceptual hash (hex)
    embedding_ref = models.CharField(max_length=200, blank=True)  # future: vector id
    vlm_notes = models.JSONField(default=dict, blank=True)  # per-image VLM findings
    quality = models.FloatField(blank=True, null=True)  # 0..1 image usability

    class Meta:
        indexes = [models.Index(fields=["assessment", "role"])]

    def __str__(self):
        return f"{self.role} {self.path}"
