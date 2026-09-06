"""Exécution bornée des processus enfants."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from harness495.errors import ChangeError


def terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def execute_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int | None,
    stdin: str | None = None,
) -> dict[str, Any]:
    """Exécute une commande sans shell ; `timeout_seconds` à `None` ne borne pas sa durée."""

    started = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as error:
        raise ChangeError(
            "process", f"impossible de lancer {command[0]} : {error}"
        ) from error

    timed_out = False
    try:
        stdout, stderr = process.communicate(input=stdin, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_process_group(process)
        stdout, stderr = process.communicate()

    return {
        "command": command,
        "duration_seconds": round(time.monotonic() - started, 6),
        "exit_code": None if timed_out else process.returncode,
        "stderr": stderr,
        "stdout": stdout,
        "timed_out": timed_out,
    }
