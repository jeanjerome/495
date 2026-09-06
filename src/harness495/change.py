"""Cas d’usage qui conduit un changement et vérifie son candidat."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from harness495.agent import AgentClient
from harness495.contract import validate_contract
from harness495.controls import ControlRunner
from harness495.errors import ChangeError
from harness495.serialization import canonical_bytes, load_json, sha256_bytes
from harness495.workspace import observe_candidate, validate_repository


def inherited_environment(
    names: list[str],
    *,
    fixed: dict[str, str],
    temporary_home: Path,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    present = sorted(name for name in names if name in os.environ)
    missing = sorted(name for name in names if name not in os.environ)
    environment = {name: os.environ[name] for name in present}
    environment.update(fixed)
    environment.update({"HOME": str(temporary_home), "TMPDIR": str(temporary_home)})
    return environment, {"inherited": present, "missing": missing}


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

    repository, baseline = validate_repository(repository)
    contract = validate_contract(load_json(contract_path.resolve(), "contrat"))
    contract_digest = sha256_bytes(canonical_bytes(contract))
    request_digest = sha256_bytes(request.encode())

    temporary_root = Path(tempfile.gettempdir()).resolve()
    if temporary_root.is_relative_to(repository):
        raise ChangeError(
            "precondition",
            "le répertoire temporaire doit être extérieur au dépôt cible",
        )

    with tempfile.TemporaryDirectory(prefix="495-run-") as directory:
        artifacts = Path(directory)
        temporary_home = artifacts / "home"
        temporary_home.mkdir()
        environment, environment_report = inherited_environment(
            contract["environment"],
            fixed=client_environment,
            temporary_home=temporary_home,
        )
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
            artifacts=artifacts,
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
            "environment": environment_report,
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

        expected_candidate_digest = candidate["digest"]
        all_passed = True
        for check in contract["checks"]:
            check_result = control_runner.run(
                repository=repository,
                check=check,
                environment=environment,
            )
            result["checks"].append(check_result)
            if check_result["status"] != "PASS":
                all_passed = False
            current_candidate = observe_candidate(repository, baseline)
            current_digest = (
                current_candidate["digest"] if current_candidate else None
            )
            if current_digest != expected_candidate_digest:
                result["violations"].append(
                    f"le contrôle {check['name']} a modifié l’état Git visible"
                )
                all_passed = False
                result["candidate_after_checks"] = current_candidate
                break

        result["outcome"] = (
            "candidate_verified" if all_passed else "candidate_failed"
        )
        return result, 0 if all_passed else 1


def error_result(error: ChangeError) -> dict[str, Any]:
    return {
        "error": {"kind": error.kind, "message": str(error)},
        "outcome": "execution_impossible",
        "version": 1,
    }
