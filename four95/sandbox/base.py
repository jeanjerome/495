"""Command execution with bounded time and, when available, host and network isolation."""

from __future__ import annotations

import contextlib
import os
import shlex
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from four95.core.models import SandboxInfo

MAX_CAPTURE = 2_000_000


@dataclass
class CommandResult:
    command: str
    exit_code: int | None
    output: str
    duration_s: float
    timed_out: bool = False
    interrupted: bool = False
    error: str = ""
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.interrupted


@dataclass
class ExecRequest:
    command: str
    cwd: Path
    timeout_s: int
    writable: bool = True
    network: bool = False
    env: dict[str, str] = field(default_factory=dict)
    scratch_dir: Path | None = None
    stop_check: Callable[[], bool] | None = None


class Sandbox:
    """Base class: run a shell command with a timeout, killing the whole process group."""

    name = "host"

    def describe(self, req: ExecRequest) -> SandboxInfo:
        return SandboxInfo(
            backend=self.name,
            network="allowed (no isolation)" if req.network else "not isolated",
            writable_paths=[str(req.cwd)] if req.writable else [],
            detail="no isolation: commands run directly on the host with a timeout only",
        )

    def wrap(self, req: ExecRequest) -> list[str]:
        return ["/bin/bash", "-c", req.command]

    def available(self) -> tuple[bool, str]:
        return True, "host execution"

    def run(self, req: ExecRequest) -> CommandResult:
        argv = self.wrap(req)
        env = os.environ.copy()
        env.update(req.env)
        env.setdefault("PAGER", "cat")
        env.setdefault("GIT_PAGER", "cat")
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("NO_COLOR", "1")
        return run_process(argv, req.cwd, req.timeout_s, env, req.stop_check, req.command)


def run_process(
    argv: list[str],
    cwd: Path,
    timeout_s: int,
    env: dict[str, str] | None,
    stop_check: Callable[[], bool] | None = None,
    display_command: str | None = None,
    stdin_text: str | None = None,
) -> CommandResult:
    """Run ``argv`` in its own session; kill the process group on timeout or stop request."""
    start = time.monotonic()
    display = display_command or shlex.join(argv)
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        return CommandResult(display, 127, "", 0.0, error=f"cannot start process: {exc}")

    chunks: list[bytes] = []
    size = 0
    truncated = False

    def reader() -> None:
        nonlocal size, truncated
        assert proc.stdout is not None
        for chunk in iter(lambda: proc.stdout.read(65536), b""):  # type: ignore[union-attr]
            if size < MAX_CAPTURE:
                chunks.append(chunk)
                size += len(chunk)
            else:
                truncated = True

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    if stdin_text is not None and proc.stdin is not None:
        try:
            proc.stdin.write(stdin_text.encode("utf-8"))
        except BrokenPipeError:
            pass
        finally:
            with contextlib.suppress(OSError):
                proc.stdin.close()

    timed_out = False
    interrupted = False
    deadline = start + timeout_s
    while True:
        try:
            proc.wait(timeout=0.25)
            break
        except subprocess.TimeoutExpired:
            pass
        if time.monotonic() > deadline:
            timed_out = True
            _kill_group(proc)
            break
        if stop_check is not None and stop_check():
            interrupted = True
            _kill_group(proc)
            break
    t.join(timeout=5)
    output = b"".join(chunks).decode("utf-8", errors="replace")
    if truncated:
        output += "\n[output truncated by 495]\n"
    return CommandResult(
        command=display,
        exit_code=proc.returncode if not (timed_out or interrupted) else None,
        output=output,
        duration_s=round(time.monotonic() - start, 3),
        timed_out=timed_out,
        interrupted=interrupted,
        truncated=truncated,
    )


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        proc.terminate()
    try:
        proc.wait(timeout=3)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=3)
