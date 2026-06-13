"""Celery tasks for return rerouting.

The two strategies — EV and LLM — run as parallel subtasks (a chord) and are
blended in the callback. Each subtask reads what it needs off the RouteDecision
row by id, so broker payloads stay tiny. In eager mode (tests / no broker) we run
inline. A failing subtask returns an empty partial and never sinks the chord.
"""

import logging

from celery import chord, group, shared_task
from django.conf import settings

from . import strategies
from .models import DecisionStatus, RouteDecision

log = logging.getLogger(__name__)


@shared_task(name="rerouting.ev")
def ev_subtask(decision_id):
    try:
        decision = RouteDecision.objects.get(pk=decision_id)
        return {"ev": strategies.ev_result(decision.costs or {})}
    except Exception:  # noqa: BLE001 — never sink the chord
        log.exception("EV strategy failed for decision %s", decision_id)
        return {"ev": {}}


@shared_task(name="rerouting.llm")
def llm_subtask(decision_id):
    try:
        decision = RouteDecision.objects.get(pk=decision_id)
        return {
            "llm": strategies.llm_result(
                decision.context or {}, decision.costs or {}
            )
        }
    except Exception:  # noqa: BLE001 — never sink the chord
        log.exception("LLM strategy failed for decision %s", decision_id)
        return {"llm": None}


@shared_task(name="rerouting.finalize")
def finalize_subtask(partials, decision_id):
    ev, llm_out = {}, None
    for part in partials or []:
        if not isinstance(part, dict):
            continue
        if "ev" in part:
            ev = part["ev"] or {}
        if "llm" in part:
            llm_out = part["llm"]
    try:
        decision = RouteDecision.objects.get(pk=decision_id)
    except RouteDecision.DoesNotExist:
        return
    strategies.finalize(decision, ev, llm_out)


@shared_task(name="rerouting.decide_route")
def decide_route(assessment_id):
    """Entry point: build context, then run EV ∥ LLM in parallel and finalize."""
    from grading.models import GradingAssessment

    try:
        assessment = GradingAssessment.objects.select_related(
            "unit", "order"
        ).get(pk=assessment_id)
    except GradingAssessment.DoesNotExist:
        return

    decision = _create_decision(assessment)
    if decision is None:
        return

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        _run_sync(decision.id)
        return

    chord(group(ev_subtask.s(decision.id), llm_subtask.s(decision.id)))(
        finalize_subtask.s(decision.id)
    )


def _create_decision(assessment):
    try:
        context, cost = strategies.build_context(assessment)
    except Exception:  # noqa: BLE001 — bad data shouldn't break grading
        log.exception("could not build rerouting context for assessment %s", assessment.id)
        return None
    decision, _ = RouteDecision.objects.update_or_create(
        assessment=assessment,
        defaults={
            "order": assessment.order,
            "unit": assessment.unit,
            "status": DecisionStatus.RUNNING,
            "route": "",
            "decided_by": "",
            "reasoning": "",
            "error": "",
            "costs": cost,
            "context": context,
        },
    )
    return decision


def _run_sync(decision_id):
    ev = ev_subtask(decision_id)
    llm_out = llm_subtask(decision_id)
    finalize_subtask([ev, llm_out], decision_id)


def decide_route_now(assessment_id):
    """Synchronous variant of decide_route.

    Builds the decision and runs EV ∥ LLM inline, returning the finalized
    RouteDecision (or None). Used as a fallback when a disposition is needed
    immediately — e.g. facility intake — and the async chain hasn't produced one
    yet. Idempotent: _create_decision update_or_creates on the assessment.
    """
    from grading.models import GradingAssessment

    try:
        assessment = GradingAssessment.objects.select_related(
            "unit", "order"
        ).get(pk=assessment_id)
    except GradingAssessment.DoesNotExist:
        return None

    decision = _create_decision(assessment)
    if decision is None:
        return None

    _run_sync(decision.id)
    try:
        decision.refresh_from_db()
    except RouteDecision.DoesNotExist:
        return None
    return decision
