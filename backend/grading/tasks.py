"""Celery tasks for return grading.

The pipeline fans the four sources out as parallel subtasks (a chord) and blends
them in the callback. Image bytes are never passed through the broker — each
subtask reads what it needs from storage by assessment id — so broker payloads
stay tiny. In eager mode (tests / no broker) we run everything inline.

Every subtask is wrapped so it can't sink the chord: a failing source returns an
empty partial and the rest still aggregate.
"""

import logging

from celery import chord, group, shared_task
from django.conf import settings

from . import orchestrator
from .models import AssessmentStatus, GradingAssessment

log = logging.getLogger(__name__)


def _safe(fn, aid):
    try:
        return fn(aid)
    except Exception:  # noqa: BLE001 — never fail the chord
        log.exception("grading subtask %s failed for assessment %s", fn.__name__, aid)
        return {}


@shared_task(name="grading.vlm")
def vlm_subtask(aid):
    return _safe(orchestrator.run_vlm, aid)


@shared_task(name="grading.similarity")
def similarity_subtask(aid):
    return _safe(orchestrator.run_similarity, aid)


@shared_task(name="grading.metadata")
def metadata_subtask(aid):
    return _safe(orchestrator.run_metadata, aid)


@shared_task(name="grading.history")
def history_subtask(aid):
    return _safe(orchestrator.run_history, aid)


@shared_task(name="grading.aggregate")
def aggregate_subtask(partials, aid):
    orchestrator.aggregate(aid, partials)


@shared_task(name="grading.run_assessment")
def run_assessment(aid):
    """Entry point. Runs the four sources in parallel then aggregates."""
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        orchestrator.run_all_sync(aid)
        return

    GradingAssessment.objects.filter(pk=aid).update(status=AssessmentStatus.RUNNING)
    header = group(
        vlm_subtask.s(aid),
        similarity_subtask.s(aid),
        metadata_subtask.s(aid),
        history_subtask.s(aid),
    )
    try:
        chord(header)(aggregate_subtask.s(aid))
    except Exception:  # noqa: BLE001 — broker hiccup -> run inline so we still grade
        log.exception("chord dispatch failed for assessment %s; running inline", aid)
        orchestrator.run_all_sync(aid)
