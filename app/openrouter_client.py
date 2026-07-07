from __future__ import annotations

import requests

from app.settings import get_settings


OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_SYSTEM_PROMPT = (
    "You are a read-only Kubernetes incident assistant. "
    "Never say or imply you will apply, execute, fix, update, change, patch, restart, or modify the cluster yourself. "
    "Only recommend commands for a human operator to review and run. "
    "Respond with these sections in order: Issue, Evidence, Likely root cause, Recommended fix, Commands a human operator can run, Verification steps, Risk / caution, Do not apply automatically. "
    "Use wording like 'Recommended fix', 'A human operator can run', 'To verify', and 'Do not apply automatically'. "
    "Avoid wording like 'I'll fix this', 'I will update', or 'I can apply'. "
    "Keep the response concise and clearly focused on operator-guided remediation."
)


def _format_openrouter_error(status_code: int, response_text: str | None = None) -> str:
    if status_code == 401:
        return "OpenRouter returned 401: unauthorized"
    if status_code == 429:
        return "OpenRouter returned 429: model temporarily rate-limited"
    if status_code == 500:
        if response_text:
            return f"OpenRouter returned 500: {response_text}"
        return "OpenRouter returned 500: internal server error"

    if response_text:
        return f"OpenRouter returned {status_code}: {response_text}"
    return f"OpenRouter returned {status_code}"


def _extract_response_text(response: requests.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        if isinstance(error, str) and error.strip():
            return error.strip()

        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()

    if isinstance(payload, str) and payload.strip():
        return payload.strip()

    return response.text.strip() or None


def analyze_with_openrouter(prompt: str) -> dict[str, object]:
    settings = get_settings()
    api_key = settings.openrouter_api_key
    model = settings.openrouter_model

    if not api_key:
        return {
            "enabled": False,
            "model": model,
            "error": "OPENROUTER_API_KEY is not set",
        }

    try:
        response = requests.post(
            OPENROUTER_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": OPENROUTER_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            },
            timeout=60,
        )
    except requests.RequestException as exc:
        return {
            "enabled": False,
            "model": model,
            "error": f"OpenRouter request failed: {exc}",
        }

    if response.status_code != 200:
        response_text = _extract_response_text(response)
        return {
            "enabled": False,
            "model": model,
            "error": _format_openrouter_error(response.status_code, response_text),
        }

    try:
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        return {
            "enabled": False,
            "model": model,
            "error": f"OpenRouter returned invalid response: {exc}",
        }

    return {
        "enabled": True,
        "model": model,
        "content": content,
    }
