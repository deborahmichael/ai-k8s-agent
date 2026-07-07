from __future__ import annotations

import unittest

from app.investigator import diagnose


class DiagnosisRulesTests(unittest.TestCase):
    def test_image_pull_backoff_diagnosis(self) -> None:
        result = diagnose(
            [
                'Deployment broken-nginx failed to pull image "nginx:wrongtag"',
                'Back-off pulling image "nginx:wrongtag" for broken-nginx-7d8c',
            ],
            "demo-apps",
            "broken-nginx",
        )

        self.assertEqual(result["root_cause"], "Container image cannot be pulled or does not exist")
        self.assertEqual(result["severity"], "High")
        self.assertGreaterEqual(result["confidence"], 90)
        self.assertIn("failed to pull image", "\n".join(result["evidence"]).lower())
        self.assertNotIn("crashloop-app", "\n".join(result["evidence"]).lower())

    def test_crashloop_backoff_diagnosis(self) -> None:
        result = diagnose(
            [
                'Pod crashloop-app-abc is in CrashLoopBackOff',
                'Last State: Terminated',
                'Exit Code: 1',
                'startup failed while initializing',
            ],
            "demo-apps",
            "crashloop-app",
        )

        self.assertEqual(result["root_cause"], "Application container exits unexpectedly or crashes repeatedly")
        self.assertEqual(result["severity"], "High")
        joined = "\n".join(result["evidence"])
        self.assertIn("crashloopbackoff", joined.lower())
        self.assertIn("exit code", joined.lower())
        self.assertIn("startup failed", joined.lower())

    def test_pending_failedscheduling_diagnosis(self) -> None:
        result = diagnose(
            [
                'Pod pending-app-abc is Pending',
                'Warning  FailedScheduling  0/1 nodes are available: 1 Insufficient cpu, 1 Insufficient memory.',
            ],
            "demo-apps",
            "pending-app",
        )

        self.assertEqual(result["root_cause"], "Pod is pending because the scheduler cannot place it on a node")
        self.assertEqual(result["severity"], "Medium")
        joined = "\n".join(result["evidence"])
        self.assertIn("failedscheduling", joined.lower())
        self.assertIn("insufficient cpu", joined.lower())
        self.assertIn("insufficient memory", joined.lower())

    def test_probe_failure_diagnosis(self) -> None:
        result = diagnose(
            [
                'Readiness probe failed: HTTP probe failed with statuscode: 500',
            ],
            "demo-apps",
            "probe-app",
        )

        self.assertEqual(result["root_cause"], "Readiness or liveness probe is failing")
        self.assertEqual(result["severity"], "High")
        self.assertIn("probe failed", "\n".join(result["evidence"]).lower())


if __name__ == "__main__":
    unittest.main()
