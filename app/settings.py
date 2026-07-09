from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_KUBECTL_TIMEOUT_SECONDS = 15
DEFAULT_LOG_TAIL_LINES = 100
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)
DEFAULT_HISTORY_LIMIT = 20
DEFAULT_INSFORGE_HISTORY_TABLE = "investigation_history"


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None
    openrouter_model: str
    kubectl_timeout_seconds: int
    log_tail_lines: int
    cors_origins: tuple[str, ...]
    insforge_enabled: bool
    insforge_api_url: str | None
    insforge_api_key: str | None
    insforge_history_table: str
    history_limit: int


def _read_str_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _read_optional_str_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _read_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _read_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    try:
        parsed = int(value)
    except ValueError:
        return default

    return parsed if parsed > 0 else default


def _read_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    items = tuple(part.strip() for part in value.split(",") if part.strip())
    return items or default


def get_settings() -> Settings:
    return Settings(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
        openrouter_model=_read_str_env("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL),
        kubectl_timeout_seconds=_read_int_env("KUBECTL_TIMEOUT_SECONDS", DEFAULT_KUBECTL_TIMEOUT_SECONDS),
        log_tail_lines=_read_int_env("LOG_TAIL_LINES", DEFAULT_LOG_TAIL_LINES),
        cors_origins=_read_csv_env("CORS_ORIGINS", DEFAULT_CORS_ORIGINS),
        insforge_enabled=_read_bool_env("INSFORGE_ENABLED", False),
        insforge_api_url=_read_optional_str_env("INSFORGE_API_URL"),
        insforge_api_key=_read_optional_str_env("INSFORGE_API_KEY"),
        insforge_history_table=_read_str_env("INSFORGE_HISTORY_TABLE", DEFAULT_INSFORGE_HISTORY_TABLE),
        history_limit=_read_int_env("HISTORY_LIMIT", DEFAULT_HISTORY_LIMIT),
    )