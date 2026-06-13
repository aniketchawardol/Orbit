"""Tests for the return grading pipeline.

Split into fast, hermetic unit tests for the pure logic (scoring, metadata,
perceptual hash, prompts, mock VLM, provider registry) and DB-backed integration
tests for the return-flow wiring and the end-to-end orchestrator.

Run with the mock VLM so nothing hits the network:
    CELERY_TASK_ALWAYS_EAGER=1 GRADING_VLM_PROVIDER=mock \
        python manage.py test grading
"""

import io
import json

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from .metadata import analyze_image, server_metadata_from_bytes, summarize
from .prompts import build_vlm_messages, normalize_vlm_output
from .providers import base, registry
from .providers.mock import MockVLM
from .providers.phash import PHashEmbedding, _dhash, _similarity, phash_bytes
from .scoring import blend

_LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


# --------------------------------------------------------------------------- #
# Image helpers
# --------------------------------------------------------------------------- #
def _solid(color=(120, 120, 120), size=(64, 64), fmt="JPEG"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def _gradient(horizontal=True, size=(64, 64), fmt="PNG", reverse=False):
    im = Image.new("L", size)
    px = im.load()
    w, h = size
    for y in range(h):
        for x in range(w):
            val = (x * 255 // w) if horizontal else (y * 255 // h)
            px[x, y] = (255 - val) if reverse else val
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format=fmt)
    return buf.getvalue()


def _vlm(**over):
    base_data = {
        "item_matches_reference": True,
        "quality_estimate": 0.9,
        "suggested_grade": "A",
        "confidence": 0.8,
        "fraud_flags": [],
        "defects": [],
        "source": "gemini",
    }
    base_data.update(over)
    return normalize_vlm_output(base_data)


# --------------------------------------------------------------------------- #
# Scoring — the multi-source blend
# --------------------------------------------------------------------------- #
class ScoringTests(SimpleTestCase):
    def test_clean_return_is_low_fraud(self):
        out = blend(
            _vlm(),
            {"overall": 0.9, "duplicate_pairs": []},
            {"metadata_fraud_signal": 0.0, "flags": []},
            {"history_fraud_signal": 0.0, "flags": []},
            {"reason": "CHANGED_MIND"},
        )
        self.assertLess(out["fraud_score"], 0.2)
        self.assertEqual(out["quality_score"], 0.9)
        self.assertIn(out["suggested_grade"], ("A", "B"))
        self.assertGreater(out["confidence"], 0.5)

    def test_multiple_signals_drive_fraud_up(self):
        out = blend(
            _vlm(
                item_matches_reference=False,
                fraud_flags=["wrong_item"],
                quality_estimate=0.9,
                suggested_grade="A",
            ),
            {"overall": 0.1, "duplicate_pairs": [["a", "b"]]},
            {"metadata_fraud_signal": 0.7, "flags": ["software_edited"]},
            {"history_fraud_signal": 0.6, "flags": ["high_return_rate"]},
            {"reason": "DEFECTIVE"},  # claims defective but VLM sees pristine
        )
        self.assertGreater(out["fraud_score"], 0.5)
        flags = out["scores"]["fraud_flags"]
        self.assertIn("wrong_item", flags)
        self.assertIn("software_edited", flags)
        self.assertIn("low_image_similarity", flags)
        self.assertIn("reason_mismatch", flags)

    def test_missing_similarity_renormalizes(self):
        out = blend(_vlm(), {}, {}, {}, {"reason": "OTHER"})
        # No 'overall' similarity -> that signal is excluded, others still score.
        self.assertLess(out["scores"]["confidence"]["availability"], 1.0)
        self.assertIsInstance(out["fraud_score"], float)

    def test_grade_is_conservative(self):
        # VLM says A but quality (0.5) implies C -> take the worse (C).
        out = blend(
            _vlm(suggested_grade="A", quality_estimate=0.5),
            {"overall": 0.9},
            {},
            {},
            {"reason": "OTHER"},
        )
        self.assertEqual(out["suggested_grade"], "C")


# --------------------------------------------------------------------------- #
# Metadata anomaly detection
# --------------------------------------------------------------------------- #
class MetadataTests(SimpleTestCase):
    def test_editor_software_flagged(self):
        res = analyze_image({"Software": "Adobe Photoshop 24.0"}, {})
        self.assertIn("software_edited", res["flags"])

    def test_png_without_camera_looks_like_screenshot(self):
        res = analyze_image({"type": "image/png"}, {"format": "PNG"})
        self.assertIn("no_camera_exif", res["flags"])
        self.assertIn("is_screenshot", res["flags"])
        self.assertIn("no_capture_time", res["flags"])

    def test_stale_capture_predating_delivery(self):
        now = timezone.now()
        old = (now - timezone.timedelta(days=10)).strftime("%Y:%m:%d %H:%M:%S")
        res = analyze_image(
            {"Make": "Apple", "Model": "iPhone", "DateTimeOriginal": old},
            {},
            reference_time=now,
        )
        self.assertIn("stale_capture", res["flags"])

    def test_dimension_mismatch(self):
        recent = timezone.now().strftime("%Y:%m:%d %H:%M:%S")
        res = analyze_image(
            {
                "Make": "Apple",
                "Model": "iPhone",
                "DateTimeOriginal": recent,
                "originalWidth": 100,
                "originalHeight": 100,
            },
            {"width": 400, "height": 400},
        )
        self.assertIn("dimension_mismatch", res["flags"])

    def test_summarize_blends_weights(self):
        out = summarize(
            [
                {"flags": ["software_edited"], "weight": 0.4},
                {"flags": [], "weight": 0.0},
            ]
        )
        self.assertGreater(out["metadata_fraud_signal"], 0.0)
        self.assertIn("software_edited", out["flags"])

    def test_server_metadata_from_bytes(self):
        out = server_metadata_from_bytes(_solid(size=(120, 90)))
        self.assertEqual((out["width"], out["height"]), (120, 90))
        self.assertEqual(out["format"], "JPEG")


# --------------------------------------------------------------------------- #
# Perceptual hash similarity
# --------------------------------------------------------------------------- #
class PHashTests(SimpleTestCase):
    def test_identical_images_match(self):
        h = _dhash(_gradient(horizontal=True))
        self.assertEqual(_similarity(h, h), 1.0)

    def test_different_content_lowers_similarity(self):
        # dHash encodes horizontal adjacent differences: a left->right gradient
        # and its right->left reverse hash to opposite bits, so similarity is low.
        hh = _dhash(_gradient(horizontal=True))
        hr = _dhash(_gradient(horizontal=True, reverse=True))
        self.assertLess(_similarity(hh, hr), 0.9)

    def test_phash_bytes_is_hex(self):
        h = phash_bytes(_gradient())
        self.assertEqual(len(h), 16)
        int(h, 16)  # must parse as hex

    @override_settings(CACHES=_LOCMEM)
    def test_compare_overall_and_duplicates(self):
        g = _gradient(horizontal=True)
        up = [
            base.GradingImageData(path="u1", data=g),
            base.GradingImageData(path="u2", data=g),  # reused -> duplicate
        ]
        ref = [base.GradingImageData(path="r1", data=g, role="REFERENCE")]
        out = PHashEmbedding().compare(up, ref)
        self.assertGreater(out["overall"], 0.95)
        self.assertTrue(out["duplicate_pairs"])


# --------------------------------------------------------------------------- #
# Prompt building + output normalization
# --------------------------------------------------------------------------- #
class PromptTests(SimpleTestCase):
    def test_normalize_tolerates_garbage(self):
        out = normalize_vlm_output(
            {
                "suggested_grade": "amazing",
                "quality_estimate": 2.0,
                "per_image": "not-a-list",
                "fraud_flags": None,
            }
        )
        self.assertEqual(out["suggested_grade"], "B")
        self.assertEqual(out["quality_estimate"], 1.0)
        self.assertEqual(out["per_image"], [])
        self.assertEqual(out["fraud_flags"], [])

    def test_build_messages_has_image_parts(self):
        req = base.VLMRequest(
            product={"title": "Phone", "category": "electronics"},
            claim={"reason": "DEFECTIVE"},
            uploaded=[base.GradingImageData(path="u", data=_solid())],
            reference=[base.GradingImageData(path="r", data=_solid(), role="REFERENCE")],
        )
        msgs = build_vlm_messages(req)
        self.assertEqual(msgs[0]["role"], "system")
        image_parts = [p for p in msgs[1]["content"] if p.get("type") == "image_url"]
        self.assertEqual(len(image_parts), 2)


# --------------------------------------------------------------------------- #
# Mock VLM + provider registry
# --------------------------------------------------------------------------- #
class MockAndRegistryTests(SimpleTestCase):
    def _req(self, **claim):
        return base.VLMRequest(
            product={"title": "X", "category": "electronics", "id": 1},
            claim=claim,
            uploaded=[base.GradingImageData(path="u", data=_solid())],
        )

    def test_untouched_grades_a(self):
        out = MockVLM().grade(self._req(claimed_untouched=True))
        self.assertEqual(out["suggested_grade"], "A")
        self.assertEqual(out["defects"], [])
        self.assertEqual(out["source"], "mock")

    def test_defective_is_worse(self):
        out = MockVLM().grade(self._req(reason="DEFECTIVE"))
        self.assertIn(out["suggested_grade"], ("C", "D"))
        self.assertLess(out["quality_estimate"], 0.5)

    @override_settings(GRADING_VLM_PROVIDER="mock")
    def test_registry_mock(self):
        self.assertIsInstance(registry.get_vlm_provider(), MockVLM)

    @override_settings(
        GRADING_VLM_PROVIDER="auto",
        LLM_PROVIDERS={
            "gemini": {"base_url": "https://x/", "api_key": "", "model": "m"}
        },
    )
    def test_registry_auto_without_key_falls_back_to_mock(self):
        self.assertIsInstance(registry.get_vlm_provider(), MockVLM)

    def test_registry_embedding_default_is_phash(self):
        self.assertIsInstance(registry.get_embedding_provider(), PHashEmbedding)


# --------------------------------------------------------------------------- #
# Integration: return flow + orchestrator (DB-backed)
# --------------------------------------------------------------------------- #
@override_settings(GRADING_VLM_PROVIDER="mock", CACHES=_LOCMEM)
class ReturnFlowTests(TestCase):
    def setUp(self):
        from catalog.models import ItemUnit, Product, UnitStates
        from core.models import User
        from marketplace.models import Listing, ListingSources, Order, OrderStates

        self.OrderStates = OrderStates
        self.buyer = User.objects.create_user("buyer", password="x")
        self.seller = User.objects.create_user("seller", password="x")
        self.product = Product.objects.create(
            title="Wireless Earbuds",
            category="electronics",
            mrp=4999,
            seller=self.seller,
            attributes={"brand": "Acme", "color": "black"},
        )
        self.unit = ItemUnit.objects.create(
            product=self.product, owner=self.buyer, state=UnitStates.SOLD
        )
        self.ref_path = default_storage.save(
            "listings/ref.png", ContentFile(_gradient(horizontal=True))
        )
        self.listing = Listing.objects.create(
            unit=self.unit,
            source=ListingSources.NEW,
            price=4999,
            photos=[self.ref_path],
            lister=self.seller,
        )
        self.order = Order.objects.create(
            buyer=self.buyer,
            listing=self.listing,
            state=OrderStates.DELIVERED,
            delivered_at=timezone.now(),
        )

    def _client(self):
        from rest_framework.test import APIClient

        c = APIClient()
        c.force_authenticate(self.buyer)
        return c

    def test_request_return_creates_and_runs_assessment(self):
        from grading.models import AssessmentContext, AssessmentStatus, GradingAssessment

        meta = [
            {
                "Make": "Apple",
                "Model": "iPhone",
                "DateTimeOriginal": timezone.now().strftime("%Y:%m:%d %H:%M:%S"),
                "originalWidth": 640,
                "originalHeight": 640,
            }
        ]
        resp = self._client().post(
            f"/api/orders/{self.order.id}/return",
            {
                "reason": "DEFECTIVE",
                "claimed_untouched": "false",
                "comment": "stopped charging",
                "photos": [
                    SimpleUploadedFile("p.jpg", _solid(), content_type="image/jpeg")
                ],
                "metadata": json.dumps(meta),
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        self.order.refresh_from_db()
        self.assertEqual(self.order.state, self.OrderStates.RETURN_REQUESTED)
        self.assertEqual(self.order.return_comment, "stopped charging")

        a = GradingAssessment.objects.get(unit=self.unit)
        self.assertEqual(a.context, AssessmentContext.RETURN)
        # Eager execution (CELERY_TASK_ALWAYS_EAGER=1) completes it inline.
        if a.status == AssessmentStatus.DONE:
            self.assertIsNotNone(a.fraud_score)
            self.assertIsNotNone(a.quality_score)
            self.assertIn(a.suggested_grade, ("A", "B", "C", "D"))
            self.assertIn("fraud", a.scores)
        # Buyer-uploaded image is recorded with its pre-compression metadata.
        uploaded = a.images.filter(role="UPLOADED")
        self.assertEqual(uploaded.count(), 1)
        self.assertEqual(uploaded.first().client_metadata.get("Make"), "Apple")
        # Reference image(s) captured for similarity comparison.
        self.assertTrue(a.images.filter(role="REFERENCE").exists())

    def test_window_expired_offers_resell(self):
        self.order.delivered_at = timezone.now() - timezone.timedelta(days=60)
        self.order.save(update_fields=["delivered_at"])
        resp = self._client().post(
            f"/api/orders/{self.order.id}/return",
            {"reason": "CHANGED_MIND", "claimed_untouched": "false"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 409)
        self.assertTrue(resp.json().get("resell_available"))

    def test_orchestrator_runs_all_sources(self):
        """Deterministic end-to-end without Celery: build then run inline."""
        from grading.models import AssessmentStatus
        from grading.orchestrator import run_all_sync
        from grading.services import create_return_assessment

        up_path = default_storage.save("returns/up.jpg", ContentFile(_solid()))
        self.order.return_reason = "DEFECTIVE"
        self.order.photos = [up_path]
        self.order.save(update_fields=["return_reason", "photos"])

        assessment = create_return_assessment(
            self.order, [up_path], client_metadatas=[{"Make": "Apple"}]
        )
        run_all_sync(assessment.id)

        assessment.refresh_from_db()
        self.assertEqual(assessment.status, AssessmentStatus.DONE)
        self.assertIsNotNone(assessment.fraud_score)
        self.assertIsNotNone(assessment.quality_score)
        self.assertIsNotNone(assessment.confidence)
        self.assertIn(assessment.suggested_grade, ("A", "B", "C", "D"))
        for key in ("fraud", "quality", "confidence", "grade"):
            self.assertIn(key, assessment.scores)
