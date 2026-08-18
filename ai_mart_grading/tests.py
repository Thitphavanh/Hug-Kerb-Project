import base64
import json
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from PIL import Image

from asset_intake.models import Asset
from crm.models import Customer
from pos.models import Order, OrderItem, ServiceType

from .models import Assessment, ChecklistItem
from .services import OpenRouterError, chat, chat_json, to_decimal
from .views import (
    AI_IMAGE_LIMIT,
    AI_IMAGE_MAX_SIZE,
    BUYBACK_IMAGE_LIMIT,
    BUYBACK_IMAGE_MAX_SIZE,
    DEFAULT_VISION_MODEL,
    _assessment_entry_values,
    _encode_images,
)


class BuybackAssessmentGuardTests(TestCase):
    def test_buyback_assessment_requires_all_five_labeled_photos(self):
        user = get_user_model().objects.create_user("ai-buyback-staff")
        self.client.force_login(user)
        customer = Customer.objects.create(name="Seller", phone="02055551111")
        asset = Asset.objects.create(customer=customer, brand="Jordan")
        service = ServiceType.objects.create(
            name="Buy-back Evaluation",
            category=ServiceType.Category.BUYBACK,
            price=0,
        )
        order = Order.objects.create(customer=customer, created_by=user)
        OrderItem.objects.create(
            order=order,
            service_type=service,
            asset=asset,
            description="Buy-back",
            unit_price=0,
        )
        ChecklistItem.objects.create(name="Condition")

        response = self.client.post(
            reverse("ai_mart_grading:run_assessment", args=[asset.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("?ai=1#ai-photo-upload", response.url)
        self.assertFalse(Assessment.objects.exists())


class VisionImagePreparationTests(SimpleTestCase):
    @staticmethod
    def _media(width=2400, height=1600):
        source = BytesIO()
        Image.new("RGB", (width, height), "white").save(source, format="PNG")
        source.seek(0)
        file_field = Mock()
        file_field.open.return_value = source
        return SimpleNamespace(media_type="image", file=file_field)

    def test_images_are_resized_converted_and_limited_before_ai_request(self):
        encoded = _encode_images([self._media() for _ in range(5)])

        self.assertEqual(len(encoded), AI_IMAGE_LIMIT)
        data_url = encoded[0]["image_url"]["url"]
        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        image_bytes = base64.b64decode(data_url.split(",", 1)[1])
        with Image.open(BytesIO(image_bytes)) as result:
            self.assertEqual(result.format, "JPEG")
            self.assertLessEqual(result.width, AI_IMAGE_MAX_SIZE[0])
            self.assertLessEqual(result.height, AI_IMAGE_MAX_SIZE[1])

    def test_buyback_can_send_eight_compressed_angles(self):
        encoded = _encode_images(
            [self._media() for _ in range(10)],
            limit=BUYBACK_IMAGE_LIMIT,
            max_size=BUYBACK_IMAGE_MAX_SIZE,
        )

        self.assertEqual(len(encoded), 8)
        image_bytes = base64.b64decode(
            encoded[-1]["image_url"]["url"].split(",", 1)[1]
        )
        with Image.open(BytesIO(image_bytes)) as result:
            self.assertLessEqual(result.width, BUYBACK_IMAGE_MAX_SIZE[0])
            self.assertLessEqual(result.height, BUYBACK_IMAGE_MAX_SIZE[1])

    def test_compact_and_legacy_assessment_entries_are_supported(self):
        self.assertEqual(DEFAULT_VISION_MODEL, "google/gemini-2.5-flash-lite")
        self.assertEqual(
            _assessment_entry_values([7, 8, "ສະພາບດີ"]),
            (7, 8, "ສະພາບດີ"),
        )
        self.assertEqual(
            _assessment_entry_values(
                {"checklist_item_id": 7, "score": 8, "note": "ສະພາບດີ"}
            ),
            (7, 8, "ສະພາບດີ"),
        )


class OpenRouterClientTests(SimpleTestCase):
    def setUp(self):
        env_patcher = patch.dict(
            "os.environ",
            {
                "OPENROUTER_API_KEY": "test-key",
                "OPENROUTER_MODEL": "anthropic/claude-sonnet-5",
            },
        )
        env_patcher.start()
        self.addCleanup(env_patcher.stop)

    @patch("ai_mart_grading.services.requests.post")
    def test_chat_json_sends_bounded_tokens_and_json_mode(self, mock_post):
        response = Mock(status_code=200)
        response.json.return_value = {
            "model": "anthropic/claude-sonnet-5",
            "choices": [{"message": {"content": json.dumps({"ok": True})}}],
        }
        mock_post.return_value = response

        result, _ = chat_json([{"role": "user", "content": "test"}])

        payload = mock_post.call_args.kwargs["json"]
        self.assertTrue(result["ok"])
        self.assertEqual(payload["max_tokens"], 2000)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(
            payload["reasoning"],
            {"effort": "none", "exclude": True},
        )

    @patch("ai_mart_grading.services.requests.post")
    def test_max_tokens_is_capped_to_prevent_large_credit_reservation(self, mock_post):
        response = Mock(status_code=200)
        response.json.return_value = {
            "model": "test-model",
            "choices": [{"message": {"content": "ok"}}],
        }
        mock_post.return_value = response

        chat([{"role": "user", "content": "test"}], max_tokens=65536)

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["max_tokens"], 4096)

    @patch("ai_mart_grading.services.requests.post")
    def test_retired_claude_35_slug_is_mapped_to_sonnet_5(self, mock_post):
        response = Mock(status_code=200)
        response.json.return_value = {
            "model": "anthropic/claude-sonnet-5",
            "choices": [{"message": {"content": "ok"}}],
        }
        mock_post.return_value = response

        with patch.dict(
            "os.environ",
            {"OPENROUTER_MODEL": "anthropic/claude-3.5-sonnet"},
        ):
            chat([{"role": "user", "content": "test"}])

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "anthropic/claude-sonnet-5")

    @patch("ai_mart_grading.services.requests.post")
    def test_unknown_404_model_retries_once_with_default(self, mock_post):
        missing = Mock(status_code=404, text="No endpoints found")
        missing.json.return_value = {"error": {"message": "No endpoints found"}}
        success = Mock(status_code=200)
        success.json.return_value = {
            "model": "anthropic/claude-sonnet-5",
            "choices": [{"message": {"content": "ok"}}],
        }
        mock_post.side_effect = [missing, success]

        chat(
            [{"role": "user", "content": "test"}],
            model="provider/removed-model",
        )

        self.assertEqual(mock_post.call_count, 2)
        retry_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(retry_payload["model"], "anthropic/claude-sonnet-5")

    @patch("ai_mart_grading.services.requests.post")
    def test_openrouter_error_uses_concise_provider_message(self, mock_post):
        response = Mock(status_code=402, text="full provider response")
        response.json.return_value = {
            "error": {
                "message": (
                    "This request requires more credits. To increase, visit "
                    "https://openrouter.ai/workspaces/default/keys/internal-id"
                )
            }
        }
        mock_post.return_value = response

        with self.assertRaisesRegex(OpenRouterError, "requires more credits") as error:
            chat([{"role": "user", "content": "test"}])
        self.assertNotIn("internal-id", str(error.exception))

    @patch("ai_mart_grading.services.requests.post")
    def test_null_content_becomes_handled_openrouter_error(self, mock_post):
        response = Mock(status_code=200)
        response.json.return_value = {
            "model": "anthropic/claude-sonnet-5",
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": None},
                }
            ],
        }
        mock_post.return_value = response

        with self.assertRaisesRegex(OpenRouterError, "finish_reason=length"):
            chat_json([{"role": "user", "content": "test"}])

    @patch("ai_mart_grading.services.requests.post")
    def test_credit_limit_retries_once_with_affordable_token_cap(self, mock_post):
        insufficient_credit = Mock(status_code=402, text="credit error")
        insufficient_credit.json.return_value = {
            "error": {
                "message": (
                    "This request requires more credits, or fewer max_tokens. "
                    "You requested up to 3000 tokens, but can only afford 1942."
                )
            }
        }
        success = Mock(status_code=200)
        success.json.return_value = {
            "model": "anthropic/claude-sonnet-5",
            "choices": [{"message": {"content": "ok"}}],
        }
        mock_post.side_effect = [insufficient_credit, success]

        content, _ = chat(
            [{"role": "user", "content": "test"}],
            max_tokens=3000,
        )

        self.assertEqual(content, "ok")
        self.assertEqual(mock_post.call_count, 2)
        retry_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(retry_payload["max_tokens"], 1878)


class AssessmentResultStorageTests(TestCase):
    """ຄຳຕອບຂອງ AI ບໍ່ຢູ່ໃນຮູບແບບທີ່ຄາດໄວ້ສະເໝີ — ຕ້ອງບໍ່ເສຍທັງການປະເມີນ"""

    def setUp(self):
        user = get_user_model().objects.create_user("grading-staff")
        self.client.force_login(user)
        customer = Customer.objects.create(name="ນາງ ຄຳ", phone="02055553333")
        self.asset = Asset.objects.create(customer=customer, brand="Nike")
        self.item = ChecklistItem.objects.create(name="ໜ້າເກີບ", max_score=10)
        self.url = reverse("ai_mart_grading:run_assessment", args=[self.asset.pk])

    @patch("ai_mart_grading.views.chat_json")
    def test_confidence_score_is_stored_as_a_column(self, mock_chat):
        mock_chat.return_value = (
            {
                "items": [[self.item.id, 8, "ດີ"]],
                "overall_grade": "B",
                "total_score": 8,
                "summary": "ສະພາບດີ",
                "confidence_score": 92,
            },
            {"model": "test-model"},
        )

        self.client.post(self.url)

        assessment = Assessment.objects.get()
        self.assertEqual(assessment.status, Assessment.Status.DONE)
        self.assertEqual(assessment.confidence_score, 92)

    @patch("ai_mart_grading.views.chat_json")
    def test_an_overlong_grade_is_narrowed_instead_of_breaking_the_save(
        self, mock_chat
    ):
        """overall_grade ຍາວໄດ້ 1 ຕົວ — "A+" ເຄີຍເຮັດໃຫ້ການບັນທຶກລົ້ມທັງໜ່ວຍ"""
        mock_chat.return_value = (
            {
                "items": [[self.item.id, "9.5", "ດີຫຼາຍ"]],
                "overall_grade": "A+",
                "total_score": "9.5",
                "summary": "ເກືອບໃໝ່",
            },
            {"model": "test-model"},
        )

        self.client.post(self.url)

        assessment = Assessment.objects.get()
        self.assertEqual(assessment.status, Assessment.Status.DONE)
        self.assertEqual(assessment.overall_grade, "A")
        self.assertEqual(assessment.total_score, Decimal("9.5"))
        self.assertEqual(assessment.items.get().score, Decimal("9.5"))

    @patch("ai_mart_grading.views.chat_json")
    def test_a_grade_that_is_not_a_letter_at_all_is_left_blank(self, mock_chat):
        mock_chat.return_value = (
            {
                "items": [[self.item.id, 5, ""]],
                "overall_grade": "Grade B",
                "total_score": 5,
            },
            {"model": "test-model"},
        )

        self.client.post(self.url)

        self.assertEqual(Assessment.objects.get().overall_grade, "")

    @patch("ai_mart_grading.views.chat_json")
    def test_an_unparsable_item_score_counts_as_zero(self, mock_chat):
        mock_chat.return_value = (
            {
                "items": [[self.item.id, "N/A", "ເບິ່ງບໍ່ຊັດ"]],
                "overall_grade": "F",
                "total_score": None,
            },
            {"model": "test-model"},
        )

        self.client.post(self.url)

        assessment = Assessment.objects.get()
        self.assertEqual(assessment.items.get().score, Decimal("0"))
        self.assertIsNone(assessment.total_score)


class ToDecimalTests(SimpleTestCase):
    def test_it_handles_the_shapes_ai_actually_returns(self):
        self.assertEqual(to_decimal("1,200,000"), Decimal("1200000"))
        self.assertEqual(to_decimal("85%"), Decimal("85"))
        self.assertEqual(to_decimal(12.5), Decimal("12.5"))
        self.assertIsNone(to_decimal("N/A"))
        self.assertIsNone(to_decimal(None))
        self.assertIsNone(to_decimal(""))
        self.assertIsNone(to_decimal(True))
        self.assertIsNone(to_decimal(float("nan")))
        self.assertEqual(to_decimal("nope", 0), 0)
