"""Assemblage des composants disponibles pour les interfaces utilisateur."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness495.change import run_change
from harness495.codex import CodexAgentClient, find_codex, validate_codex_home
from harness495.controls import CodexSandboxControlRunner


def run_codex_change(
    *,
    repository: Path,
    contract_path: Path,
    request: str,
    codex_home: Path,
    agent_timeout_seconds: int,
    executable: Path | None = None,
) -> tuple[dict[str, Any], int]:
    """Assemble le premier parcours avec les capacités fournies par Codex CLI."""

    repository = repository.resolve()
    codex_home = validate_codex_home(codex_home, repository)
    executable = executable or find_codex()
    return run_change(
        repository=repository,
        contract_path=contract_path,
        request=request,
        agent_timeout_seconds=agent_timeout_seconds,
        agent_client=CodexAgentClient(executable),
        control_runner=CodexSandboxControlRunner(executable),
        client_environment={"CODEX_HOME": str(codex_home)},
    )
