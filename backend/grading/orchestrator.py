"""Run the grading sources and aggregate them onto a GradingAssessment.

Each source is a small, independent function keyed by assessment id so it can run
as its own Celery subtask in parallel (see tasks.py) or inline (tests). Sources
write their own per-image artifacts with targeted column updates to avoid
clobbering each other, and return a JSON-serializable summary that the aggregate
step blends into the final scores.
"""

import logging
import time
from pathlib import Path

from django.core.files.storage import default_storage
from django.utils import timezone

from . import history, metadata, scoring
from .models import AssessmentContext, AssessmentStatus, GradingAssessment, GradingImage, ImageRole
from .providers import base as pbase
from .providers import mock as pmock
from .providers import registry

log = logging.getLogger(__name__)


def _mime(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")


def _read(path: str) -> bytes:
    try:
        with default_storage.open(path, "rb") as fh:
            return fh.read()
    except Exception:  # noqa: BLE001
        log.warning("could not read media %s", path)
        return b""


def _image_data(rows):
    out = []
    for r in rows:
        data = _read(r.path)
        if data:
            out.append(
                pbase.GradingImageData(
                    path=r.path, data=data, mime=_mime(r.path), role=r.role
                )
            )
    return out


def _rows(aid):
    uploaded = list(
        GradingImage.objects.filter(assessment_id=aid, role=ImageRole.UPLOADED).order_by("id")
    )
    reference = list(
        GradingImage.objects.filter(assessment_id=aid, role=ImageRole.REFERENCE).order_by("id")
    )
    return uploaded, reference


# --- individual sources -----------------------------------------------------

def run_vlm(aid) -> dict:
    a = GradingAssessment.objects.select_related("unit__product", "order").get(pk=aid)
    uploaded_rows, reference_rows = _rows(aid)
    product = a.unit.product
    claim = {
        "reason": getattr(a.order, "return_reason", "") or "OTHER",
        "comment": getattr(a.order, "return_comment", "") or "",
        "claimed_untouched": bool(getattr(a.order, "claimed_untouched", False)),
    }
    req = pbase.VLMRequest(
        product={
            "id": product.id,
            "title": product.title,
            "category": product.category,
            "description": product.description,
            "attributes": product.attributes or {},
            "mrp": product.mrp,
        },
        claim=claim,
        uploaded=_image_data(uploaded_rows),
        reference=_image_data(reference_rows),
    )

    provider = registry.get_vlm_provider()
    try:
        result = provider.grade(req)
        used = result.get("source") or provider.name
    except Exception:  # noqa: BLE001 — any provider failure -> deterministic mock
        log.exception("VLM provider %s failed; falling back to mock", provider.name)
        result = pmock.MockVLM().grade(req)
        used = "mock"

    # Persist per-image VLM notes + quality (targeted updates).
    for i, row in enumerate(uploaded_rows):
        pi = result.get("per_image") or []
        note = pi[i] if i < len(pi) else {}
        GradingImage.objects.filter(pk=row.pk).update(
            vlm_notes=note, quality=note.get("quality")
        )

    return {"vlm_result": result, "vlm_provider": used}


def run_similarity(aid) -> dict:
    uploaded_rows, reference_rows = _rows(aid)
    provider = registry.get_embedding_provider()
    try:
        result = provider.compare(_image_data(uploaded_rows), _image_data(reference_rows))
        used = result.get("source") or provider.name
    except Exception:  # noqa: BLE001
        log.exception("similarity provider failed")
        result = {"overall": None, "per_image": [], "duplicate_pairs": [], "source": "error"}
        used = "error"

    # Persist per-image perceptual hashes.
    by_path = {pi.get("path"): pi for pi in result.get("per_image", [])}
    for row in uploaded_rows:
        pi = by_path.get(row.path)
        if pi and pi.get("phash"):
            GradingImage.objects.filter(pk=row.pk).update(phash=pi["phash"])

    return {"similarity": result, "embedding_provider": used}


def run_metadata(aid) -> dict:
    a = GradingAssessment.objects.select_related("order").get(pk=aid)
    uploaded_rows, _ = _rows(aid)
    reference_time = getattr(a.order, "delivered_at", None)

    findings = []
    for row in uploaded_rows:
        server_meta = metadata.server_metadata_from_bytes(_read(row.path))
        analysis = metadata.analyze_image(row.client_metadata, server_meta, reference_time)
        analysis["path"] = row.path
        findings.append(analysis)
        GradingImage.objects.filter(pk=row.pk).update(server_metadata=server_meta)

    return {"metadata_findings": metadata.summarize(findings)}


def run_history(aid) -> dict:
    a = GradingAssessment.objects.select_related("order").get(pk=aid)
    buyer_id = getattr(a.order, "buyer_id", None)
    order_id = getattr(a.order, "id", None)
    if not buyer_id:
        return {"history_signals": {"history_fraud_signal": 0.0, "insufficient_history": True}}
    return {"history_signals": history.analyze(buyer_id, exclude_order_id=order_id)}


# --- aggregation ------------------------------------------------------------

def _persist_grader_attributes(product, vlm_result, vlm_provider) -> None:
    """Persist the grader-derived classification onto the product's open-ended
    attributes (JSONB) so routing and future assessments can reuse it without
    re-running the VLM. Only a real VLM (not the mock/empty fallback) may mutate
    catalog data, and we merge so user-entered keys (brand, color, ...) survive."""
    if vlm_provider in ("", "mock", "error", "unknown"):
        return
    derived = {
        "size_class": vlm_result.get("size_class"),
        "fragility": vlm_result.get("fragility"),
        "category": product.category or None,
    }
    derived = {k: v for k, v in derived.items() if v}
    if not derived:
        return
    attrs = dict(product.attributes or {})
    if all(attrs.get(k) == v for k, v in derived.items()):
        return  # already current — nothing to write
    attrs.update(derived)
    product.attributes = attrs
    product.save(update_fields=["attributes", "updated_at"])
    log.info("persisted grader attributes for product %s: %s", product.id, derived)


def aggregate(aid, partials) -> None:
    """Merge source outputs, blend scores, finalize the assessment."""
    merged = {}
    for part in partials:
        if isinstance(part, dict):
            merged.update(part)

    a = GradingAssessment.objects.get(pk=aid)
    vlm_result = merged.get("vlm_result", {})
    similarity = merged.get("similarity", {})
    metadata_findings = merged.get("metadata_findings", {})
    history_signals = merged.get("history_signals", {})

    claim = {"reason": getattr(a.order, "return_reason", "") or "OTHER"}
    blended = scoring.blend(vlm_result, similarity, metadata_findings, history_signals, claim)

    a.vlm_result = vlm_result
    a.similarity = similarity
    a.metadata_findings = metadata_findings
    a.history_signals = history_signals
    a.vlm_provider = merged.get("vlm_provider", "")
    a.embedding_provider = merged.get("embedding_provider", "")
    a.quality_score = blended["quality_score"]
    a.fraud_score = blended["fraud_score"]
    a.confidence = blended["confidence"]
    a.suggested_grade = blended["suggested_grade"]
    a.scores = blended["scores"]
    a.status = AssessmentStatus.DONE
    a.latency_ms = int(max(0, (timezone.now() - a.created_at).total_seconds() * 1000))
    a.save()
    log.info(
        "assessment %s done: grade=%s quality=%.2f fraud=%.2f conf=%.2f",
        aid, a.suggested_grade, a.quality_score, a.fraud_score, a.confidence,
    )

    # Persist the grader's durable classification (size/fragility/category) onto
    # the product so routing and future assessments reuse it. Best-effort: an
    # attribute write must never break grading.
    try:
        _persist_grader_attributes(a.unit.product, vlm_result, a.vlm_provider)
    except Exception:  # noqa: BLE001
        log.exception("could not persist grader attributes for assessment %s", aid)

    # Hand off to the rerouting engine (RESELL/REFURBISH/P2P/DONATE). Only return
    # assessments get a disposition decision, and a failure here must never break
    # grading itself.
    if a.context == AssessmentContext.RETURN:
        try:
            from rerouting.tasks import decide_route

            decide_route.delay(a.id)
        except Exception:  # noqa: BLE001 — broker down shouldn't break grading
            log.exception("could not enqueue rerouting for assessment %s", aid)
    elif a.context == AssessmentContext.RESALE:
        # Hand off to the Next Best Owner engine: price the item, match buyers,
        # and start the Dutch auction. A failure here must never break grading.
        try:
            from nextowner.tasks import price_and_match

            price_and_match.delay(a.id)
        except Exception:  # noqa: BLE001 — broker down shouldn't break grading
            log.exception("could not enqueue nextowner pricing for assessment %s", aid)


def run_all_sync(aid) -> None:
    """Run every source then aggregate, inline. Used in eager/test mode and as a
    safety net. Each source is isolated so one failure can't sink the rest."""
    a = GradingAssessment.objects.get(pk=aid)
    a.status = AssessmentStatus.RUNNING
    a.save(update_fields=["status", "updated_at"])

    partials = []
    for fn in (run_vlm, run_similarity, run_metadata, run_history):
        try:
            partials.append(fn(aid))
        except Exception:  # noqa: BLE001
            log.exception("grading source %s failed for assessment %s", fn.__name__, aid)
    aggregate(aid, partials)
