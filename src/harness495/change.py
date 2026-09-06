"""Cas d’usage qui conduit un changement et vérifie son candidat."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness495.agent import AgentClient, agent_completed, agent_failure_violations
from harness495.contract import AGENT_RESPONSE_SCHEMA, load_contract
from harness495.controls import ControlRunner
from harness495.environment import prepared_environment
from harness495.serialization import sha256_bytes
from harness495.process import OUTPUT_LIMIT_BYTES
from harness495.verification import run_checks, runner_report, validate_controls
from harness495.workspace import (
    observe_candidate,
    repository_root,
    require_clean,
    resolve_baseline,
)


def change_prompt(request: str) -> str:
    return (
        "Réalise la demande ci-dessous dans le dépôt courant. Respecte les instructions "
        "et skills applicables du dépôt. Ne crée aucun commit et ne publie rien. "
        "Ta réponse finale doit respecter le JSON Schema fourni ; elle décrit ton "
        "intervention mais ne décide pas si le candidat est vérifié.\n\n"
        "Demande :\n"
        f"{request.rstrip()}\n"
    )


def run_change(
    *,
    repository: Path,
    contract_path: Path,
    request: str,
    agent_timeout_seconds: int,
    agent_client: AgentClient,
    control_runner: ControlRunner,
    client_environment: dict[str, str],
) -> dict[str, Any]:
    """Produit un candidat puis lui applique les contrôles de l’application cible."""

    repository = repository_root(repository)
    baseline, head = resolve_baseline(repository)
    require_clean(repository)
    contract, contract_digest = load_contract(contract_path)
    request_digest = sha256_bytes(request.encode())

    with prepared_environment(
        contract["environment"], repository=repository, fixed=client_environment
    ) as prepared:
        environment = prepared.variables
        version = agent_client.version(
            repository=repository,
            environment=environment,
        )
        agent_client.validate_ready(
            repository=repository,
            environment=environment,
        )
        runner = runner_report(
            control_runner, repository=repository, environment=environment
        )
        validate_controls(
            repository=repository,
            contract=contract,
            environment=environment,
            control_runner=control_runner,
        )
        agent = agent_client.invoke(
            repository=repository,
            prompt=change_prompt(request),
            response_schema=AGENT_RESPONSE_SCHEMA,
            filesystem="workspace-write",
            environment=environment,
            artifacts=prepared.artifacts,
            timeout_seconds=agent_timeout_seconds,
        )

        candidate = observe_candidate(repository, baseline)
        result: dict[str, Any] = {
            "agent": agent,
            "baseline": baseline,
            "candidate": candidate,
            "checks": [],
            "client_version": version,
            "command": "change",
            "contract_digest": contract_digest,
            "environment": prepared.report,
            "head": head,
            "limitations": [],
            "outcome": "agent_failed",
            "output_limit_bytes": OUTPUT_LIMIT_BYTES,
            "reference": "HEAD",
            "request_digest": request_digest,
            "runner": runner,
            "version": 1,
            "violations": [],
        }

        if not agent_completed(agent) or candidate is None:
            result["violations"].extend(agent_failure_violations(agent))
            if candidate is None:
                result["violations"].append("aucun candidat observé")
            return result

        result.update(
            run_checks(
                repository=repository,
                baseline=baseline,
                candidate=candidate,
                contract=contract,
                environment=environment,
                control_runner=control_runner,
            )
        )
        return result
