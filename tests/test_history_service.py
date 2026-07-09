from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.history_service import get_history_item, list_history, save_investigation


class HistoryServiceTests(unittest.TestCase):
    def _disabled_settings(self) -> SimpleNamespace:
        return SimpleNamespace(
            openrouter_api_key=None,
            openrouter_model="nvidia/nemotron-3-ultra-550b-a55b:free",
            kubectl_timeout_seconds=15,
            log_tail_lines=100,
            cors_origins=("http://localhost:5173",),
            insforge_enabled=False,
            insforge_api_url=None,
            insforge_api_key=None,
            insforge_history_table="investigation_history",
            history_limit=20,
        )

    @patch("app.history_service.get_settings")
    def test_disabled_returns_safely(self, mock_get_settings: object) -> None:
        mock_get_settings.return_value = self._disabled_settings()

        result = {
            "namespace": "demo-apps",
            "resource_name": "broken-nginx",
            "diagnosis": {
                "root_cause": "Container image cannot be pulled or does not exist",
                "severity": "High",
                "confidence": 95,
                "suggested_fix": "Recommended fix: review the image tag.",
                "evidence": ["failed to pull image"],
                "verification_commands": ["kubectl get pods -n demo-apps"],
                "llm": {"enabled": False},
            },
            "resource_summary": {
                "namespace": "demo-apps",
                "resource_name": "broken-nginx",
                "detected_pod_names": ["broken-nginx-abc"],
                "pod_count": 1,
                "has_logs": False,
                "investigation_timestamp_utc": "2026-07-08T00:00:00Z",
            },
        }

        self.assertIsNone(save_investigation(result))
        self.assertEqual(list_history(), [])
        self.assertIsNone(get_history_item("history-1"))


if __name__ == "__main__":
    unittest.main()