from __future__ import annotations

import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


if "fastapi" not in sys.modules:
    fastapi_module = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FastAPI:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.routes: dict[str, object] = {}
            self.middlewares: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def add_middleware(self, *args: object, **kwargs: object) -> None:
            self.middlewares.append((args, kwargs))

        def get(self, path: str):
            def decorator(func):
                self.routes[path] = func
                return func

            return decorator

    def Query(default: object = None, **kwargs: object) -> object:
        return default

    fastapi_module.FastAPI = FastAPI
    fastapi_module.HTTPException = HTTPException
    fastapi_module.Query = Query

    middleware_module = types.ModuleType("fastapi.middleware")
    cors_module = types.ModuleType("fastapi.middleware.cors")

    class CORSMiddleware:
        pass

    cors_module.CORSMiddleware = CORSMiddleware
    middleware_module.cors = cors_module

    sys.modules["fastapi"] = fastapi_module
    sys.modules["fastapi.middleware"] = middleware_module
    sys.modules["fastapi.middleware.cors"] = cors_module

import app.main as main


class HistoryEndpointTests(unittest.TestCase):
    def _sample_result(self) -> dict[str, object]:
        return {
            "namespace": "demo-apps",
            "resource_name": "broken-nginx",
            "pods": {"command": [], "returncode": 0, "stdout": "", "stderr": ""},
            "events": {"command": [], "returncode": 0, "stdout": "", "stderr": ""},
            "deployment": {"command": [], "returncode": 0, "stdout": "", "stderr": ""},
            "services": {"command": [], "returncode": 0, "stdout": "", "stderr": ""},
            "endpoints": {"command": [], "returncode": 0, "stdout": "", "stderr": ""},
            "replicasets": {"command": [], "returncode": 0, "stdout": "", "stderr": ""},
            "pod_describes": [],
            "pod_logs": [],
            "resource_summary": {
                "namespace": "demo-apps",
                "resource_name": "broken-nginx",
                "detected_pod_names": ["broken-nginx-abc"],
                "pod_count": 1,
                "has_logs": False,
                "investigation_timestamp_utc": "2026-07-08T00:00:00Z",
            },
            "diagnosis": {
                "root_cause": "Container image cannot be pulled or does not exist",
                "severity": "High",
                "confidence": 95,
                "suggested_fix": "Recommended fix: review the image tag.",
                "verification_commands": ["kubectl get pods -n demo-apps"],
                "evidence": ["failed to pull image"],
                "llm": {"enabled": False},
            },
        }

    @patch("app.main.is_history_enabled", return_value=False)
    def test_history_endpoint_disabled_returns_safe_shape(self, mock_enabled: object) -> None:
        self.assertEqual(main.history(), {"enabled": False, "items": []})

    @patch("app.history_service.get_settings")
    @patch("app.main.investigate_namespace")
    def test_investigation_still_works_when_history_is_disabled(self, mock_investigate: object, mock_get_settings: object) -> None:
        mock_get_settings.return_value = SimpleNamespace(
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
        mock_investigate.return_value = self._sample_result()

        payload = main.investigate(namespace="demo-apps", resource_name="broken-nginx")

        self.assertEqual(payload["namespace"], "demo-apps")
        self.assertEqual(payload["resource_name"], "broken-nginx")
        self.assertFalse(payload["history_saved"])
        self.assertIsNone(payload["history_id"])

    @patch("app.main.save_investigation", side_effect=Exception("boom"))
    @patch("app.main.investigate_namespace")
    def test_history_save_failure_does_not_break_investigation(self, mock_investigate: object, mock_save: object) -> None:
        mock_investigate.return_value = self._sample_result()

        payload = main.investigate(namespace="demo-apps", resource_name="broken-nginx")

        self.assertEqual(payload["namespace"], "demo-apps")
        self.assertFalse(payload["history_saved"])
        self.assertIsNone(payload["history_id"])


if __name__ == "__main__":
    unittest.main()