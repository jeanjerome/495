"""Assemblage des composants disponibles pour les interfaces utilisateur."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness495.change import run_change
from harness495.codex import CodexAgentClient, find_codex, validate_codex_home
from harness495.controls import CodexSandboxControlRunner
from harness495.verification import verify_candidate


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


def verify_with_codex_sandbox(
    *,
    repository: Path,
    contract_path: Path,
    reference: str = "HEAD",
    executable: Path | None = None,
) -> dict[str, Any]:
    """Vérifie un candidat déjà présent avec `codex sandbox`, sans authentification.

    Le runner reçoit un CODEX_HOME jetable sous le HOME temporaire ; aucun
    `CODEX_HOME` utilisateur ni `codex login status` n’intervient.
    """

    executable = executable or find_codex()
    return verify_candidate(
        repository=repository,
        contract_path=contract_path,
        reference=reference,
        control_runner=CodexSandboxControlRunner(executable),
    )
