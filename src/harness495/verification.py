"""Vérification d’un candidat Git par les contrôles de l’application cible."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from harness495.contract import load_contract
from harness495.controls import ControlRunner
from harness495.environment import prepared_environment
from harness495.errors import ChangeError
from harness495.workspace import observe_candidate, repository_root, resolve_baseline


def resolve_executable(
    command: list[str], *, repository: Path, environment: dict[str, str]
) -> str | None:
    """Localise l’exécutable d’une commande de contrôle, ou `None` s’il est introuvable.

    Un premier argument contenant un séparateur de chemin est résolu par rapport
    à la racine du dépôt et doit désigner un fichier exécutable. Sinon il est
    cherché dans le `PATH` de l’environnement filtré, ou dans `os.defpath` quand
    le contrat ne transmet pas `PATH`. Cette résolution est une précondition de
    495 ; elle ne prouve pas que `codex sandbox` pourra lancer la commande.
    """

    first = command[0]
    if os.sep in first or (os.altsep and os.altsep in first):
        path = (repository / first).resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        return None
    located = shutil.which(first, path=environment.get("PATH", os.defpath))
    return None if located is None else str(Path(located).resolve())


def resolve_commands(
    contract: dict[str, Any], *, repository: Path, environment: dict[str, str]
) -> dict[str, str | None]:
    """Associe chaque nom de contrôle à son exécutable résolu, ou à `None`."""

    return {
        check["name"]: resolve_executable(
            check["command"], repository=repository, environment=environment
        )
        for check in contract["checks"]
    }


def validate_controls(
    *,
    repository: Path,
    contract: dict[str, Any],
    environment: dict[str, str],
    control_runner: ControlRunner,
) -> dict[str, str]:
    """Applique les préconditions des contrôles : exécutables présents, profils sondés.

    Un exécutable introuvable ou une sandbox indisponible rend l’exécution
    impossible avant tout contrôle, afin qu’un outil absent ne soit jamais
    présenté comme un candidat défavorable.
    """

    commands = resolve_commands(contract, repository=repository, environment=environment)
    missing = sorted(name for name, path in commands.items() if path is None)
    if missing:
        details = "; ".join(
            f"{check['name']} : {check['command'][0]}"
            for check in contract["checks"]
            if check["name"] in missing
        )
        raise ChangeError(
            "precondition", f"exécutable de contrôle introuvable : {details}"
        )
    control_runner.validate_profiles(
        repository=repository, contract=contract, environment=environment
    )
    return {name: path for name, path in commands.items() if path is not None}


def run_checks(
    *,
    repository: Path,
    baseline: str,
    candidate: dict[str, Any],
    contract: dict[str, Any],
    environment: dict[str, str],
    control_runner: ControlRunner,
) -> dict[str, Any]:
    """Exécute chaque contrôle une fois, dans l’ordre déclaré, sur le candidat observé.

    Après chaque contrôle, le candidat est observé de nouveau. Un digest
    différent signifie que le contrôle a modifié l’état Git visible : la suite
    est interrompue et l’état constaté est rapporté, car les contrôles suivants
    porteraient sur un candidat autre que celui identifié.
    """

    result: dict[str, Any] = {"checks": [], "violations": []}
    expected_digest = candidate["digest"]
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
        current_digest = current_candidate["digest"] if current_candidate else None
        if current_digest != expected_digest:
            result["violations"].append(
                f"le contrôle {check['name']} a modifié l’état Git visible"
            )
            all_passed = False
            result["candidate_after_checks"] = current_candidate
            break
    result["outcome"] = "candidate_verified" if all_passed else "candidate_failed"
    return result


def verify_candidate(
    *,
    repository: Path,
    contract_path: Path,
    reference: str = "HEAD",
    control_runner: ControlRunner,
) -> dict[str, Any]:
    """Vérifie l’écart entre l’arbre de travail et une référence Git, sans agent.

    Un dépôt modifié est accepté : c’est cet écart qui constitue le candidat.
    Les préconditions du contrat, des exécutables et des profils sandbox sont
    appliquées avant l’observation, de sorte qu’une configuration invalide, un
    outil absent ou une sandbox indisponible soit rapporté même lorsqu’il n’y a
    rien à vérifier.
    """

    repository = repository_root(repository)
    baseline, head = resolve_baseline(repository, reference)
    contract, contract_digest = load_contract(contract_path)

    with prepared_environment(
        contract["environment"], repository=repository, fixed={}
    ) as prepared:
        validate_controls(
            repository=repository,
            contract=contract,
            environment=prepared.variables,
            control_runner=control_runner,
        )
        candidate = observe_candidate(repository, baseline)
        result: dict[str, Any] = {
            "baseline": baseline,
            "candidate": candidate,
            "checks": [],
            "command": "verify",
            "contract_digest": contract_digest,
            "environment": prepared.report,
            "head": head,
            "limitations": [],
            "outcome": "no_candidate",
            "reference": reference,
            "version": 1,
            "violations": [],
        }
        if candidate is None:
            result["limitations"].append(
                f"l’arbre de travail est identique à la référence {reference} "
                f"({baseline}) ; aucun contrôle n’a été lancé ; une référence "
                "antérieure, par exemple HEAD~1, permet de vérifier un candidat "
                "déjà commité"
            )
            return result
        result.update(
            run_checks(
                repository=repository,
                baseline=baseline,
                candidate=candidate,
                contract=contract,
                environment=prepared.variables,
                control_runner=control_runner,
            )
        )
        return result
