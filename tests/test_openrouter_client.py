from __future__ import annotations

import unittest
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
    @patch("app.openrouter_client.get_openrouter_api_key", return_value="test-key")
    @patch("app.openrouter_client.requests.post")
    def test_includes_safety_system_prompt(self, mock_post: object, mock_api_key: object) -> None:
        mock_post.return_value = FakeResponse(
            200,
            payload={"choices": [{"message": {"content": "ok"}}]},
        )

        analyze_with_openrouter("prompt")

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertIn("read-only Kubernetes incident assistant", payload["messages"][0]["content"])
        self.assertIn("Only recommend commands for a human operator", payload["messages"][0]["content"])
        self.assertEqual(payload["messages"][1]["role"], "user")

    @patch("app.openrouter_client.get_openrouter_api_key", return_value="test-key")
    @patch("app.openrouter_client.requests.post")
    def test_returns_error_for_rate_limit(self, mock_post: object, mock_api_key: object) -> None:
        mock_post.return_value = FakeResponse(
            429,
            '{"error":{"message":"model temporarily rate-limited"}}',
            {"error": {"message": "model temporarily rate-limited"}},
        )

        result = analyze_with_openrouter("prompt")

        self.assertEqual(result["enabled"], False)
        self.assertEqual(result["model"], "openai/gpt-oss-120b:free")
        self.assertEqual(result["error"], "OpenRouter returned 429: model temporarily rate-limited")

    @patch("app.openrouter_client.get_openrouter_api_key", return_value="test-key")
    @patch("app.openrouter_client.requests.post", side_effect=requests.RequestException("network down"))
    def test_returns_error_for_request_exception(self, mock_post: object, mock_api_key: object) -> None:
        result = analyze_with_openrouter("prompt")

        self.assertEqual(result["enabled"], False)
        self.assertEqual(result["model"], "openai/gpt-oss-120b:free")
        self.assertIn("OpenRouter request failed:", result["error"])


if __name__ == "__main__":
    unittest.main()
