import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .services import OpenRouterError, chat, chat_json


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
            "error": {"message": "This request requires more credits."}
        }
        mock_post.return_value = response

        with self.assertRaisesRegex(OpenRouterError, "requires more credits"):
            chat([{"role": "user", "content": "test"}])
