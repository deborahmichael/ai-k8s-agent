from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def run_kubectl(args: list[str]) -> CommandResult:
    command = ["kubectl", *args]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
