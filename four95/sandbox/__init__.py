"""Sandbox selection."""

from __future__ import annotations

import platform

from four95.core.models import SandboxConfig
from four95.sandbox.base import CommandResult, ExecRequest, Sandbox, run_process
from four95.sandbox.docker import DockerSandbox
from four95.sandbox.seatbelt import SeatbeltSandbox

__all__ = [
    "CommandResult",
    "DockerSandbox",
    "ExecRequest",
    "Sandbox",
    "SeatbeltSandbox",
    "run_process",
    "select_sandbox",
]


def select_sandbox(config: SandboxConfig) -> tuple[Sandbox, list[str]]:
    """Return the sandbox to use plus warnings explaining any fallback."""
    warnings: list[str] = []
    backend = config.backend
    if backend == "docker":
        docker = DockerSandbox(config.docker_image)
        ok, why = docker.available()
        if ok:
            return docker, warnings
        warnings.append(f"docker sandbox unavailable ({why}); falling back")
        backend = "auto"
    if backend == "seatbelt":
        sb = SeatbeltSandbox()
        ok, why = sb.available()
        if ok:
            return sb, warnings
        warnings.append(f"seatbelt sandbox unavailable ({why}); falling back")
        backend = "auto"
    if backend == "auto":
        if platform.system() == "Darwin":
            sb = SeatbeltSandbox()
            ok, _ = sb.available()
            if ok:
                return sb, warnings
        docker = DockerSandbox(config.docker_image)
        ok, _ = docker.available()
        if ok:
            return docker, warnings
        warnings.append(
            "no isolation backend available: commands run on the host without isolation"
        )
        return Sandbox(), warnings
    if backend != "host":
        warnings.append(f"unknown sandbox backend '{backend}', using host")
    return Sandbox(), warnings
