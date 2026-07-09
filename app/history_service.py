from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import requests

from app.settings import get_settings


logger = logging.getLogger(__name__)

HISTORY_REQUEST_TIMEOUT_SECONDS = 10
_LOCAL_HISTORY_CACHE: dict[str, dict[str, object]] = {}
_LAST_HISTORY_ERROR: str | None = None


def _set_last_error(message: str | None) -> None:
    global _LAST_HISTORY_ERROR
    _LAST_HISTORY_ERROR = message


def get_history_error() -> str | None:
    return _LAST_HISTORY_ERROR


def _settings_ready() -> tuple[bool, str | None]:
    settings = get_settings()
    if not settings.insforge_enabled:
        return False, None
    if not settings.insforge_api_url or not settings.insforge_api_key or not settings.insforge_history_table:
        return False, None
    return True, None


def is_history_enabled() -> bool:
    enabled, _ = _settings_ready()
    return enabled


def _now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _build_compact_record(result: dict[str, object]) -> dict[str, object]:
    diagnosis = result.get("diagnosis") if isinstance(result.get("diagnosis"), dict) else {}
    resource_summary = result.get("resource_summary") if isinstance(result.get("resource_summary"), dict) else {}

    record: dict[str, object] = {
        "history_id": uuid.uuid4().hex,
        "namespace": str(result.get("namespace", "")),
        "resource_name": str(result.get("resource_name", "")),
        "root_cause": str(diagnosis.get("root_cause", "")),
        "severity": str(diagnosis.get("severity", "Unknown")),
        "confidence": diagnosis.get("confidence", 0),
        "suggested_fix": str(diagnosis.get("suggested_fix", "")),
        "evidence": _coerce_list(diagnosis.get("evidence")),
        "verification_commands": _coerce_list(diagnosis.get("verification_commands")),
        "llm_enabled": bool(isinstance(diagnosis.get("llm"), dict) and diagnosis["llm"].get("enabled")),
        "created_at": _now_utc(),
        "compact_result_json": "",
        "resource_summary": {
            "namespace": resource_summary.get("namespace", result.get("namespace", "")),
            "resource_name": resource_summary.get("resource_name", result.get("resource_name", "")),
            "detected_pod_names": _coerce_list(resource_summary.get("detected_pod_names")),
            "pod_count": resource_summary.get("pod_count", 0),
            "has_logs": bool(resource_summary.get("has_logs", False)),
            "investigation_timestamp_utc": resource_summary.get("investigation_timestamp_utc", _now_utc()),
        },
    }
    record["compact_result_json"] = json.dumps(record, sort_keys=True)
    return record


def _service_headers(settings: object) -> dict[str, str]:
    api_key = getattr(settings, "insforge_api_key", None)
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _service_url(settings: object) -> str:
    base_url = str(getattr(settings, "insforge_api_url", "") or "").rstrip("/")
    table = str(getattr(settings, "insforge_history_table", "") or "")
    return f"{base_url}/records?table={table}"


def _service_item_url(settings: object, history_id: str) -> str:
    base_url = str(getattr(settings, "insforge_api_url", "") or "").rstrip("/")
    table = str(getattr(settings, "insforge_history_table", "") or "")
    return f"{base_url}/records/{history_id}?table={table}"


def _normalize_history_item(item: object) -> dict[str, object] | None:
    if not isinstance(item, dict):
        return None

    normalized = dict(item)
    if not normalized.get("history_id"):
        normalized["history_id"] = str(normalized.get("id") or normalized.get("record_id") or "")

    compact_json = normalized.get("compact_result_json")
    if isinstance(compact_json, str) and compact_json.strip():
        try:
            normalized["compact_result"] = json.loads(compact_json)
        except ValueError:
            normalized["compact_result"] = None
    return normalized


def _remember_history_item(item: dict[str, object]) -> None:
    history_id = str(item.get("history_id") or "")
    if history_id:
        _LOCAL_HISTORY_CACHE[history_id] = item


def _request_failed(prefix: str, exc: Exception) -> None:
    message = f"{prefix}: {exc.__class__.__name__}"
    logger.warning(message)
    _set_last_error(message)


def save_investigation(result: dict) -> str | None:
    _set_last_error(None)
    settings = get_settings()
    if not settings.insforge_enabled:
        return None
    if not settings.insforge_api_url or not settings.insforge_api_key or not settings.insforge_history_table:
        return None

    record = _build_compact_record(result)
    payload = {
        "table": settings.insforge_history_table,
        "record": record,
    }

    try:
        response = requests.post(
            _service_url(settings),
            headers=_service_headers(settings),
            json=payload,
            timeout=HISTORY_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        _request_failed("InsForge history save failed", exc)
        return None

    if response.status_code not in {200, 201, 202}:
        _request_failed(f"InsForge history save failed with status {response.status_code}", Exception(response.text.strip() or "request failed"))
        return None

    _remember_history_item(record)
    return str(record["history_id"])


def _parse_items(payload: object) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    candidates: object = payload
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            candidates = payload["items"]
        elif isinstance(payload.get("records"), list):
            candidates = payload["records"]
        elif isinstance(payload.get("data"), list):
            candidates = payload["data"]

    if isinstance(candidates, list):
        for entry in candidates:
            normalized = _normalize_history_item(entry)
            if normalized is not None:
                items.append(normalized)
    return items


def list_history(limit: int = 20) -> list[dict[str, object]]:
    _set_last_error(None)
    settings = get_settings()
    if not settings.insforge_enabled:
        return []
    if not settings.insforge_api_url or not settings.insforge_api_key or not settings.insforge_history_table:
        return []

    limit = limit if limit > 0 else 20
    try:
        response = requests.get(
            _service_url(settings),
            headers=_service_headers(settings),
            params={"limit": limit},
            timeout=HISTORY_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            _request_failed(
                f"InsForge history list failed with status {response.status_code}",
                Exception(response.text.strip() or "request failed"),
            )
            return list(_LOCAL_HISTORY_CACHE.values())[:limit]

        payload = response.json()
        items = _parse_items(payload)
        for item in items:
            _remember_history_item(item)
        return items[:limit]
    except (requests.RequestException, ValueError) as exc:
        _request_failed("InsForge history list failed", exc)
        cached = sorted(
            _LOCAL_HISTORY_CACHE.values(),
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )
        return cached[:limit]


def get_history_item(history_id: str) -> dict[str, object] | None:
    _set_last_error(None)
    if not history_id.strip():
        return None

    settings = get_settings()
    if not settings.insforge_enabled:
        return None
    if not settings.insforge_api_url or not settings.insforge_api_key or not settings.insforge_history_table:
        return None

    cached = _LOCAL_HISTORY_CACHE.get(history_id)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            _service_item_url(settings, history_id),
            headers=_service_headers(settings),
            timeout=HISTORY_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            _request_failed(
                f"InsForge history item lookup failed with status {response.status_code}",
                Exception(response.text.strip() or "request failed"),
            )
            return None

        payload = response.json()
        item = _normalize_history_item(payload)
        if item is not None:
            _remember_history_item(item)
        return item
    except (requests.RequestException, ValueError) as exc:
        _request_failed("InsForge history item lookup failed", exc)
        return _LOCAL_HISTORY_CACHE.get(history_id)