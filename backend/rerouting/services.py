"""Offer lifecycle: accept / decline a return-prevention offer.

Cash is notional in this prototype (no payment model) — accepting simply records
it and moves the order to PREVENTED. Green credits, however, are *real*: accepting
awards them to the buyer's account. Both actions are idempotent and owner-checked
by the view.
"""

import logging

from django.db import transaction
from django.utils import timezone

from catalog.models import UnitStates
from greencredits.logic import award_credits
from greencredits.models import GreenCreditAccount
from marketplace.models import OrderStates

from .models import OfferStatus, ReturnOffer

log = logging.getLogger(__name__)


def recommendation_for(unit):
    """Latest disposition recommendation for a unit, shaped for the facility UI.

    Replaces the old deterministic ai.route(): the decision was computed (LLM ∥
    EV) when the return was requested, so here we just read the freshest one.
    """
    from .models import DecisionStatus, RouteDecision

    decision = (
        RouteDecision.objects.filter(unit=unit, status=DecisionStatus.DONE)
        .order_by("-created_at")
        .first()
    )
    if not decision or not decision.route:
        return None
    return _shape_recommendation(decision)


def ensure_recommendation_for(unit):
    """Like recommendation_for, but compute one synchronously if none is ready.

    The async return->grading->rerouting chain may not have finished by the time
    a unit is physically received, which would leave the operator with no AI
    disposition. When no DONE decision exists we run the engine inline against the
    latest completed grading assessment for this unit, so intake always has a
    recommendation. Best-effort: any failure falls back to whatever (if anything)
    recommendation_for can read.
    """
    existing = recommendation_for(unit)
    if existing:
        return existing

    from grading.models import AssessmentStatus, GradingAssessment

    assessment = (
        GradingAssessment.objects.filter(unit=unit, status=AssessmentStatus.DONE)
        .order_by("-created_at")
        .first()
    )
    if assessment is None:
        # No completed grading yet — finish the most recent pending/running one
        # inline so we can still route. Rare: async grading has usually completed
        # long before a physical unit is received.
        pending = (
            GradingAssessment.objects.filter(
                unit=unit,
                status__in=[AssessmentStatus.PENDING, AssessmentStatus.RUNNING],
            )
            .order_by("-created_at")
            .first()
        )
        if pending is not None:
            try:
                from grading.orchestrator import run_all_sync

                run_all_sync(pending.id)
                pending.refresh_from_db()
                if pending.status == AssessmentStatus.DONE:
                    assessment = pending
            except Exception:  # noqa: BLE001 — never let grading break intake
                log.exception("inline grading completion failed for unit %s", unit.id)

    if assessment is None:
        return None

    try:
        from .tasks import decide_route_now

        decision = decide_route_now(assessment.id)
    except Exception:  # noqa: BLE001 — never let routing break intake
        log.exception("inline rerouting failed for unit %s", unit.id)
        decision = None

    if decision and decision.route:
        return _shape_recommendation(decision)
    return recommendation_for(unit)


def _shape_recommendation(decision):
    """Shape a RouteDecision into the dict the facility/health-card UI expects."""
    ranking = (decision.costs or {}).get("ev", {}).get("ranking", [])
    alternatives = [
        r["route"] for r in ranking if r.get("route") != decision.route
    ][:3]
    return {
        "recommendation": decision.route,
        "confidence": decision.confidence,
        "reasoning": decision.reasoning,
        "alternatives": alternatives,
        "decided_by": decision.decided_by,
        "source": "rerouting",
    }


def latest_offer(order):
    """Most recent pending offer for an order, or None."""
    return (
        ReturnOffer.objects.filter(order=order, status=OfferStatus.PENDING)
        .order_by("-created_at")
        .first()
    )


def _balance(user) -> int:
    account = GreenCreditAccount.objects.filter(user=user).first()
    return account.balance if account else 0


@transaction.atomic
def accept_offer(offer: ReturnOffer, actor) -> dict:
    """Buyer keeps the item: award real credits, mark the return prevented."""
    if offer.status != OfferStatus.PENDING:
        return {"status": offer.status, "balance": _balance(actor)}

    order = offer.order
    buyer = order.buyer

    if offer.green_credits:
        award_credits(
            buyer,
            offer.green_credits,
            "RETURN_PREVENTION",
            "Kept item instead of returning",
            order.id,
        )

    offer.status = OfferStatus.ACCEPTED
    offer.responded_at = timezone.now()
    offer.save(update_fields=["status", "responded_at", "updated_at"])

    order.transition(
        OrderStates.PREVENTED,
        actor=actor,
        cash_refund=offer.cash_refund,
        green_credits=offer.green_credits,
    )

    # The unit never comes back — it stays with the buyer.
    unit = order.listing.unit
    unit.owner = buyer
    unit.transition(UnitStates.SOLD, actor=actor, reason="return_prevented")

    return {
        "status": offer.status,
        "cash_refund": offer.cash_refund,
        "green_credits": offer.green_credits,
        "balance": _balance(buyer),
    }


@transaction.atomic
def decline_offer(offer: ReturnOffer, actor) -> dict:
    """Buyer declines: the normal return proceeds; we just record the decline."""
    if offer.status != OfferStatus.PENDING:
        return {"status": offer.status}
    offer.status = OfferStatus.DECLINED
    offer.responded_at = timezone.now()
    offer.save(update_fields=["status", "responded_at", "updated_at"])
    return {"status": offer.status}
