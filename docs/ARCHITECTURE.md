# Architecture

## High-Level Diagram

```text
+-------------------+
| Client / curl      |
+-------------------+
          |
          v
+----------------------------+
| FastAPI /api/investigate   |
+----------------------------+
          |
          v
+----------------------------+       +-------------------------+
| app/investigator.py        |------>| app/openrouter_client.py|
| - read-only kubectl calls  |       | - safe LLM prompt       |
| - pod discovery            |       | - structured errors     |
| - pod logs / describes     |       +-------------------------+
| - services / endpoints / rs |
| - rule-based diagnosis     |
+----------------------------+
          |
          v
+----------------------------+
| Kubernetes cluster / k3s   |
+----------------------------+
```

## Request Flow

1. A caller sends `GET /api/investigate?namespace=...&resource_name=...`.
2. The backend collects read-only Kubernetes evidence.
3. The investigation layer finds related pods and gathers per-pod describes and logs.
4. The rule engine inspects all evidence and produces a structured diagnosis.
5. The OpenRouter client receives the evidence, summary, and diagnosis context.
6. The API returns a single JSON payload with both raw evidence and LLM output.

## Investigation Layer Responsibilities

- Run only read-only `kubectl` commands
- Collect pods, events, deployment describe output, pod describes, pod logs, services, endpoints, and ReplicaSets
- Build `resource_summary`
- Detect common failure patterns with simple rules
- Keep the response shape stable for API clients

## LLM Reasoning Layer Responsibilities

- Summarize the issue for a human operator
- Reference the collected evidence
- Recommend manual commands only
- Avoid autonomous remediation language
- Return a concise operator-safe explanation

## Safety Model

- The backend does not patch, delete, set, or restart workloads
- The LLM prompt explicitly says not to apply changes automatically
- The LLM may suggest commands, but the human operator must review and run them
- Any corrective action is manual

## Future Improvements

- Frontend dashboard for investigation results
- InsForge auth and history tracking
- Kubernetes service account and RBAC support
- Deployment into k3s
- GitHub Actions CI
