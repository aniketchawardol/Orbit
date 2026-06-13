from django.contrib import admin

from .models import GradingAssessment, GradingImage


class GradingImageInline(admin.TabularInline):
    model = GradingImage
    extra = 0
    readonly_fields = ("path", "role", "phash", "quality", "client_metadata", "server_metadata", "vlm_notes")
    can_delete = False


@admin.register(GradingAssessment)
class GradingAssessmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "unit",
        "context",
        "status",
        "suggested_grade",
        "quality_score",
        "fraud_score",
        "confidence",
        "vlm_provider",
        "created_at",
    )
    list_filter = ("status", "context", "vlm_provider", "suggested_grade")
    search_fields = ("unit__id", "order__id")
    readonly_fields = (
        "unit",
        "order",
        "triggered_by",
        "context",
        "status",
        "vlm_provider",
        "embedding_provider",
        "vlm_result",
        "similarity",
        "metadata_findings",
        "history_signals",
        "quality_score",
        "fraud_score",
        "confidence",
        "suggested_grade",
        "scores",
        "error",
        "latency_ms",
        "created_at",
        "updated_at",
    )
    inlines = [GradingImageInline]
