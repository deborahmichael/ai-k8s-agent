from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.k8s_client import run_kubectl


class KubectlClientTests(unittest.TestCase):
    @patch("app.k8s_client.get_settings")
    @patch("app.k8s_client.subprocess.run")
    def test_timeout_returns_structured_error(self, mock_run: object, mock_get_settings: object) -> None:
        mock_get_settings.return_value = SimpleNamespace(
            openrouter_api_key=None,
            openrouter_model="nvidia/nemotron-3-ultra-550b-a55b:free",
            kubectl_timeout_seconds=7,
            log_tail_lines=100,
        )
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["kubectl", "get", "pods", "-n", "demo-apps"],
            timeout=7,
            output="partial output",
            stderr="context deadline exceeded",
        )

        result = run_kubectl(["get", "pods", "-n", "demo-apps"])

        self.assertEqual(result.command, ["kubectl", "get", "pods", "-n", "demo-apps"])
        self.assertEqual(result.returncode, 124)
        self.assertEqual(result.stdout, "partial output")
        self.assertIn("kubectl timed out after 7 seconds", result.stderr)
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args.kwargs["timeout"], 7)
        self.assertFalse(mock_run.call_args.kwargs["shell"] if "shell" in mock_run.call_args.kwargs else False)


if __name__ == "__main__":
    unittest.main()
