"""Interface et adaptation des contrôles appliqués au candidat."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from harness495.contract import FILESYSTEM_PROFILES
from harness495.errors import ChangeError
from harness495.process import execute_process


class ControlRunner(Protocol):
    """Capacités requises pour exécuter les feedbacks de l’application cible."""

    def validate_profiles(
        self,
        *,
        repository: Path,
        contract: dict[str, Any],
        environment: dict[str, str],
    ) -> None: ...

    def run(
        self,
        *,
        repository: Path,
        check: dict[str, Any],
        environment: dict[str, str],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CodexSandboxControlRunner:
    """Exécute les contrôles avec les profils sandbox fournis par Codex CLI."""

    executable: Path

    def validate_profiles(
        self,
        *,
        repository: Path,
        contract: dict[str, Any],
        environment: dict[str, str],
    ) -> None:
        for filesystem in sorted(
            {check["filesystem"] for check in contract["checks"]}
        ):
            probe = {
                "command": [sys.executable, "-c", "pass"],
                "filesystem": filesystem,
                "name": f"sandbox-{filesystem}",
                "timeout_seconds": 10,
            }
            result = self.run(
                repository=repository,
                check=probe,
                environment=environment,
            )
            if result["status"] != "PASS":
                diagnostic = result["stderr"].strip() or result["stdout"].strip()
                raise ChangeError(
                    "precondition",
                    f"sandbox {filesystem} indisponible : "
                    f"{diagnostic or 'échec sans diagnostic'}",
                )

    def run(
        self,
        *,
        repository: Path,
        check: dict[str, Any],
        environment: dict[str, str],
    ) -> dict[str, Any]:
        profile = FILESYSTEM_PROFILES[check["filesystem"]]
        sandbox_environment = environment.copy()
        sandbox_home = Path(environment["HOME"]) / "codex-sandbox"
        sandbox_home.mkdir(exist_ok=True)
        sandbox_environment["CODEX_HOME"] = str(sandbox_home)
        command = [
            str(self.executable),
            "sandbox",
            "-P",
            profile,
            "--sandbox-state-disable-network",
            "-C",
            str(repository),
            "--",
            *check["command"],
        ]
        process = execute_process(
            command,
            cwd=repository,
            environment=sandbox_environment,
            timeout_seconds=check["timeout_seconds"],
        )
        return {
            "command": check["command"],
            "duration_seconds": process["duration_seconds"],
            "exit_code": process["exit_code"],
            "name": check["name"],
            "sandbox": {
                "filesystem": check["filesystem"],
                "network": "disabled",
            },
            "status": "PASS"
            if process["exit_code"] == 0 and not process["timed_out"]
            else "FAIL",
            "stderr": process["stderr"],
            "stdout": process["stdout"],
            "timed_out": process["timed_out"],
        }
