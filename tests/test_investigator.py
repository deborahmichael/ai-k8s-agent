from __future__ import annotations

import unittest
from unittest.mock import patch

from app.k8s_client import CommandResult
from app.investigator import investigate_namespace


def result(command: list[str], returncode: int, stdout: str, stderr: str) -> CommandResult:
    return CommandResult(command, returncode, stdout, stderr)


class InvestigatorIntegrationTests(unittest.TestCase):
    @patch(
        "app.investigator.analyze_with_openrouter",
        return_value={"enabled": True, "model": "test-model", "content": "llm"},
    )
    @patch("app.investigator.run_kubectl")
    def test_crashloop_diagnosis_ignores_broken_nginx_events(self, mock_run_kubectl: object, mock_llm: object) -> None:
        mock_run_kubectl.side_effect = [
            result(
                ["kubectl", "get", "pods", "-n", "demo-apps"],
                0,
                "NAME READY STATUS RESTARTS AGE\ncrashloop-app-abc 0/1 CrashLoopBackOff 3 2m\nbroken-nginx-7d8c 0/1 ImagePullBackOff 0 1m\n",
                "",
            ),
            result(
                ["kubectl", "get", "pods", "-n", "demo-apps", "-l", "app=crashloop-app"],
                0,
                "NAME READY STATUS RESTARTS AGE\ncrashloop-app-abc 0/1 CrashLoopBackOff 3 2m\n",
                "",
            ),
            result(["kubectl", "get", "svc", "-n", "demo-apps"], 0, "NAME TYPE CLUSTER-IP EXTERNAL-IP PORT(S) AGE\ndemo-svc ClusterIP 10.0.0.1 <none> 80/TCP 1m\n", ""),
            result(["kubectl", "get", "endpoints", "-n", "demo-apps"], 0, "NAME ENDPOINTS AGE\ndemo-svc 10.244.0.10:80 1m\n", ""),
            result(["kubectl", "get", "rs", "-n", "demo-apps"], 0, "NAME DESIRED CURRENT READY AGE\ncrashloop-app-abc 1 1 0 2m\nbroken-nginx-7d8c 1 1 0 1m\n", ""),
            result(
                ["kubectl", "get", "events", "-n", "demo-apps", "--sort-by=.lastTimestamp"],
                0,
                'Warning  Failed  Failed to pull image "nginx:wrongtag" for broken-nginx-7d8c\nWarning  BackOff  Back-off restarting failed container for crashloop-app-abc',
                "",
            ),
            result(["kubectl", "describe", "deployment", "crashloop-app", "-n", "demo-apps"], 0, "Progressing: False\nReason: ProgressDeadlineExceeded", ""),
            result(
                ["kubectl", "describe", "pod", "crashloop-app-abc", "-n", "demo-apps"],
                0,
                "State: Waiting\n  Reason: CrashLoopBackOff\nLast State: Terminated\n  Reason: Error\n  Exit Code: 1",
                "",
            ),
            result(["kubectl", "logs", "crashloop-app-abc", "-n", "demo-apps", "--tail=100"], 0, "startup failed\nnon-zero exit", ""),
        ]

        result_data = investigate_namespace("demo-apps", "crashloop-app")

        self.assertEqual(result_data["diagnosis"]["root_cause"], "Application container exits unexpectedly or crashes repeatedly")
        evidence = result_data["diagnosis"]["evidence"]
        joined = "\n".join(evidence).lower()
        self.assertNotIn("broken-nginx", joined)
        self.assertIn("crashloopbackoff", joined)
        self.assertIn("startup failed", joined)
        self.assertNotIn("broken-nginx", mock_llm.call_args.args[0].lower())
        self.assertIn("Do not apply automatically", mock_llm.call_args.args[0])

    @patch(
        "app.investigator.analyze_with_openrouter",
        return_value={"enabled": True, "model": "test-model", "content": "llm"},
    )
    @patch("app.investigator.run_kubectl")
    def test_pending_diagnosis_ignores_other_apps(self, mock_run_kubectl: object, mock_llm: object) -> None:
        mock_run_kubectl.side_effect = [
            result(
                ["kubectl", "get", "pods", "-n", "demo-apps"],
                0,
                "NAME READY STATUS RESTARTS AGE\npending-app-abc 0/1 Pending 0 5m\nbroken-nginx-7d8c 0/1 ImagePullBackOff 0 1m\ncrashloop-app-xyz 0/1 CrashLoopBackOff 4 3m\n",
                "",
            ),
            result(
                ["kubectl", "get", "pods", "-n", "demo-apps", "-l", "app=pending-app"],
                0,
                "NAME READY STATUS RESTARTS AGE\npending-app-abc 0/1 Pending 0 5m\n",
                "",
            ),
            result(["kubectl", "get", "svc", "-n", "demo-apps"], 0, "NAME TYPE CLUSTER-IP EXTERNAL-IP PORT(S) AGE\n", ""),
            result(["kubectl", "get", "endpoints", "-n", "demo-apps"], 0, "NAME ENDPOINTS AGE\n", ""),
            result(["kubectl", "get", "rs", "-n", "demo-apps"], 0, "NAME DESIRED CURRENT READY AGE\npending-app-abc 1 0 0 5m\n", ""),
            result(
                ["kubectl", "get", "events", "-n", "demo-apps", "--sort-by=.lastTimestamp"],
                0,
                'Warning  FailedScheduling  0/1 nodes are available: 1 Insufficient cpu, 1 Insufficient memory.\nWarning  Failed  Failed to pull image "nginx:wrongtag" for broken-nginx-7d8c',
                "",
            ),
            result(["kubectl", "describe", "deployment", "pending-app", "-n", "demo-apps"], 0, "Replica Failure\nReason: FailedScheduling", ""),
            result(
                ["kubectl", "describe", "pod", "pending-app-abc", "-n", "demo-apps"],
                0,
                "Status: Pending\n  Reason: Unschedulable\nEvents:\n  Warning  FailedScheduling  0/1 nodes are available: 1 Insufficient cpu, 1 Insufficient memory.",
                "",
            ),
            result(["kubectl", "logs", "pending-app-abc", "-n", "demo-apps", "--tail=100"], 1, "", "Error from server (BadRequest): container is waiting: ContainerCreating"),
        ]

        result_data = investigate_namespace("demo-apps", "pending-app")

        self.assertEqual(result_data["diagnosis"]["root_cause"], "Pod is pending because the scheduler cannot place it on a node")
        evidence = result_data["diagnosis"]["evidence"]
        joined = "\n".join(evidence).lower()
        self.assertIn("pending-app", joined)
        self.assertNotIn("broken-nginx", joined)
        self.assertNotIn("crashloop-app", joined)
        self.assertIn("failedscheduling", joined)
        self.assertIn("Do not apply automatically", mock_llm.call_args.args[0])
        self.assertIn("pending-app", mock_llm.call_args.args[0].lower())
        self.assertNotIn("broken-nginx", mock_llm.call_args.args[0].lower())

    @patch(
        "app.investigator.analyze_with_openrouter",
        return_value={"enabled": True, "model": "test-model", "content": "llm"},
    )
    @patch("app.investigator.run_kubectl")
    def test_imagepull_diagnosis_still_works_for_broken_nginx(self, mock_run_kubectl: object, mock_llm: object) -> None:
        mock_run_kubectl.side_effect = [
            result(
                ["kubectl", "get", "pods", "-n", "demo-apps"],
                0,
                "NAME READY STATUS RESTARTS AGE\nbroken-nginx-7d8c 0/1 ImagePullBackOff 0 1m\npending-app-abc 0/1 Pending 0 5m\n",
                "",
            ),
            result(
                ["kubectl", "get", "pods", "-n", "demo-apps", "-l", "app=broken-nginx"],
                0,
                "NAME READY STATUS RESTARTS AGE\nbroken-nginx-7d8c 0/1 ImagePullBackOff 0 1m\n",
                "",
            ),
            result(["kubectl", "get", "svc", "-n", "demo-apps"], 0, "NAME TYPE CLUSTER-IP EXTERNAL-IP PORT(S) AGE\n", ""),
            result(["kubectl", "get", "endpoints", "-n", "demo-apps"], 0, "NAME ENDPOINTS AGE\n", ""),
            result(["kubectl", "get", "rs", "-n", "demo-apps"], 0, "NAME DESIRED CURRENT READY AGE\nbroken-nginx-7d8c 1 0 0 1m\n", ""),
            result(
                ["kubectl", "get", "events", "-n", "demo-apps", "--sort-by=.lastTimestamp"],
                0,
                'Warning  Failed  Failed to pull image "nginx:wrongtag" for broken-nginx-7d8c\nWarning  FailedScheduling  0/1 nodes are available: 1 Insufficient cpu.',
                "",
            ),
            result(["kubectl", "describe", "deployment", "broken-nginx", "-n", "demo-apps"], 0, "ProgressDeadlineExceeded", ""),
            result(["kubectl", "describe", "pod", "broken-nginx-7d8c", "-n", "demo-apps"], 0, "Reason: ErrImagePull\nBack-off pulling image \"nginx:wrongtag\"", ""),
            result(["kubectl", "logs", "broken-nginx-7d8c", "-n", "demo-apps", "--tail=100"], 1, "", "Error from server (BadRequest): container is waiting: ImagePullBackOff"),
        ]

        result_data = investigate_namespace("demo-apps", "broken-nginx")

        self.assertEqual(result_data["diagnosis"]["root_cause"], "Container image cannot be pulled or does not exist")
        evidence = result_data["diagnosis"]["evidence"]
        joined = "\n".join(evidence).lower()
        self.assertIn("broken-nginx", joined)
        self.assertNotIn("crashloop-app", joined)
        self.assertIn("failed to pull image", joined)
        self.assertIn("broken-nginx", mock_llm.call_args.args[0].lower())
        self.assertNotIn("crashloop-app", mock_llm.call_args.args[0].lower())
        self.assertNotIn("pending-app", mock_llm.call_args.args[0].lower())


if __name__ == "__main__":
    unittest.main()
