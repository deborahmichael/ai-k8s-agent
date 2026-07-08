from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_KUBECTL_TIMEOUT_SECONDS = 15
DEFAULT_LOG_TAIL_LINES = 100
DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None
    openrouter_model: str
    kubectl_timeout_seconds: int
    log_tail_lines: int
    cors_origins: tuple[str, ...]


def _read_str_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


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
    )
