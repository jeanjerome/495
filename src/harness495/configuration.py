"""Proposition, validation et enregistrement du contrat d’une application cible."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harness495.agent import AgentClient, agent_completed, agent_failure_violations
from harness495.contract import (
    FILESYSTEM_PROFILES,
    load_contract,
    validate_contract,
    write_contract,
)
from harness495.controls import ControlRunner
from harness495.environment import prepared_environment
from harness495.errors import ChangeError, ConfigurationError
from harness495.serialization import canonical_bytes, load_json, sha256_bytes
from harness495.verification import resolve_commands, validate_controls
from harness495.workspace import observe_candidate, repository_root, resolve_baseline


PROPOSAL_RESPONSE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["completed", "blocked"]},
        "summary": {"type": "string"},
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "command": {"type": "array", "items": {"type": "string"}},
                    "timeout_seconds": {"type": ["integer", "null"]},
                    "filesystem": {
                        "type": "string",
                        "enum": sorted(FILESYSTEM_PROFILES),
                    },
                    "evidence": {"type": "string"},
                },
                "required": ["name", "command", "timeout_seconds", "filesystem", "evidence"],
                "additionalProperties": False,
            },
        },
        "environment": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "status",
        "summary",
        "checks",
        "environment",
        "questions",
        "limitations",
    ],
    "additionalProperties": False,
}

PROPOSAL_REMINDER = (
    "la proposition est produite par un agent : elle n’atteste ni la pertinence "
    "ni l’exécutabilité des contrôles ; l’utilisateur la relit, la corrige au "
    "besoin, puis l’enregistre explicitement avec configure write"
)


def proposal_prompt() -> str:
    return (
        "Inspecte le dépôt courant en lecture seule pour proposer la configuration "
        "des contrôles que 495 exécutera sur ses candidats. Ne modifie aucun fichier, "
        "ne crée aucun commit et n’exécute pas les contrôles toi-même.\n\n"
        "Ne propose que des commandes attestées par le dépôt lui-même : scripts, "
        "cibles de Makefile, manifestes de paquets, configuration d’intégration "
        "continue, instructions du README ou du fichier d’instructions du dépôt. "
        "Pour chaque contrôle, `evidence` cite le fichier ou la convention qui "
        "l’atteste. Un choix que le dépôt ne permet pas de trancher, par exemple "
        "entre deux gestionnaires de paquets, devient une entrée de `questions` ; "
        "n’invente jamais une valeur.\n\n"
        "Chaque contrôle a un `name` unique, une `command` sous forme de liste "
        "d’arguments exécutée sans shell depuis la racine du dépôt, un "
        "`timeout_seconds` entier positif seulement lorsque le dépôt l’atteste, "
        "par exemple dans sa configuration d’intégration continue, et `null` "
        "sinon, ainsi qu’un `filesystem` qui vaut `read-only` "
        "sauf lorsque tu constates que la commande écrit dans l’espace de travail, "
        "auquel cas il vaut `workspace-write`. `environment` énumère les seules "
        "variables ordinaires nécessaires aux contrôles, par exemple PATH ou LANG ; "
        "HOME, TMPDIR, CODEX_HOME et tout nom évoquant une clé, un secret ou un "
        "jeton sont refusés. Si aucun contrôle n’est attesté, rends `checks` vide "
        "et explique dans `questions` ce qui manque.\n\n"
        "Ta réponse finale doit respecter le JSON Schema fourni. Elle est une "
        "proposition relue par une personne, pas une configuration enregistrée.\n"
    )


def contract_from_response(response: dict[str, Any]) -> dict[str, Any]:
    """Construit le contrat proposé à partir des champs `checks` et `environment`."""

    return {
        "checks": [
            {
                "command": list(check["command"]),
                "filesystem": check["filesystem"],
                "name": check["name"],
                "timeout_seconds": check["timeout_seconds"],
            }
            for check in response["checks"]
        ],
        "environment": list(response["environment"]),
        "version": 1,
    }


def apply_timeout(
    contract: dict[str, Any], timeout_seconds: int | None
) -> str | None:
    """Complète les contrôles sans timeout avec la valeur fournie par l’utilisateur.

    Retourne la limitation à rapporter, ou `None` lorsque tous les contrôles
    portaient déjà un timeout attesté. Sans valeur fournie, les contrôles
    restent sans borne de durée : ni l’agent ni 495 n’inventent ce délai.
    """

    unbounded = [
        check["name"] for check in contract["checks"] if check["timeout_seconds"] is None
    ]
    if not unbounded:
        return None
    names = ", ".join(unbounded)
    if timeout_seconds is None:
        return (
            f"aucun timeout n’est attesté par le dépôt pour {names} et aucune "
            "valeur n’a été passée avec --timeout-seconds : ces contrôles ne sont "
            "pas bornés dans le temps"
        )
    for check in contract["checks"]:
        if check["timeout_seconds"] is None:
            check["timeout_seconds"] = timeout_seconds
    return (
        f"le timeout de {names} vaut {timeout_seconds} s, valeur passée avec "
        "--timeout-seconds et non attestée par le dépôt"
    )


def propose_configuration(
    *,
    repository: Path,
    agent_client: AgentClient,
    agent_timeout_seconds: int,
    client_environment: dict[str, str],
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Fait inspecter le dépôt par l’agent en lecture seule et restitue une proposition.

    Rien n’est écrit dans le dépôt. Le candidat est observé avant et après
    l’inspection : une différence est une violation, car un agent qui écrit
    malgré la lecture seule n’est pas digne de confiance pour proposer une
    configuration. La proposition n’est jamais une preuve de pertinence.
    """

    repository = repository_root(repository)
    baseline, _ = resolve_baseline(repository)

    with prepared_environment(
        ["PATH"], repository=repository, fixed=client_environment
    ) as prepared:
        environment = prepared.variables
        version = agent_client.version(repository=repository, environment=environment)
        agent_client.validate_ready(repository=repository, environment=environment)

        before = observe_candidate(repository, baseline)
        agent = agent_client.invoke(
            repository=repository,
            prompt=proposal_prompt(),
            response_schema=PROPOSAL_RESPONSE_SCHEMA,
            filesystem="read-only",
            environment=environment,
            artifacts=prepared.artifacts,
            timeout_seconds=agent_timeout_seconds,
        )
        after = observe_candidate(repository, baseline)

        result: dict[str, Any] = {
            "agent": agent,
            "baseline": baseline,
            "client_version": version,
            "command": "configure propose",
            "commands": {},
            "contract": None,
            "environment": prepared.report,
            "evidence": {},
            "limitations": [PROPOSAL_REMINDER],
            "outcome": "agent_failed",
            "questions": [],
            "version": 1,
            "violations": [],
        }

        before_digest = before["digest"] if before else None
        after_digest = after["digest"] if after else None
        if before_digest != after_digest:
            result["violations"].append(
                "l’agent a modifié le dépôt pendant l’inspection en lecture seule"
            )
        response = agent["response"]
        if isinstance(response, dict):
            result["questions"] = list(response.get("questions", []))
        if not agent_completed(agent):
            result["violations"].extend(agent_failure_violations(agent))
        if result["violations"]:
            return result

        assert isinstance(response, dict)
        if not response["checks"]:
            result["outcome"] = "no_checks_detected"
            result["limitations"].append(
                "aucun contrôle attesté par le dépôt n’a été détecté ; le contrat "
                "peut être écrit à la main puis contrôlé avec configure validate"
            )
            return result

        contract = contract_from_response(response)
        timeout_limitation = apply_timeout(contract, timeout_seconds)
        if timeout_limitation is not None:
            result["limitations"].append(timeout_limitation)
        try:
            validate_contract(contract)
        except ConfigurationError as error:
            result["violations"].append(f"proposition non conforme au contrat : {error}")
            return result

        result["contract"] = contract
        result["evidence"] = {
            check["name"]: check["evidence"] for check in response["checks"]
        }
        result["commands"] = resolve_commands(
            contract, repository=repository, environment=environment
        )
        result["outcome"] = "proposal_ready"
        return result


def _relative_contract_path(path: Path, repository: Path) -> str:
    return Path(os.path.relpath(path.resolve(), repository)).as_posix()


def _validated_document(
    *,
    command: str,
    repository: Path,
    contract_path: Path,
    contract: dict[str, Any],
    contract_digest: str,
    control_runner: ControlRunner,
) -> dict[str, Any]:
    with prepared_environment(
        contract["environment"], repository=repository, fixed={}
    ) as prepared:
        runner_version = control_runner.version(
            repository=repository, environment=prepared.variables
        )
        commands = validate_controls(
            repository=repository,
            contract=contract,
            environment=prepared.variables,
            control_runner=control_runner,
        )
        return {
            "command": command,
            "commands": commands,
            "contract_digest": contract_digest,
            "contract_path": _relative_contract_path(contract_path, repository),
            "environment": prepared.report,
            "limitations": [],
            "runner": {"name": "codex-sandbox", "version": runner_version},
            "version": 1,
        }


def validate_configuration(
    *,
    repository: Path,
    contract_path: Path,
    control_runner: ControlRunner,
) -> dict[str, Any]:
    """Contrôle un contrat présent : format, exécutables résolus, profils sondés."""

    repository = repository_root(repository)
    contract, contract_digest = load_contract(contract_path)
    result = _validated_document(
        command="configure validate",
        repository=repository,
        contract_path=contract_path,
        contract=contract,
        contract_digest=contract_digest,
        control_runner=control_runner,
    )
    result["outcome"] = "configuration_valid"
    return result


def load_proposal(path: Path) -> dict[str, Any]:
    """Extrait le contrat d’une proposition produite par `configure propose`."""

    value = load_json(path, "proposition")
    if (
        not isinstance(value, dict)
        or value.get("command") != "configure propose"
        or value.get("version") != 1
        or not isinstance(value.get("contract"), dict)
    ):
        raise ChangeError(
            "precondition",
            f"le fichier n’est pas une proposition de configure propose "
            f"avec un contrat : {path}",
        )
    return value["contract"]


def write_configuration(
    *,
    repository: Path,
    proposal_path: Path,
    contract_path: Path,
    overwrite: bool,
    control_runner: ControlRunner,
) -> dict[str, Any]:
    """Valide le contrat d’une proposition relue puis l’enregistre dans le dépôt."""

    repository = repository_root(repository)
    target = contract_path.resolve()
    if not target.is_relative_to(repository):
        raise ChangeError(
            "precondition", f"le contrat doit être situé dans le dépôt : {target}"
        )
    if target.exists() and not overwrite:
        raise ChangeError(
            "precondition",
            f"contrat existant, --overwrite requis pour le remplacer : {target}",
        )
    contract = validate_contract(load_proposal(proposal_path))
    contract_digest = sha256_bytes(canonical_bytes(contract))
    result = _validated_document(
        command="configure write",
        repository=repository,
        contract_path=target,
        contract=contract,
        contract_digest=contract_digest,
        control_runner=control_runner,
    )
    result["overwritten"] = write_contract(
        target, contract, repository=repository, overwrite=overwrite
    )
    result["outcome"] = "configuration_written"
    return result
