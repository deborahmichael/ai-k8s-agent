from __future__ import annotations

import unittest
from unittest.mock import patch

from app.k8s_client import CommandResult
from app.investigator import investigate_namespace


class InvestigatorPodCollectionTests(unittest.TestCase):
    @patch("app.investigator.analyze_with_openrouter", return_value={"enabled": True, "model": "test-model", "content": "llm"})
    @patch("app.investigator.run_kubectl")
    def test_collects_pod_describes_and_logs_from_label_selector(self, mock_run_kubectl: object, mock_llm: object) -> None:
        mock_run_kubectl.side_effect = [
            CommandResult(["kubectl", "get", "pods", "-n", "demo-apps"], 0, "NAME READY STATUS RESTARTS AGE\nbroken-nginx-7d8c 0/1 ImagePullBackOff 0 1m\n", ""),
            CommandResult(["kubectl", "get", "pods", "-n", "demo-apps", "-l", "app=broken-nginx"], 0, "NAME READY STATUS RESTARTS AGE\nbroken-nginx-7d8c 0/1 ImagePullBackOff 0 1m\n", ""),
            CommandResult(["kubectl", "get", "events", "-n", "demo-apps", "--sort-by=.lastTimestamp"], 0, "events output", ""),
            CommandResult(["kubectl", "describe", "deployment", "broken-nginx", "-n", "demo-apps"], 0, "deployment describe", ""),
            CommandResult(["kubectl", "describe", "pod", "broken-nginx-7d8c", "-n", "demo-apps"], 0, "pod describe", ""),
            CommandResult(["kubectl", "logs", "broken-nginx-7d8c", "-n", "demo-apps", "--tail=100"], 1, "", "Error from server (BadRequest): container is waiting: ImagePullBackOff"),
        ]

        result = investigate_namespace("demo-apps", "broken-nginx")

        self.assertEqual(result["pods"]["stdout"].strip().splitlines()[-1], "broken-nginx-7d8c 0/1 ImagePullBackOff 0 1m")
        self.assertEqual(len(result["pod_describes"]), 1)
        self.assertEqual(len(result["pod_logs"]), 1)
        self.assertEqual(result["pod_describes"][0]["pod_name"], "broken-nginx-7d8c")
        self.assertEqual(result["pod_logs"][0]["stderr"], "Error from server (BadRequest): container is waiting: ImagePullBackOff")
        self.assertEqual(result["diagnosis"]["root_cause"], "Invalid container image or image tag")
        self.assertIn("Pod describes:", mock_llm.call_args.args[0])
        self.assertIn("Pod logs:", mock_llm.call_args.args[0])
        self.assertIn("Do not apply automatically", mock_llm.call_args.args[0])

    @patch("app.investigator.analyze_with_openrouter", return_value={"enabled": False, "model": "test-model", "error": "openrouter failed"})
    @patch("app.investigator.run_kubectl")
    def test_falls_back_to_pod_name_prefix_when_label_query_finds_none(self, mock_run_kubectl: object, mock_llm: object) -> None:
        mock_run_kubectl.side_effect = [
            CommandResult(["kubectl", "get", "pods", "-n", "demo-apps"], 0, "NAME READY STATUS RESTARTS AGE\nbroken-nginx-7d8c 0/1 Pending 0 1m\nhelper 1/1 Running 0 2m\n", ""),
            CommandResult(["kubectl", "get", "pods", "-n", "demo-apps", "-l", "app=broken-nginx"], 0, "NAME READY STATUS RESTARTS AGE\n", ""),
            CommandResult(["kubectl", "get", "events", "-n", "demo-apps", "--sort-by=.lastTimestamp"], 0, "events output", ""),
            CommandResult(["kubectl", "describe", "deployment", "broken-nginx", "-n", "demo-apps"], 0, "deployment describe", ""),
            CommandResult(["kubectl", "describe", "pod", "broken-nginx-7d8c", "-n", "demo-apps"], 0, "pod describe", ""),
            CommandResult(["kubectl", "logs", "broken-nginx-7d8c", "-n", "demo-apps", "--tail=100"], 0, "pod logs", ""),
        ]

        result = investigate_namespace("demo-apps", "broken-nginx")

        self.assertEqual([entry["pod_name"] for entry in result["pod_describes"]], ["broken-nginx-7d8c"])
        self.assertEqual([entry["pod_name"] for entry in result["pod_logs"]], ["broken-nginx-7d8c"])
        self.assertEqual(result["diagnosis"]["root_cause"], "Pod is pending and may not be scheduled")
        self.assertIn("Pod describes:", mock_llm.call_args.args[0])
        self.assertIn("broken-nginx-7d8c", mock_llm.call_args.args[0])
        self.assertIn("A human operator can run", mock_llm.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
