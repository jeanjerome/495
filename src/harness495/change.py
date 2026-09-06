"""Cas d’usage qui conduit un changement et vérifie son candidat."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness495.agent import AgentClient
from harness495.contract import load_contract
from harness495.controls import ControlRunner
from harness495.environment import prepared_environment
from harness495.errors import ChangeError
from harness495.serialization import sha256_bytes
from harness495.verification import run_checks
from harness495.workspace import (
    observe_candidate,
    repository_root,
    require_clean,
    resolve_baseline,
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
) -> tuple[dict[str, Any], int]:
    """Produit un candidat puis lui applique les contrôles de l’application cible."""

    repository = repository_root(repository)
    baseline, _head = resolve_baseline(repository)
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
        control_runner.validate_profiles(
            repository=repository,
            contract=contract,
            environment=environment,
        )
        agent = agent_client.invoke(
            repository=repository,
            request=request,
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
            "contract_digest": contract_digest,
            "environment": prepared.report,
            "outcome": "agent_failed",
            "request_digest": request_digest,
            "version": 1,
            "violations": [],
        }

        response = agent["response"]
        agent_succeeded = (
            not agent["timed_out"]
            and agent["exit_code"] == 0
            and agent["events_error"] is None
            and agent["response_error"] is None
            and isinstance(response, dict)
            and response["status"] == "completed"
        )
        if not agent_succeeded or candidate is None:
            if agent["timed_out"]:
                result["violations"].append("timeout du client")
            elif agent["exit_code"] != 0:
                result["violations"].append(
                    "code de sortie défavorable du client"
                )
            elif agent["events_error"] is not None:
                result["violations"].append(
                    "flux d’événements du client invalide"
                )
            elif agent["response_error"] is not None:
                result["violations"].append("réponse de l’agent invalide")
            elif isinstance(response, dict) and response.get("status") == "blocked":
                result["violations"].append("agent bloqué")
            if candidate is None:
                result["violations"].append("aucun candidat observé")
            return result, 3

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
        return result, 0 if result["outcome"] == "candidate_verified" else 1


def error_result(error: ChangeError) -> dict[str, Any]:
    return {
        "error": {"kind": error.kind, "message": str(error)},
        "outcome": "execution_impossible",
        "version": 1,
    }
