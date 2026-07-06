# AI Kubernetes Agent

This project is a small, read-only Kubernetes investigation API.

It looks at a target namespace and resource, gathers live Kubernetes output, inspects related pods, applies a few rule-based checks, and optionally asks OpenRouter for an LLM diagnosis.

## What It Does

- Runs read-only `kubectl` commands against a cluster
- Collects pod, event, and deployment output
- Finds related pods, then collects pod describes and pod logs
- Applies simple rules for common failure patterns
- Sends the gathered text to OpenRouter for an optional LLM diagnosis
- Returns everything in a single JSON response from `/api/investigate`

## Architecture

- `app/main.py` exposes the FastAPI app and the `/api/investigate` endpoint
- `app/k8s_client.py` runs read-only `kubectl` commands with `subprocess`
- `app/investigator.py` combines Kubernetes output, related pod describes/logs, rule-based diagnosis, and LLM output
- `app/openrouter_client.py` calls OpenRouter and converts upstream failures into `diagnosis.llm.error`

The API does not patch, restart, or modify Kubernetes resources.

## Prerequisites

- Python 3.12 or newer
- `kubectl` configured with access to your cluster
- A Kubernetes namespace and resource to inspect
- Optional: an OpenRouter API key for LLM diagnosis

## Local Setup

1. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

   On WSL or macOS/Linux:

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:

   ```bash
   copy .env.example .env
   ```

   Set `OPENROUTER_API_KEY` in `.env` if you want LLM output.

4. Start the API:

   ```bash
   uvicorn app.main:app --reload
   ```

## Demo Workload

The repository includes `broken-nginx.yaml`, which defines a deliberately broken deployment in the `demo-apps` namespace.

1. Create the namespace:

   ```bash
   kubectl create namespace demo-apps
   ```

2. Apply the workload:

   ```bash
   kubectl apply -f broken-nginx.yaml
   ```

The manifest uses `nginx:wrongtag`, so the pod should fail with an image pull problem.

## Example Requests

Investigate the demo workload:

```bash
curl "http://127.0.0.1:8000/api/investigate?namespace=demo-apps&resource_name=broken-nginx"
```

Investigate a different resource:

```bash
curl "http://127.0.0.1:8000/api/investigate?namespace=default&resource_name=my-app"
```

## Example Response

The API also includes `pod_describes` and `pod_logs` arrays for each matching pod.

```json
{
  "namespace": "demo-apps",
  "resource_name": "broken-nginx",
  "pods": {
    "command": ["kubectl", "get", "pods", "-n", "demo-apps"],
    "returncode": 0,
    "stdout": "...",
    "stderr": ""
  },
  "events": {
    "command": ["kubectl", "get", "events", "-n", "demo-apps", "--sort-by=.lastTimestamp"],
    "returncode": 0,
    "stdout": "...",
    "stderr": ""
  },
  "deployment": {
    "command": ["kubectl", "describe", "deployment", "broken-nginx", "-n", "demo-apps"],
    "returncode": 0,
    "stdout": "...",
    "stderr": ""
  },
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
  "diagnosis": {
    "root_cause": "Invalid container image or image tag",
    "severity": "High",
    "confidence": 95,
    "suggested_fix": "Update the deployment to use a valid image tag, then verify rollout status.",
    "verification_commands": [
      "kubectl get pods -n demo-apps",
      "kubectl rollout status deployment/broken-nginx -n demo-apps"
    ],
    "llm": {
      "enabled": false,
      "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
      "error": "OpenRouter returned 429: model temporarily rate-limited"
    }
  }
}
```

## Safety Note

This project is read-only by design.

- It only gathers Kubernetes information
- It does not auto-fix workloads
- It does not restart pods or patch resources
- Any remediation must be done manually by the operator
