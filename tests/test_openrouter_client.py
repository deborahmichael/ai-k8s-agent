from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

from app.openrouter_client import analyze_with_openrouter


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", payload: object | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        if self._payload is None:
            raise ValueError("no json payload")
        return self._payload


class OpenRouterClientTests(unittest.TestCase):
    @patch("app.openrouter_client.get_settings")
    @patch("app.openrouter_client.requests.post")
    def test_uses_safety_system_prompt(self, mock_post: object, mock_get_settings: object) -> None:
        mock_get_settings.return_value = SimpleNamespace(
            openrouter_api_key="test-key",
            openrouter_model="nvidia/nemotron-3-ultra-550b-a55b:free",
            kubectl_timeout_seconds=15,
            log_tail_lines=100,
        )
        mock_post.return_value = FakeResponse(200, payload={"choices": [{"message": {"content": "ok"}}]})

        result = analyze_with_openrouter("prompt")

        self.assertEqual(result["enabled"], True)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertIn("read-only Kubernetes incident assistant", payload["messages"][0]["content"])
        self.assertIn("Do not apply automatically", payload["messages"][0]["content"])
        self.assertIn("Commands a human operator can run", payload["messages"][0]["content"])
        self.assertEqual(payload["messages"][1]["role"], "user")
        self.assertEqual(result["content"], "ok")

    @patch("app.openrouter_client.get_settings")
    @patch("app.openrouter_client.requests.post")
    def test_returns_error_for_401(self, mock_post: object, mock_get_settings: object) -> None:
        mock_get_settings.return_value = SimpleNamespace(
            openrouter_api_key="test-key",
            openrouter_model="nvidia/nemotron-3-ultra-550b-a55b:free",
            kubectl_timeout_seconds=15,
            log_tail_lines=100,
        )
        mock_post.return_value = FakeResponse(
            401,
            '{"error":{"message":"invalid api key"}}',
            {"error": {"message": "invalid api key"}},
        )

        result = analyze_with_openrouter("prompt")

        self.assertEqual(result["enabled"], False)
        self.assertEqual(result["error"], "OpenRouter returned 401: unauthorized")

    @patch("app.openrouter_client.get_settings")
    @patch("app.openrouter_client.requests.post")
    def test_returns_error_for_429(self, mock_post: object, mock_get_settings: object) -> None:
        mock_get_settings.return_value = SimpleNamespace(
            openrouter_api_key="test-key",
            openrouter_model="nvidia/nemotron-3-ultra-550b-a55b:free",
            kubectl_timeout_seconds=15,
            log_tail_lines=100,
        )
        mock_post.return_value = FakeResponse(
            429,
            '{"error":{"message":"model temporarily rate-limited"}}',
            {"error": {"message": "model temporarily rate-limited"}},
        )

        result = analyze_with_openrouter("prompt")

        self.assertEqual(result["enabled"], False)
        self.assertEqual(result["error"], "OpenRouter returned 429: model temporarily rate-limited")

    @patch("app.openrouter_client.get_settings")
    @patch("app.openrouter_client.requests.post")
    def test_returns_error_for_request_exception(self, mock_post: object, mock_get_settings: object) -> None:
        mock_get_settings.return_value = SimpleNamespace(
            openrouter_api_key="test-key",
            openrouter_model="nvidia/nemotron-3-ultra-550b-a55b:free",
            kubectl_timeout_seconds=15,
            log_tail_lines=100,
        )
        mock_post.side_effect = requests.RequestException("network down")

        result = analyze_with_openrouter("prompt")

        self.assertEqual(result["enabled"], False)
        self.assertIn("OpenRouter request failed:", result["error"])

    @patch("app.openrouter_client.get_settings")
    @patch("app.openrouter_client.requests.post")
    def test_disabled_when_no_key_is_set(self, mock_post: object, mock_get_settings: object) -> None:
        mock_get_settings.return_value = SimpleNamespace(
            openrouter_api_key=None,
            openrouter_model="nvidia/nemotron-3-ultra-550b-a55b:free",
            kubectl_timeout_seconds=15,
            log_tail_lines=100,
        )

        result = analyze_with_openrouter("prompt")

        self.assertEqual(result["enabled"], False)
        self.assertEqual(result["error"], "OPENROUTER_API_KEY is not set")
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
