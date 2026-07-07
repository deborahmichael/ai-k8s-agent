from __future__ import annotations

import subprocess
from dataclasses import dataclass

from app.settings import get_settings


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def _normalize_output(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def run_kubectl(args: list[str]) -> CommandResult:
    settings = get_settings()
    command = ["kubectl", *args]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=settings.kubectl_timeout_seconds,
        )
    except FileNotFoundError as exc:
        return CommandResult(
            command=command,
            returncode=127,
            stdout="",
            stderr=f"kubectl not found: {exc}",
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _normalize_output(exc.stdout)
        stderr = _normalize_output(exc.stderr).strip()
        timeout_message = f"kubectl timed out after {settings.kubectl_timeout_seconds} seconds"
        if stderr:
            timeout_message = f"{timeout_message}: {stderr}"
        return CommandResult(
            command=command,
            returncode=124,
            stdout=stdout,
            stderr=timeout_message,
        )

    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
