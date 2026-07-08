# AI Kubernetes Troubleshooting Agent

A small, read-only FastAPI backend for investigating Kubernetes problems.

The agent collects cluster evidence with `kubectl`, applies rule-based diagnosis, and optionally asks OpenRouter for a concise operator-safe explanation.

## What It Does

- Investigates a workload by namespace and resource name
- Collects pods, events, deployment describe output, pod describes, pod logs, services, endpoints, and ReplicaSets
- Builds a small resource summary for the current investigation
- Uses rule-based diagnosis for common failure modes
- Uses OpenRouter for a second-pass explanation that is safe for human operators
- Never applies fixes automatically

## Architecture

```
Client
  |
  v
FastAPI /api/investigate
  |
  +--> app/investigator.py
  |      - runs read-only kubectl commands
  |      - discovers related pods
  |      - gathers pod describe/log output
  |      - collects services, endpoints, ReplicaSets
  |      - builds resource_summary
  |      - runs rule-based diagnosis
  |
  +--> app/openrouter_client.py
         - sends a safety-constrained prompt to OpenRouter
         - returns an explanation or a structured error
```

### Request Flow

1. The client calls `/api/investigate?namespace=...&resource_name=...`.
2. The backend gathers read-only Kubernetes evidence.
3. The diagnosis layer scans the collected text for known patterns.
4. The LLM layer receives the evidence, summary, and diagnosis context.
5. The API returns one JSON payload with all evidence and explanations.

### Investigation Responsibilities

- Discover pods linked to the requested resource
- Describe each pod and fetch recent logs
- Collect supporting cluster context with `kubectl get svc`, `kubectl get endpoints`, and `kubectl get rs`
- Build a structured summary for the incident
- Keep every command read-only

### LLM Responsibilities

- Summarize the likely issue
- Describe evidence in operator-friendly language
- Recommend commands that a human operator can review and run
- Never claim it will fix, apply, patch, or change the cluster

### Safety Model

- No `kubectl apply`
- No `kubectl delete`
- No `kubectl patch`
- No `kubectl set`
- No `kubectl rollout restart`
- No automatic remediation of any kind
- The LLM may recommend commands, but a human operator must run them

## Prerequisites

- Python 3.12 or newer
- `kubectl` installed and configured
- Access to a Kubernetes cluster or k3s context
- Optional: OpenRouter API key for LLM explanations

## Required Environment Variables

Copy the template and fill in your local values:

```bash
copy .env.example .env
```

Environment variables used by the backend:

- `OPENROUTER_API_KEY` - optional, enables the LLM explanation
- `OPENROUTER_MODEL` - defaults to `nvidia/nemotron-3-ultra-550b-a55b:free`
- `KUBECTL_TIMEOUT_SECONDS` - defaults to `15`
- `LOG_TAIL_LINES` - defaults to `100`
- `CORS_ORIGINS` - optional, comma-separated allowed browser origins such as `http://localhost:5173`

## Run Locally

1. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

   On WSL or Linux:

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   make install
   ```

3. Start the API:

   ```bash
   make run
   ```

4. Open the docs or call the API directly at `http://127.0.0.1:8000`.

## Deploy Into Local k3s

This project can run inside a local k3s cluster with a small read-only footprint.

1. Build the container image locally:

   ```bash
   docker build -t ai-k8s-agent:local .
   ```

2. If your local k3s node cannot see the Docker image directly, save and import it into k3s/containerd:

   ```bash
   docker save ai-k8s-agent:local -o ai-k8s-agent-local.tar
   sudo k3s ctr images import ai-k8s-agent-local.tar
   ```

3. Create the OpenRouter secret manually. Do not commit the secret file:

   ```bash
   kubectl create namespace ai-k8s-agent
   kubectl create secret generic ai-k8s-agent-secrets \
     -n ai-k8s-agent \
     --from-literal=OPENROUTER_API_KEY="$OPENROUTER_API_KEY"
   ```

4. Apply the manifests:

   ```bash
   kubectl apply -f k8s/namespace.yaml
   kubectl apply -f k8s/serviceaccount.yaml
   kubectl apply -f k8s/rbac.yaml
   kubectl apply -f k8s/deployment.yaml
   kubectl apply -f k8s/service.yaml
   ```

5. Port-forward the service:

   ```bash
   kubectl port-forward svc/ai-k8s-agent -n ai-k8s-agent 8000:8000
   ```

6. Test the deployment:

   ```bash
   curl http://localhost:8000/health
   curl "http://localhost:8000/api/investigate?namespace=demo-apps&resource_name=broken-nginx"
   ```

Notes:

- The app remains read-only inside the cluster.
- The RBAC in `k8s/rbac.yaml` only grants read access needed for investigation.
- To investigate more namespaces, create additional namespace-scoped Role/RoleBinding pairs for each namespace.

## Frontend

A small Vite + React dashboard lives in `frontend/` and only talks to the backend API.

1. Start the backend first with `make run`.
2. In a second terminal, install the frontend dependencies:

   ```bash
   cd frontend
   npm install
   ```

3. Run the frontend dev server:

   ```bash
   npm run dev
   ```

4. Open `http://localhost:5173` in your browser.

The frontend uses `VITE_API_BASE_URL` and defaults to `http://localhost:8000`.

To test the three demo apps from the UI:

- Use `broken-nginx` for the image pull failure demo
- Use `crashloop-app` for the crash loop demo
- Use `pending-app` for the scheduling failure demo

## Demo Workloads

Create the demo namespace if it does not already exist:

```bash
kubectl create namespace demo-apps
```

Apply the intentionally broken workloads:

```bash
kubectl apply -f broken-nginx.yaml
kubectl apply -f crashloop-app.yaml
kubectl apply -f pending-app.yaml
```

Use these manifests to test the common failure paths:

- `broken-nginx.yaml` for `ImagePullBackOff`
- `crashloop-app.yaml` for `CrashLoopBackOff`
- `pending-app.yaml` for pending or scheduling failures

## Example Curl Commands

Broken image demo:

```bash
curl "http://127.0.0.1:8000/api/investigate?namespace=demo-apps&resource_name=broken-nginx"
```

Crash loop demo:

```bash
curl "http://127.0.0.1:8000/api/investigate?namespace=demo-apps&resource_name=crashloop-app"
```

Pending demo:

```bash
curl "http://127.0.0.1:8000/api/investigate?namespace=demo-apps&resource_name=pending-app"
```

## Example Response

The response keeps the Kubernetes evidence and adds `resource_summary`, `diagnosis.evidence`, and `diagnosis.llm`.

```json
{
  "namespace": "demo-apps",
  "resource_name": "broken-nginx",
  "pods": { "command": ["kubectl", "get", "pods", "-n", "demo-apps"], "returncode": 0, "stdout": "...", "stderr": "" },
  "events": { "command": ["kubectl", "get", "events", "-n", "demo-apps", "--sort-by=.lastTimestamp"], "returncode": 0, "stdout": "...", "stderr": "" },
  "deployment": { "command": ["kubectl", "describe", "deployment", "broken-nginx", "-n", "demo-apps"], "returncode": 0, "stdout": "...", "stderr": "" },
  "services": { "command": ["kubectl", "get", "svc", "-n", "demo-apps"], "returncode": 0, "stdout": "...", "stderr": "" },
  "endpoints": { "command": ["kubectl", "get", "endpoints", "-n", "demo-apps"], "returncode": 0, "stdout": "...", "stderr": "" },
  "replicasets": { "command": ["kubectl", "get", "rs", "-n", "demo-apps"], "returncode": 0, "stdout": "...", "stderr": "" },
  "pod_describes": [
    {
      "pod_name": "broken-nginx-7d8c",
      "command": ["kubectl", "describe", "pod", "broken-nginx-7d8c", "-n", "demo-apps"],
      "returncode": 0,
      "stdout": "...",
      "stderr": ""
    }
  ],
  "pod_logs": [
    {
      "pod_name": "broken-nginx-7d8c",
      "command": ["kubectl", "logs", "broken-nginx-7d8c", "-n", "demo-apps", "--tail=100"],
      "returncode": 1,
      "stdout": "",
      "stderr": "Error from server (BadRequest): container is waiting: ImagePullBackOff"
    }
  ],
  "resource_summary": {
    "namespace": "demo-apps",
    "resource_name": "broken-nginx",
    "detected_pod_names": ["broken-nginx-7d8c"],
    "pod_count": 1,
    "has_logs": false,
    "investigation_timestamp_utc": "2026-07-06T00:00:00Z"
  },
  "diagnosis": {
    "root_cause": "Container image cannot be pulled or does not exist",
    "severity": "High",
    "confidence": 95,
    "suggested_fix": "Recommended fix: a human operator can review the image name and tag in the Deployment, correct the reference if needed, and then verify the rollout.",
    "verification_commands": [
      "kubectl get pods -n demo-apps",
      "kubectl describe deployment broken-nginx -n demo-apps",
      "kubectl rollout status deployment/broken-nginx -n demo-apps"
    ],
    "evidence": [
      "Failed to pull image \"nginx:wrongtag\"",
      "Back-off pulling image \"nginx:wrongtag\""
    ],
    "llm": {
      "enabled": false,
      "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
      "error": "OpenRouter returned 429: model temporarily rate-limited"
    }
  }
}
```

## Safety Notes

- The backend is read-only
- It only gathers evidence and returns recommendations
- It does not apply fixes automatically
- The LLM is constrained to operator-safe wording

## Troubleshooting

### `OPENROUTER_API_KEY` not set

If the key is missing, the LLM section returns a structured error and the Kubernetes investigation still succeeds.

### OpenRouter 401

A 401 usually means the API key is missing, invalid, or revoked. Update the key in `.env` and restart the app.

### OpenRouter 429

A 429 usually means the model is rate-limited. The backend keeps returning the Kubernetes evidence and puts the error under `diagnosis.llm.error`.

### `kubectl` not found

Install `kubectl` and make sure it is on your `PATH`.

### k3s / kubeconfig not reachable

Verify the current context with `kubectl config current-context` and confirm your kubeconfig is pointing at a live cluster or k3s endpoint.

## Useful Make Targets

- `make install`
- `make test`
- `make run`
- `make check`
- `make docker-build`
- `make frontend-install`
- `make frontend-dev`
- `make frontend-build`
- `make k8s-apply`
- `make k8s-status`
- `make k8s-port-forward`
- `make demo-apply`
- `make demo-status`
