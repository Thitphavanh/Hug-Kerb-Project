import base64
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from PIL import Image

from .services import OpenRouterError, chat, chat_json
from .views import (
    AI_IMAGE_LIMIT,
    AI_IMAGE_MAX_SIZE,
    DEFAULT_VISION_MODEL,
    _assessment_entry_values,
    _encode_images,
)


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
