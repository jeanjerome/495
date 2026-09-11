"""Docker backend: ``--network none``, the worktree bind-mounted, nothing else from the host."""

from __future__ import annotations

import shutil
import subprocess

from harness495.core.models import SandboxInfo
from harness495.sandbox.base import ExecRequest, Sandbox


class DockerSandbox(Sandbox):
    name = "docker"

    def __init__(self, image: str, executable: str = "docker") -> None:
        self.image = image
        self.executable = executable

    def available(self) -> tuple[bool, str]:
        exe = shutil.which(self.executable)
        if exe is None:
            return False, f"{self.executable} not found"
        try:
            proc = subprocess.run(
                [exe, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"docker not reachable: {exc}"
        if proc.returncode != 0:
            return False, f"docker daemon not reachable: {proc.stderr.strip()[:200]}"
        return True, f"docker server {proc.stdout.strip()} image {self.image}"

    def describe(self, req: ExecRequest) -> SandboxInfo:
        return SandboxInfo(
            backend=self.name,
            network="allowed" if req.network else "denied",
            writable_paths=[str(req.cwd)] if req.writable else [],
            detail=f"docker image {self.image}, worktree mounted at /work"
            + (" read-only" if not req.writable else ""),
        )

    def wrap(self, req: ExecRequest) -> list[str]:
        mount = f"{req.cwd.resolve()}:/work" + ("" if req.writable else ":ro")
        argv = [
            self.executable,
            "run",
            "--rm",
            "-i",
            "--network",
            "bridge" if req.network else "none",
        ]
        argv += ["-v", mount, "-w", "/work"]
        for k, v in req.env.items():
            argv += ["-e", f"{k}={v}"]
        argv += [self.image, "/bin/sh", "-c", req.command]
        return argv
