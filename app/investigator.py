from __future__ import annotations

import json
from datetime import UTC, datetime

from app.k8s_client import run_kubectl
from app.openrouter_client import analyze_with_openrouter
from app.settings import get_settings


LLM_USER_PROMPT_HEADER = (
    "You are reviewing Kubernetes evidence for a human operator. "
    "Do not say you will apply, execute, fix, update, change, patch, or restart anything yourself. "
    "Only recommend commands that a human operator can review and run. "
    "Use wording like 'Recommended fix', 'A human operator can run', 'To verify', and 'Do not apply automatically'."
)


IMAGE_PULL_KEYWORDS = (
    "imagepullbackoff",
    "errimagepull",
    "failed to pull image",
    "image not found",
    "back-off pulling image",
    "pull access denied",
)

CRASH_KEYWORDS = (
    "crashloopbackoff",
    "back-off restarting failed container",
    "startup failed",
    "startup error",
    "exit code",
    "non-zero exit",
    "exited with status",
    "terminated",
)

PENDING_KEYWORDS = (
    "pending",
    "failedscheduling",
    "insufficient cpu",
    "insufficient memory",
    "pod unschedulable",
)

PROBE_KEYWORDS = (
    "readiness probe failed",
    "liveness probe failed",
    "startup probe failed",
    "probe failed",
)

PROGRESS_DEADLINE_KEYWORDS = (
    "progressdeadlineexceeded",
    "exceeded its progress deadline",
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


def _extract_related_replicaset_names(resource_name: str, replicasets_output: str) -> list[str]:
    related: list[str] = []
    seen: set[str] = set()
    resource_lower = resource_name.lower()

    for line in replicasets_output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("NAME "):
            continue

        rs_name = stripped.split()[0]
        if resource_lower in rs_name.lower() and rs_name not in seen:
            related.append(rs_name)
            seen.add(rs_name)

    return related


def _scope_terms(resource_name: str, pod_names: list[str], replicaset_names: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for term in [resource_name, *pod_names, *replicaset_names]:
        lowered = term.lower().strip()
        if lowered and lowered not in seen:
            terms.append(lowered)
            seen.add(lowered)
    return terms


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


def _result_text(result: object) -> str:
    stdout = getattr(result, "stdout", "") or ""
    stderr = getattr(result, "stderr", "") or ""
    return "\n".join(part for part in (stdout, stderr) if part)


def _scoped_lines(blocks: list[str], scope_terms: list[str], limit: int = 50) -> list[str]:
    scoped: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if any(term in lowered for term in scope_terms) and stripped not in seen:
                scoped.append(stripped)
                seen.add(stripped)
            if len(scoped) >= limit:
                return scoped
    return scoped


def _scoped_result_text(result: object, scope_terms: list[str]) -> str:
    scoped_lines = _scoped_lines([_result_text(result)], scope_terms)
    return "\n".join(scoped_lines) or "None"


def _collect_evidence(blocks: list[str], keywords: tuple[str, ...], limit: int = 5) -> list[str]:
    evidence: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            lowered = line.lower()
            if any(keyword in lowered for keyword in keywords):
                cleaned = line.strip()
                if cleaned and cleaned not in evidence:
                    evidence.append(cleaned)
            if len(evidence) >= limit:
                return evidence
    return evidence


def _rule_result(
    *,
    root_cause: str,
    severity: str,
    confidence: int,
    suggested_fix: str,
    verification_commands: list[str],
    evidence: list[str],
) -> dict[str, object]:
    return {
        "root_cause": root_cause,
        "severity": severity,
        "confidence": confidence,
        "suggested_fix": suggested_fix,
        "verification_commands": verification_commands,
        "evidence": evidence,
    }


def diagnose(blocks: list[str], namespace: str, resource_name: str, pod_texts: list[str] | None = None) -> dict[str, object]:
    all_blocks = [block for block in blocks + (pod_texts or []) if block]

    crash_evidence = _collect_evidence(all_blocks, CRASH_KEYWORDS)
    if crash_evidence:
        return _rule_result(
            root_cause="Application container exits unexpectedly or crashes repeatedly",
            severity="High",
            confidence=87,
            suggested_fix=(
                "Recommended fix: a human operator can review container logs, startup commands, configuration, "
                "and recent code changes, then verify the pod again."
            ),
            verification_commands=[
                f"kubectl describe pod -n {namespace} -l app={resource_name}",
                f"kubectl logs -n {namespace} -l app={resource_name} --tail=100",
                f"kubectl get events -n {namespace} --sort-by=.lastTimestamp",
            ],
            evidence=crash_evidence,
        )

    image_pull_evidence = _collect_evidence(all_blocks, IMAGE_PULL_KEYWORDS)
    if image_pull_evidence:
        return _rule_result(
            root_cause="Container image cannot be pulled or does not exist",
            severity="High",
            confidence=95,
            suggested_fix=(
                "Recommended fix: a human operator can review the image name and tag in the Deployment, "
                "correct the reference if needed, and then verify the rollout."
            ),
            verification_commands=[
                f"kubectl get pods -n {namespace}",
                f"kubectl describe deployment {resource_name} -n {namespace}",
                f"kubectl rollout status deployment/{resource_name} -n {namespace}",
            ],
            evidence=image_pull_evidence,
        )

    pending_evidence = _collect_evidence(all_blocks, PENDING_KEYWORDS)
    if pending_evidence:
        return _rule_result(
            root_cause="Pod is pending because the scheduler cannot place it on a node",
            severity="Medium",
            confidence=82,
            suggested_fix=(
                "Recommended fix: a human operator can review resource requests, node capacity, selectors, "
                "taints, and tolerations, then verify scheduling again."
            ),
            verification_commands=[
                f"kubectl get pods -n {namespace} -l app={resource_name}",
                f"kubectl describe deployment {resource_name} -n {namespace}",
                f"kubectl get events -n {namespace} --sort-by=.lastTimestamp",
            ],
            evidence=pending_evidence,
        )

    progress_deadline_evidence = _collect_evidence(all_blocks, PROGRESS_DEADLINE_KEYWORDS)
    if progress_deadline_evidence:
        return _rule_result(
            root_cause="Deployment did not finish progressing before the deadline",
            severity="High",
            confidence=90,
            suggested_fix=(
                "Recommended fix: a human operator can review rollout progress, pod readiness, and probe timing, "
                "then verify the rollout after any manual remediation."
            ),
            verification_commands=[
                f"kubectl rollout status deployment/{resource_name} -n {namespace}",
                f"kubectl describe deployment {resource_name} -n {namespace}",
                f"kubectl get events -n {namespace} --sort-by=.lastTimestamp",
            ],
            evidence=progress_deadline_evidence,
        )

    probe_evidence = _collect_evidence(all_blocks, PROBE_KEYWORDS)
    if probe_evidence:
        return _rule_result(
            root_cause="Readiness or liveness probe is failing",
            severity="High",
            confidence=88,
            suggested_fix=(
                "Recommended fix: a human operator can review the probe configuration, startup timing, "
                "and application health behavior, then verify the pod again."
            ),
            verification_commands=[
                f"kubectl describe pod -n {namespace} -l app={resource_name}",
                f"kubectl logs -n {namespace} -l app={resource_name} --tail=100",
                f"kubectl get events -n {namespace} --sort-by=.lastTimestamp",
            ],
            evidence=probe_evidence,
        )

    return _rule_result(
        root_cause="No known issue detected from current rules",
        severity="Unknown",
        confidence=40,
        suggested_fix="Recommended fix: a human operator can review the raw Kubernetes output and LLM explanation.",
        verification_commands=[
            f"kubectl get pods -n {namespace}",
            f"kubectl get events -n {namespace} --sort-by=.lastTimestamp",
        ],
        evidence=_collect_evidence(all_blocks, ("error", "warning", "failed", "not ready")),
    )


def _section(title: str, body: str) -> str:
    return f"{title}:\n{body or 'None'}"


def _build_llm_prompt(
    *,
    namespace: str,
    resource_name: str,
    pods_text: str,
    labeled_pods_text: str,
    services_text: str,
    endpoints_text: str,
    replicasets_text: str,
    events_text: str,
    deployment_text: str,
    pod_describes: list[dict[str, object]],
    pod_logs: list[dict[str, object]],
    resource_summary: dict[str, object],
    diagnosis: dict[str, object],
) -> str:
    pod_describe_text = "\n\n".join(_entry_text(entry, "Pod describe") for entry in pod_describes) or "None"
    pod_logs_text = "\n\n".join(_entry_text(entry, "Pod logs") for entry in pod_logs) or "None"
    diagnosis_evidence = diagnosis.get("evidence", [])
    diagnosis_evidence_text = "\n".join(f"- {item}" for item in diagnosis_evidence) or "None"

    sections = [
        LLM_USER_PROMPT_HEADER,
        f"Namespace: {namespace}",
        f"Resource: {resource_name}",
        _section("Resource summary", json.dumps(resource_summary, indent=2, sort_keys=True)),
        _section("Services", services_text),
        _section("Endpoints", endpoints_text),
        _section("ReplicaSets", replicasets_text),
        _section("All pods", pods_text),
        _section("Labeled pods", labeled_pods_text),
        _section("Events", events_text),
        _section("Deployment describe", deployment_text),
        _section("Pod describes", pod_describe_text),
        _section("Pod logs", pod_logs_text),
        _section("Diagnosis evidence", diagnosis_evidence_text),
        "Return a concise operator-safe explanation with these sections only: Issue, Evidence, Likely root cause, Recommended fix, Commands a human operator can run, Verification steps, Risk / caution, Do not apply automatically.",
    ]
    return "\n\n".join(sections)


def investigate_namespace(namespace: str, resource_name: str) -> dict[str, object]:
    settings = get_settings()

    pods = run_kubectl(["get", "pods", "-n", namespace])
    labeled_pods = run_kubectl(["get", "pods", "-n", namespace, "-l", f"app={resource_name}"])
    services = run_kubectl(["get", "svc", "-n", namespace])
    endpoints = run_kubectl(["get", "endpoints", "-n", namespace])
    replicasets = run_kubectl(["get", "rs", "-n", namespace])
    events = run_kubectl(["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"])
    deployment = run_kubectl(["describe", "deployment", resource_name, "-n", namespace])

    matching_pods = _extract_matching_pods(resource_name, labeled_pods.stdout)
    if not matching_pods:
        matching_pods = _extract_matching_pods(resource_name, pods.stdout)

    related_replicaset_names = _extract_related_replicaset_names(resource_name, replicasets.stdout)
    scope_terms = _scope_terms(resource_name, matching_pods, related_replicaset_names)

    pod_describes: list[dict[str, object]] = []
    pod_logs: list[dict[str, object]] = []
    for pod_name in matching_pods:
        describe_result = run_kubectl(["describe", "pod", pod_name, "-n", namespace])
        logs_result = run_kubectl(["logs", pod_name, "-n", namespace, f"--tail={settings.log_tail_lines}"])

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
    scoped_namespace_blocks = _scoped_lines(
        [
            _result_text(pods),
            _result_text(labeled_pods),
            _result_text(services),
            _result_text(endpoints),
            _result_text(replicasets),
            _result_text(events),
        ],
        scope_terms,
    )
    diagnosis_blocks = [
        _result_text(deployment),
        *pod_context_texts,
        *scoped_namespace_blocks,
    ]

    resource_summary = {
        "namespace": namespace,
        "resource_name": resource_name,
        "detected_pod_names": matching_pods,
        "pod_count": len(matching_pods),
        "has_logs": any((entry.get("stdout") or "").strip() for entry in pod_logs),
        "investigation_timestamp_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "related_replicaset_names": related_replicaset_names,
    }

    diagnosis = diagnose(diagnosis_blocks, namespace, resource_name)
    scoped_pods_text = _scoped_result_text(pods, scope_terms)
    scoped_labeled_pods_text = _scoped_result_text(labeled_pods, scope_terms)
    scoped_services_text = _scoped_result_text(services, scope_terms)
    scoped_endpoints_text = _scoped_result_text(endpoints, scope_terms)
    scoped_replicasets_text = _scoped_result_text(replicasets, scope_terms)
    scoped_events_text = _scoped_result_text(events, scope_terms)
    llm_prompt = _build_llm_prompt(
        namespace=namespace,
        resource_name=resource_name,
        pods_text=scoped_pods_text,
        labeled_pods_text=scoped_labeled_pods_text,
        services_text=scoped_services_text,
        endpoints_text=scoped_endpoints_text,
        replicasets_text=scoped_replicasets_text,
        events_text=scoped_events_text,
        deployment_text=_result_text(deployment),
        pod_describes=pod_describes,
        pod_logs=pod_logs,
        resource_summary=resource_summary,
        diagnosis=diagnosis,
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
        "services": {
            "command": services.command,
            "returncode": services.returncode,
            "stdout": services.stdout,
            "stderr": services.stderr,
        },
        "endpoints": {
            "command": endpoints.command,
            "returncode": endpoints.returncode,
            "stdout": endpoints.stdout,
            "stderr": endpoints.stderr,
        },
        "replicasets": {
            "command": replicasets.command,
            "returncode": replicasets.returncode,
            "stdout": replicasets.stdout,
            "stderr": replicasets.stderr,
        },
        "pod_describes": pod_describes,
        "pod_logs": pod_logs,
        "resource_summary": resource_summary,
        "diagnosis": {
            **diagnosis,
            "llm": analyze_with_openrouter(llm_prompt),
        },
    }
