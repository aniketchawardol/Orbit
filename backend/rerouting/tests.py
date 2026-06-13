"""Tests for the return rerouting engine.

Fast, hermetic unit tests for the pure logic (deterministic JSON recovery,
size/fragility normalization, the risk-adjusted cost model, the EV optimizer and
the offer split) plus DB-backed tests for the offer accept/decline flow and the
end-to-end return -> grade -> reroute pipeline.

Run with mock providers so nothing hits the network:
    CELERY_TASK_ALWAYS_EAGER=1 GRADING_VLM_PROVIDER=mock \
        REROUTING_LLM_PROVIDER=mock python manage.py test rerouting
"""

from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from grading.jsonio import extract_json
from grading.prompts import normalize_vlm_output

from . import costs, optimizer, strategies


# --------------------------------------------------------------------------- #
# Deterministic JSON recovery (the gemma "<thought>" / prose problem)
# --------------------------------------------------------------------------- #
class JsonIoTests(SimpleTestCase):
    def test_plain_object(self):
        self.assertEqual(extract_json('{"route": "RESELL"}'), {"route": "RESELL"})

    def test_closed_think_tag_before_json(self):
        text = "<think>weighing options</think>\n{\"route\": \"RESELL\"}"
        self.assertEqual(extract_json(text), {"route": "RESELL"})

    def test_thought_tag_with_braces_inside(self):
        text = "<thought>maybe {garbage} here</thought>{\"route\": \"DONATE\"}"
        self.assertEqual(extract_json(text)["route"], "DONATE")

    def test_fenced_block(self):
        text = "```json\n{\"route\": \"P2P\"}\n```"
        self.assertEqual(extract_json(text)["route"], "P2P")

    def test_prose_around_json(self):
        text = "Sure! {\"route\": \"REFURBISH\"} — hope that helps."
        self.assertEqual(extract_json(text)["route"], "REFURBISH")

    def test_nested_objects_fast_path(self):
        obj = extract_json('{"a": {"b": 1}, "route": "RESELL"}')
        self.assertEqual(obj["a"]["b"], 1)
        self.assertEqual(obj["route"], "RESELL")

    def test_trailing_comma_repair(self):
        self.assertEqual(extract_json('{"route": "DONATE",}')["route"], "DONATE")

    def test_brace_inside_string_is_ignored(self):
        text = 'noise {"reasoning": "use } carefully", "route": "P2P"} tail'
        self.assertEqual(extract_json(text)["route"], "P2P")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            extract_json("   ")

    def test_no_object_raises(self):
        with self.assertRaises(ValueError):
            extract_json("just prose, no json at all")


# --------------------------------------------------------------------------- #
# size_class / fragility normalization
# --------------------------------------------------------------------------- #
class NormalizeTests(SimpleTestCase):
    def _norm(self, **over):
        base = {
            "item_matches_reference": True,
            "quality_estimate": 0.9,
            "suggested_grade": "A",
            "confidence": 0.8,
        }
        base.update(over)
        return normalize_vlm_output(base)

    def test_defaults_when_absent(self):
        out = self._norm()
        self.assertEqual(out["size_class"], "small")
        self.assertEqual(out["fragility"], "rigid")

    def test_preserves_valid_values(self):
        out = self._norm(size_class="big", fragility="delicate")
        self.assertEqual(out["size_class"], "big")
        self.assertEqual(out["fragility"], "delicate")

    def test_invalid_value_falls_back(self):
        out = self._norm(size_class="enormous", fragility="squishy")
        self.assertEqual(out["size_class"], "small")
        self.assertEqual(out["fragility"], "rigid")


# --------------------------------------------------------------------------- #
# Risk-adjusted cost model + EV optimizer
# --------------------------------------------------------------------------- #
class CostModelTests(SimpleTestCase):
    def _best(self, **kw):
        params = dict(
            mrp=5000, paid=4000, est_value=2500, quality=0.9, fraud=0.05,
            size_class="small", fragility="rigid", distance_km=100, storage=0,
        )
        params.update(kw)
        return optimizer.optimize(costs.compute(**params))

    def test_high_quality_low_fraud_resells(self):
        res = self._best(quality=0.9, fraud=0.05, est_value=3000)
        self.assertEqual(res["route"], "RESELL")
        self.assertGreater(res["profit"], 0)

    def test_low_quality_prefers_refurbish_over_resell(self):
        # Bad condition tanks resale realization; repair unlocks value.
        res = self._best(quality=0.2, est_value=800)
        self.assertNotEqual(res["route"], "RESELL")
        self.assertEqual(res["route"], "REFURBISH")

    def test_high_fraud_penalizes_resale(self):
        # Fraud strongly discounts as-is resale; refurb inspection mitigates it.
        res = self._best(quality=0.7, fraud=0.8, est_value=2500)
        self.assertNotEqual(res["route"], "RESELL")

    def test_donate_is_the_loss_floor_when_everything_bad(self):
        res = self._best(
            quality=0.15, fraud=0.9, est_value=500,
            size_class="big", fragility="delicate", distance_km=800,
        )
        self.assertEqual(res["route"], "DONATE")
        self.assertGreater(res["loss"], 0)

    def test_quality_changes_realization(self):
        c_hi = costs.compute(
            mrp=5000, paid=4000, est_value=2500, quality=0.95, fraud=0.0,
            size_class="small", fragility="rigid", distance_km=100,
        )
        c_lo = costs.compute(
            mrp=5000, paid=4000, est_value=2500, quality=0.2, fraud=0.0,
            size_class="small", fragility="rigid", distance_km=100,
        )
        self.assertGreater(
            c_hi["routes"]["RESELL"]["realize"],
            c_lo["routes"]["RESELL"]["realize"],
        )

    def test_big_delicate_costs_more_per_km(self):
        small = costs.compute(
            mrp=5000, paid=4000, est_value=2500, quality=0.8, fraud=0.0,
            size_class="small", fragility="rigid", distance_km=100,
        )
        big = costs.compute(
            mrp=5000, paid=4000, est_value=2500, quality=0.8, fraud=0.0,
            size_class="big", fragility="delicate", distance_km=100,
        )
        self.assertGreater(
            big["routes"]["RESELL"]["costs"],
            small["routes"]["RESELL"]["costs"],
        )


class OptimizerTests(SimpleTestCase):
    def test_argmax_and_loss(self):
        cost = {
            "routes": {
                "RESELL": {"profit": -100},
                "REFURBISH": {"profit": -40},
                "P2P": {"profit": -250},
                "DONATE": {"profit": -60},
            }
        }
        res = optimizer.optimize(cost)
        self.assertEqual(res["route"], "REFURBISH")
        self.assertEqual(res["loss"], 40)
        self.assertEqual(res["ranking"][0]["route"], "REFURBISH")

    def test_empty(self):
        res = optimizer.optimize({})
        self.assertEqual(res["route"], "")
        self.assertEqual(res["loss"], 0)


# --------------------------------------------------------------------------- #
# DB-backed helpers
# --------------------------------------------------------------------------- #
def _order_graph():
    from catalog.models import ItemUnit, Product, UnitStates
    from core.models import User
    from marketplace.models import Listing, ListingSources, Order, OrderStates

    buyer = User.objects.create_user("buyer", password="x", city="Delhi",
                                     lat=28.6139, lng=77.2090)
    seller = User.objects.create_user("seller", password="x", city="Bengaluru",
                                       lat=12.9716, lng=77.5946)
    product = Product.objects.create(
        title="Blender", category="appliances", mrp=3000, seller=seller
    )
    unit = ItemUnit.objects.create(
        product=product, owner=buyer, state=UnitStates.RETURN_PENDING, est_value=1500
    )
    listing = Listing.objects.create(
        unit=unit, source=ListingSources.NEW, price=2800, lister=seller
    )
    order = Order.objects.create(
        buyer=buyer, listing=listing, state=OrderStates.RETURN_REQUESTED,
        return_reason="DEFECTIVE", delivered_at=timezone.now(),
    )
    return buyer, seller, product, unit, listing, order


# --------------------------------------------------------------------------- #
# Keep-it offer split
# --------------------------------------------------------------------------- #
class OfferSplitTests(TestCase):
    def _decision(self, quality, fraud, paid):
        from .models import DecisionStatus, RouteDecision

        _, _, _, unit, _, order = _order_graph()
        return RouteDecision.objects.create(
            order=order, unit=unit, status=DecisionStatus.DONE,
            context={"quality": quality, "fraud": fraud, "paid": paid},
        )

    def test_offer_is_cash_majority_and_cheaper_than_loss(self):
        decision = self._decision(quality=0.5, fraud=0.1, paid=600)
        offer = strategies.maybe_offer(decision, {"loss": 370})
        self.assertIsNotNone(offer)
        # make_whole = min(600*0.5, 370) = 300 -> cash 180, credits 120
        self.assertEqual(offer.cash_refund, 180)
        self.assertEqual(offer.green_credits, 120)
        self.assertGreater(offer.cash_refund, offer.green_credits)  # cash majority
        self.assertEqual(offer.company_cost, 288)  # 180 + 0.9*120
        self.assertLess(offer.company_cost, offer.expected_loss)  # worth offering

    def test_no_offer_when_fraud_high(self):
        decision = self._decision(quality=0.6, fraud=0.9, paid=600)
        self.assertIsNone(strategies.maybe_offer(decision, {"loss": 370}))

    def test_no_offer_when_quality_too_low(self):
        decision = self._decision(quality=0.1, fraud=0.05, paid=600)
        self.assertIsNone(strategies.maybe_offer(decision, {"loss": 370}))

    def test_no_offer_when_no_loss(self):
        decision = self._decision(quality=0.6, fraud=0.05, paid=600)
        self.assertIsNone(strategies.maybe_offer(decision, {"loss": 0}))


# --------------------------------------------------------------------------- #
# Accept / decline flow
# --------------------------------------------------------------------------- #
class OfferFlowTests(TestCase):
    def setUp(self):
        from .models import DecisionStatus, OfferStatus, ReturnOffer, RouteDecision

        self.OfferStatus = OfferStatus
        self.buyer, _, _, self.unit, _, self.order = _order_graph()
        self.decision = RouteDecision.objects.create(
            order=self.order, unit=self.unit, status=DecisionStatus.DONE,
            route="DONATE", context={"quality": 0.5, "fraud": 0.1, "paid": 600},
        )
        self.offer = ReturnOffer.objects.create(
            decision=self.decision, order=self.order, status=OfferStatus.PENDING,
            cash_refund=180, green_credits=120, expected_loss=370, company_cost=288,
            message="Keep it and get ₹180 back plus 120 credits.",
        )

    def _client(self):
        from rest_framework.test import APIClient

        c = APIClient()
        c.force_authenticate(self.buyer)
        return c

    def test_accept_prevents_return_and_awards_real_credits(self):
        from catalog.models import UnitStates
        from greencredits.models import GreenCreditAccount
        from marketplace.models import OrderStates

        resp = self._client().post(f"/api/rerouting/offers/{self.offer.id}/accept")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], self.OfferStatus.ACCEPTED)
        self.assertEqual(body["balance"], 120)

        self.offer.refresh_from_db()
        self.order.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(self.offer.status, self.OfferStatus.ACCEPTED)
        self.assertEqual(self.order.state, OrderStates.PREVENTED)
        self.assertEqual(self.unit.state, UnitStates.SOLD)
        self.assertEqual(self.unit.owner_id, self.buyer.id)

        account = GreenCreditAccount.objects.get(user=self.buyer)
        self.assertEqual(account.balance, 120)

    def test_accept_is_idempotent(self):
        client = self._client()
        client.post(f"/api/rerouting/offers/{self.offer.id}/accept")
        resp = client.post(f"/api/rerouting/offers/{self.offer.id}/accept")
        self.assertEqual(resp.status_code, 200)
        # Credits awarded only once.
        from greencredits.models import GreenCreditAccount

        self.assertEqual(
            GreenCreditAccount.objects.get(user=self.buyer).balance, 120
        )

    def test_decline_records_and_keeps_order_in_return(self):
        from marketplace.models import OrderStates

        resp = self._client().post(f"/api/rerouting/offers/{self.offer.id}/decline")
        self.assertEqual(resp.status_code, 200)
        self.offer.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.offer.status, self.OfferStatus.DECLINED)
        self.assertEqual(self.order.state, OrderStates.RETURN_REQUESTED)

    def test_cannot_accept_another_buyers_offer(self):
        from core.models import User
        from rest_framework.test import APIClient

        other = User.objects.create_user("intruder", password="x")
        c = APIClient()
        c.force_authenticate(other)
        resp = c.post(f"/api/rerouting/offers/{self.offer.id}/accept")
        self.assertEqual(resp.status_code, 404)


# --------------------------------------------------------------------------- #
# End-to-end: grade -> reroute
# --------------------------------------------------------------------------- #
@override_settings(AI_MOCK=True)
class RerouteIntegrationTests(TestCase):
    def test_decide_route_produces_a_done_decision(self):
        from grading.models import (
            AssessmentContext,
            AssessmentStatus,
            GradingAssessment,
        )
        from .models import DecisionStatus, RouteChoices, RouteDecision
        from .tasks import decide_route

        _, _, _, unit, _, order = _order_graph()
        assessment = GradingAssessment.objects.create(
            unit=unit, order=order, context=AssessmentContext.RETURN,
            status=AssessmentStatus.DONE, quality_score=0.8, fraud_score=0.05,
            confidence=0.8, suggested_grade="B",
            vlm_result={"size_class": "small", "fragility": "rigid", "defects": []},
        )

        decide_route(assessment.id)

        decision = RouteDecision.objects.get(assessment=assessment)
        self.assertEqual(decision.status, DecisionStatus.DONE)
        self.assertIn(decision.route, RouteChoices.values)
        self.assertIn("routes", decision.costs)
        self.assertIn("ev", decision.costs)
        # EV fallback used (no LLM provider in mock mode).
        self.assertEqual(decision.decided_by, "ev")

    def test_ensure_recommendation_computes_inline_when_async_not_ready(self):
        """The timing gap: a unit is received before the async rerouting chain
        has produced a decision. ensure_recommendation_for must compute one
        inline from the latest DONE grading assessment so intake always shows a
        disposition."""
        from grading.models import (
            AssessmentContext,
            AssessmentStatus,
            GradingAssessment,
        )
        from .models import RouteChoices, RouteDecision
        from .services import ensure_recommendation_for, recommendation_for

        _, _, _, unit, _, order = _order_graph()
        GradingAssessment.objects.create(
            unit=unit, order=order, context=AssessmentContext.RETURN,
            status=AssessmentStatus.DONE, quality_score=0.8, fraud_score=0.05,
            confidence=0.8, suggested_grade="B",
            vlm_result={"size_class": "small", "fragility": "rigid", "defects": []},
        )

        # Precondition: the async chain has NOT produced a decision yet.
        self.assertIsNone(recommendation_for(unit))
        self.assertFalse(RouteDecision.objects.filter(unit=unit).exists())

        rec = ensure_recommendation_for(unit)

        # A disposition is now available and persisted.
        self.assertIsNotNone(rec)
        self.assertIn(rec["recommendation"], RouteChoices.values)
        self.assertEqual(rec["decided_by"], "ev")
        self.assertIn("alternatives", rec)
        self.assertTrue(RouteDecision.objects.filter(unit=unit).exists())

    def test_ensure_recommendation_reuses_existing_decision(self):
        """When a DONE decision already exists, ensure_recommendation_for must
        return it without creating a duplicate."""
        from grading.models import (
            AssessmentContext,
            AssessmentStatus,
            GradingAssessment,
        )
        from .models import RouteDecision
        from .services import ensure_recommendation_for
        from .tasks import decide_route

        _, _, _, unit, _, order = _order_graph()
        assessment = GradingAssessment.objects.create(
            unit=unit, order=order, context=AssessmentContext.RETURN,
            status=AssessmentStatus.DONE, quality_score=0.8, fraud_score=0.05,
            confidence=0.8, suggested_grade="B",
            vlm_result={"size_class": "small", "fragility": "rigid", "defects": []},
        )
        decide_route(assessment.id)
        self.assertEqual(RouteDecision.objects.filter(unit=unit).count(), 1)

        rec = ensure_recommendation_for(unit)

        self.assertIsNotNone(rec)
        # No duplicate decision was created.
        self.assertEqual(RouteDecision.objects.filter(unit=unit).count(), 1)

