"""macOS Seatbelt backend (``sandbox-exec``): no network, writes confined to the worktree."""

from __future__ import annotations

import platform
import shutil
import tempfile
from pathlib import Path

from four95.core.models import SandboxInfo
from four95.sandbox.base import ExecRequest, Sandbox


def _sb_path(p: Path) -> str:
    return str(p.resolve()).replace('"', '\\"')


def build_profile(req: ExecRequest) -> str:
    lines = ["(version 1)", "(allow default)"]
    if not req.network:
        lines.append("(deny network*)")
    lines.append("(deny file-write*)")
    if req.writable:
        lines.append(f'(allow file-write* (subpath "{_sb_path(req.cwd)}"))')
    scratch = req.scratch_dir or Path(tempfile.gettempdir())
    lines.append(f'(allow file-write* (subpath "{_sb_path(scratch)}"))')
    for extra in ("/private/tmp", "/tmp", "/dev"):
        lines.append(f'(allow file-write* (subpath "{extra}"))')
    lines.append('(allow file-write* (literal "/dev/null"))')
    return "\n".join(lines) + "\n"


class SeatbeltSandbox(Sandbox):
    name = "seatbelt"

    def available(self) -> tuple[bool, str]:
        if platform.system() != "Darwin":
            return False, "seatbelt requires macOS"
        if shutil.which("sandbox-exec") is None:
            return False, "sandbox-exec not found"
        return True, "macOS sandbox-exec"

    def describe(self, req: ExecRequest) -> SandboxInfo:
        return SandboxInfo(
            backend=self.name,
            network="allowed" if req.network else "denied",
            writable_paths=[str(req.cwd)] if req.writable else [],
            detail="macOS Seatbelt profile: file writes limited to the worktree and scratch dirs",
        )

    def wrap(self, req: ExecRequest) -> list[str]:
        return ["sandbox-exec", "-p", build_profile(req), "/bin/bash", "-c", req.command]
