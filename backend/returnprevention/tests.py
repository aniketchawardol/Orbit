"""Tests for return prevention: apparel fit guide + accessory compatibility.

The LLM is forced off (``RETURNPREV_LLM_PROVIDER="mock"``) so the deterministic
rules engine runs — no network, fully reproducible.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from unittest.mock import patch

from catalog.models import ItemUnit, Product, UnitStates
from marketplace.models import (
    Listing,
    ListingSources,
    ListingStates,
    Order,
    OrderStates,
)

from . import rules, services
from .tasks import precompute_for_user

User = get_user_model()


@override_settings(RETURNPREV_LLM_PROVIDER="mock")
class ReturnPreventionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.seller = User.objects.create_user("seller_rp", password="x")
        self.buyer = User.objects.create_user(
            "buyer_rp",
            password="x",
            profile={"sizes": {"waist": "32", "top": "M", "shoe_uk": "9"}},
        )

    # --- fixtures ---
    def make_product(self, title, category="electronics", **attrs):
        return Product.objects.create(
            title=title,
            category=category,
            mrp=1000,
            seller=self.seller,
            attributes=attrs,
        )

    def make_listing(self, product, owner=None, state=ListingStates.ACTIVE):
        unit = ItemUnit.objects.create(
            product=product, state=UnitStates.NEW, owner=owner
        )
        return Listing.objects.create(
            unit=unit, source=ListingSources.NEW, price=product.mrp, state=state
        )

    def give_owned(self, product):
        """Make the buyer own ``product`` via a delivered order."""
        listing = self.make_listing(
            product, owner=self.buyer, state=ListingStates.SOLD
        )
        Order.objects.create(
            buyer=self.buyer, listing=listing, state=OrderStates.DELIVERED
        )

    # --- deterministic compatibility rules (pure) ---
    def test_rules_same_family_other_variant_incompatible(self):
        owned = [{"model": "iPhone 15", "title": "x", "category": "y"}]
        v = rules.check_compat("iPhone 14", owned)
        self.assertFalse(v["compatible"])
        self.assertTrue(v["warning"])

    def test_rules_same_model_compatible(self):
        owned = [{"model": "iPhone 15", "title": "x", "category": "y"}]
        v = rules.check_compat("iPhone 15", owned)
        self.assertTrue(v["compatible"])
        self.assertEqual(v["warning"], "")

    def test_rules_other_family_silent(self):
        owned = [{"model": "iPhone 15", "title": "x", "category": "y"}]
        self.assertTrue(rules.check_compat("Galaxy S23", owned)["compatible"])

    def test_rules_no_owned_silent(self):
        self.assertTrue(rules.check_compat("iPhone 14", [])["compatible"])

    # --- apparel/footwear fit guide ---
    def test_fit_guide_unsized(self):
        p = self.make_product("Plain Tee")
        self.assertEqual(services.fit_guide(self.buyer, p), {"sized": False})

    def test_fit_guide_exact_match(self):
        p = self.make_product(
            "Jeans", "apparel", size_type="waist", size_options=["28", "30", "32", "34"]
        )
        g = services.fit_guide(self.buyer, p)
        self.assertTrue(g["sized"])
        self.assertEqual(g["recommended_size"], "32")
        self.assertIn("32", g["message"])

    def test_fit_guide_closest_match(self):
        p = self.make_product(
            "Jeans", "apparel", size_type="waist", size_options=["28", "30", "34", "36"]
        )
        g = services.fit_guide(self.buyer, p)
        self.assertIn(g["recommended_size"], {"30", "34"})

    def test_fit_guide_no_profile(self):
        nuser = User.objects.create_user("nop_rp", password="x")
        p = self.make_product(
            "Jeans", "apparel", size_type="waist", size_options=["28", "30", "32"]
        )
        g = services.fit_guide(nuser, p)
        self.assertTrue(g["sized"])
        self.assertIsNone(g["recommended_size"])
        self.assertIsNone(g["message"])

    # --- accessory compatibility (DB + cache) ---
    def test_compat_non_accessory_short_circuits(self):
        p = self.make_product("Apple iPhone 15", model="iPhone 15")
        v = services.get_compat(self.buyer, p)
        self.assertFalse(v["checked"])
        self.assertTrue(v["compatible"])

    def test_compat_incompatible_when_owns_other_variant(self):
        self.give_owned(self.make_product("Apple iPhone 15", model="iPhone 15"))
        case = self.make_product(
            "iPhone 14 Case", "accessories", compatible_model="iPhone 14"
        )
        v = services.get_compat(self.buyer, case)
        self.assertTrue(v["checked"])
        self.assertFalse(v["compatible"])
        self.assertTrue(v["warning"])

    def test_compat_compatible_same_model(self):
        self.give_owned(self.make_product("Apple iPhone 15", model="iPhone 15"))
        case = self.make_product(
            "iPhone 15 Case", "accessories", compatible_model="iPhone 15"
        )
        v = services.get_compat(self.buyer, case)
        self.assertTrue(v["compatible"])
        self.assertEqual(v["warning"], "")

    def test_compat_silent_for_unowned_family(self):
        self.give_owned(self.make_product("Apple iPhone 15", model="iPhone 15"))
        case = self.make_product(
            "Galaxy S23 Case", "accessories", compatible_model="Galaxy S23"
        )
        self.assertTrue(services.get_compat(self.buyer, case)["compatible"])

    def test_compat_caches_verdict(self):
        self.give_owned(self.make_product("Apple iPhone 15", model="iPhone 15"))
        case = self.make_product(
            "iPhone 14 Case", "accessories", compatible_model="iPhone 14"
        )
        services.get_compat(self.buyer, case)
        cached = cache.get(services._compat_key(self.buyer.id, case.id))
        self.assertIsNotNone(cached)
        self.assertFalse(cached["compatible"])

    def test_guard_suppresses_cross_family_false_positive(self):
        """A cross-family LLM false positive (owns iPhone, buys Galaxy case) is
        overridden to compatible — the shopper owns no same-line device."""
        self.give_owned(self.make_product("Apple iPhone 15", model="iPhone 15"))
        case = self.make_product(
            "Galaxy S23 Case", "accessories", compatible_model="Galaxy S23"
        )
        with patch(
            "returnprevention.llm.check_compat",
            return_value={"compatible": False, "warning": "bogus"},
        ):
            v = services.get_compat(self.buyer, case)
        self.assertTrue(v["compatible"])
        self.assertEqual(v["warning"], "")

    def test_guard_keeps_genuine_same_family_warning(self):
        """A genuine same-line conflict from the LLM is preserved by the guard."""
        self.give_owned(self.make_product("Apple iPhone 15", model="iPhone 15"))
        case = self.make_product(
            "iPhone 14 Case", "accessories", compatible_model="iPhone 14"
        )
        with patch(
            "returnprevention.llm.check_compat",
            return_value={
                "compatible": False,
                "warning": "You own an iPhone 15 — this case fits an iPhone 14.",
            },
        ):
            v = services.get_compat(self.buyer, case)
        self.assertFalse(v["compatible"])
        self.assertTrue(v["warning"])

    # --- combined pre-purchase gate ---
    def test_gate_size_required(self):
        p = self.make_product(
            "Jeans", "apparel", size_type="waist", size_options=["28", "30", "32"]
        )
        out = services.purchase_warnings(self.buyer, p, "")
        self.assertTrue(out["size_required"])

    def test_gate_wrong_size_warns(self):
        p = self.make_product(
            "Jeans", "apparel", size_type="waist", size_options=["28", "30", "32", "34"]
        )
        out = services.purchase_warnings(self.buyer, p, "34")
        self.assertIn("size", [w["kind"] for w in out["warnings"]])

    def test_gate_right_size_no_warning(self):
        p = self.make_product(
            "Jeans", "apparel", size_type="waist", size_options=["28", "30", "32", "34"]
        )
        out = services.purchase_warnings(self.buyer, p, "32")
        self.assertFalse(out["size_required"])
        self.assertEqual(out["warnings"], [])

    def test_gate_incompatible_accessory_warns(self):
        self.give_owned(self.make_product("Apple iPhone 15", model="iPhone 15"))
        case = self.make_product(
            "iPhone 14 Case", "accessories", compatible_model="iPhone 14"
        )
        out = services.purchase_warnings(self.buyer, case, "")
        self.assertIn("compat", [w["kind"] for w in out["warnings"]])

    def test_gate_compatible_accessory_no_warning(self):
        self.give_owned(self.make_product("Apple iPhone 15", model="iPhone 15"))
        case = self.make_product(
            "iPhone 15 Case", "accessories", compatible_model="iPhone 15"
        )
        out = services.purchase_warnings(self.buyer, case, "")
        self.assertEqual(out["warnings"], [])

    # --- login precompute warms the cache (eager) ---
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, RETURNPREV_LLM_PROVIDER="mock")
    def test_precompute_warms_cache(self):
        self.give_owned(self.make_product("Apple iPhone 15", model="iPhone 15"))
        case = self.make_product(
            "iPhone 14 Case", "accessories", compatible_model="iPhone 14"
        )
        self.make_listing(case, state=ListingStates.ACTIVE)
        precompute_for_user(self.buyer.id)
        cached = cache.get(services._compat_key(self.buyer.id, case.id))
        self.assertIsNotNone(cached)
        self.assertFalse(cached["compatible"])
