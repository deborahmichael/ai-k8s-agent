from __future__ import annotations

from app.k8s_client import run_kubectl
from app.openrouter_client import analyze_with_openrouter


LLM_USER_PROMPT_HEADER = (
    "You are reviewing Kubernetes evidence for a human operator. "
    "Do not say you will apply, execute, fix, update, change, patch, or restart anything yourself. "
    "Only recommend commands that a human operator can review and run. "
    "Use wording like 'Recommended fix', 'A human operator can run', 'To verify', and 'Do not apply automatically'."
)


def _extract_matching_pods(resource_name: str, pods_output: str) -> list[str]:
    matching_pods: list[str] = []
    seen: set[str] = set()

    for line in pods_output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("NAME "):
            continue

        pod_name = stripped.split()[0]
        if pod_name.startswith(resource_name) and pod_name not in seen:
            matching_pods.append(pod_name)
            seen.add(pod_name)

    return matching_pods


def _entry_text(entry: dict[str, object], title: str) -> str:
    return "\n".join(
        [
            f"{title}: {entry.get('pod_name', '')}",
            f"Command: {entry.get('command', [])}",
            f"Return code: {entry.get('returncode', '')}",
            "Stdout:",
            str(entry.get("stdout", "")),
            "Stderr:",
            str(entry.get("stderr", "")),
        ]
    )


def _pod_text_blocks(pod_describes: list[dict[str, object]], pod_logs: list[dict[str, object]]) -> list[str]:
    blocks: list[str] = []
    for entry in pod_describes:
        blocks.append(_entry_text(entry, "Pod describe"))
    for entry in pod_logs:
        blocks.append(_entry_text(entry, "Pod logs"))
    return blocks


def diagnose(outputs: list[str], namespace: str, resource_name: str, pod_texts: list[str] | None = None) -> dict[str, object]:
    text = "\n".join([value for value in outputs + (pod_texts or []) if value]).lower()

    if any(keyword in text for keyword in ("imagepullbackoff", "errimagepull", "not found")):
        return {
            "root_cause": "Invalid container image or image tag",
            "severity": "High",
            "confidence": 95,
            "suggested_fix": "Update the deployment to use a valid image tag, then verify rollout status.",
            "verification_commands": [
                f"kubectl get pods -n {namespace}",
                f"kubectl rollout status deployment/{resource_name} -n {namespace}",
            ],
        }

    if "crashloopbackoff" in text:
        return {
            "root_cause": "Application container is crashing repeatedly",
            "severity": "High",
            "confidence": 85,
            "suggested_fix": "Check container logs and application startup configuration.",
        }

    if "pending" in text:
        return {
            "root_cause": "Pod is pending and may not be scheduled",
            "severity": "Medium",
            "confidence": 75,
            "suggested_fix": "Check node resources, taints, tolerations, and PVCs.",
        }

    return {
        "root_cause": "No known issue detected from current rules",
        "severity": "Unknown",
        "confidence": 40,
        "suggested_fix": "Review raw Kubernetes output or use LLM analysis.",
    }


def investigate_namespace(namespace: str, resource_name: str) -> dict[str, object]:
    pods = run_kubectl(["get", "pods", "-n", namespace])
    labeled_pods = run_kubectl(["get", "pods", "-n", namespace, "-l", f"app={resource_name}"])
    events = run_kubectl(["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"])
    deployment = run_kubectl(["describe", "deployment", resource_name, "-n", namespace])

    matching_pods = _extract_matching_pods(resource_name, labeled_pods.stdout)
    if not matching_pods:
        matching_pods = _extract_matching_pods(resource_name, pods.stdout)

    pod_describes: list[dict[str, object]] = []
    pod_logs: list[dict[str, object]] = []
    for pod_name in matching_pods:
        describe_result = run_kubectl(["describe", "pod", pod_name, "-n", namespace])
        logs_result = run_kubectl(["logs", pod_name, "-n", namespace, "--tail=100"])

        pod_describes.append(
            {
                "pod_name": pod_name,
                "command": describe_result.command,
                "returncode": describe_result.returncode,
                "stdout": describe_result.stdout,
                "stderr": describe_result.stderr,
            }
        )
        pod_logs.append(
            {
                "pod_name": pod_name,
                "command": logs_result.command,
                "returncode": logs_result.returncode,
                "stdout": logs_result.stdout,
                "stderr": logs_result.stderr,
            }
        )

    pod_context_texts = _pod_text_blocks(pod_describes, pod_logs)
    raw_outputs = [
        pods.stdout,
        pods.stderr,
        labeled_pods.stdout,
        labeled_pods.stderr,
        events.stdout,
        events.stderr,
        deployment.stdout,
        deployment.stderr,
        *pod_context_texts,
    ]

    llm_prompt = "\n\n".join(
        [
            LLM_USER_PROMPT_HEADER,
            f"Namespace: {namespace}",
            f"Resource: {resource_name}",
            "Evidence to review:",
            "All pods:\n" + "\n".join(filter(None, [pods.stdout, pods.stderr])),
            "Labeled pods:\n" + "\n".join(filter(None, [labeled_pods.stdout, labeled_pods.stderr])),
            "Events:\n" + "\n".join(filter(None, [events.stdout, events.stderr])),
            "Deployment describe:\n" + "\n".join(filter(None, [deployment.stdout, deployment.stderr])),
            "Pod describes:\n" + ("\n\n".join(_entry_text(entry, "Pod describe") for entry in pod_describes) if pod_describes else "None"),
            "Pod logs:\n" + ("\n\n".join(_entry_text(entry, "Pod logs") for entry in pod_logs) if pod_logs else "None"),
            "Response guidance: use 'Recommended fix', 'A human operator can run', 'To verify', and 'Do not apply automatically'.",
        ]
    )

    return {
        "namespace": namespace,
        "resource_name": resource_name,
        "pods": {
            "command": pods.command,
            "returncode": pods.returncode,
            "stdout": pods.stdout,
            "stderr": pods.stderr,
        },
        "events": {
            "command": events.command,
            "returncode": events.returncode,
            "stdout": events.stdout,
            "stderr": events.stderr,
        },
        "deployment": {
            "command": deployment.command,
            "returncode": deployment.returncode,
            "stdout": deployment.stdout,
            "stderr": deployment.stderr,
        },
        "pod_describes": pod_describes,
        "pod_logs": pod_logs,
        "diagnosis": {
            **diagnose(raw_outputs, namespace, resource_name, pod_context_texts),
            "llm": analyze_with_openrouter(llm_prompt),
        },
    }
