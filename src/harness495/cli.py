"""Interface en ligne de commande de 495."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from harness495.composition import (
    propose_with_codex,
    run_codex_change,
    validate_with_codex_sandbox,
    verify_with_codex_sandbox,
    write_with_codex_sandbox,
)
from harness495.errors import ChangeError, ConfigurationError
from harness495.serialization import result_bytes


# Table unique qui dérive le code de sortie de l’issue du document JSON.
EXIT_CODES = {
    "candidate_verified": 0,
    "proposal_ready": 0,
    "configuration_valid": 0,
    "configuration_written": 0,
    "candidate_failed": 1,
    "execution_impossible": 2,
    "configuration_invalid": 2,
    "agent_failed": 3,
    "no_candidate": 4,
    "no_checks_detected": 4,
}


def exit_code_for(result: dict[str, Any]) -> int:
    return EXIT_CODES[result["outcome"]]


def error_result(error: ChangeError, command: str) -> dict[str, Any]:
    """Document minimal d’une commande interrompue avant son résultat."""

    outcome = (
        "configuration_invalid"
        if isinstance(error, ConfigurationError)
        else "execution_impossible"
    )
    return {
        "command": command,
        "error": {"kind": error.kind, "message": str(error)},
        "outcome": outcome,
        "version": 1,
    }


def add_repository_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path("."),
        help="racine du dépôt Git cible (défaut : répertoire courant)",
    )


def add_contract_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="contrat de l’application cible (défaut : 495.json à la racine)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="495",
        description=(
            "Configure un dépôt pour 495, vérifie un candidat Git présent ou "
            "invoque Codex sur un dépôt local et contrôle le candidat produit."
        ),
    )
    commands = parser.add_subparsers(dest="command", metavar="<commande>")

    verify = commands.add_parser(
        "verify",
        help="vérifier l’écart entre l’arbre de travail et une référence Git",
        description=(
            "Exécute les contrôles du contrat sur l’écart entre l’arbre de travail "
            "et une référence Git, sans agent ni authentification."
        ),
    )
    add_repository_option(verify)
    add_contract_option(verify)
    verify.add_argument(
        "--baseline",
        default="HEAD",
        help="référence Git de l’état de départ, HEAD ou un ancêtre (défaut : HEAD)",
    )

    configure = commands.add_parser(
        "configure",
        help="proposer, valider ou enregistrer le contrat d’un dépôt",
        description=(
            "Prépare un dépôt pour 495 : propose un contrat depuis les conventions "
            "observées, valide un contrat présent ou enregistre une proposition relue."
        ),
    )
    configure.set_defaults(configure_parser=configure)
    operations = configure.add_subparsers(dest="operation", metavar="<opération>")

    propose = operations.add_parser(
        "propose",
        help="faire proposer un contrat par Codex en lecture seule, sans écriture",
        description=(
            "Inspecte le dépôt avec Codex en lecture seule et restitue une "
            "proposition de contrat sans rien écrire. Requiert un CODEX_HOME "
            "authentifié ; l’appel contacte le service Codex et consomme du quota."
        ),
    )
    add_repository_option(propose)
    propose.add_argument("--codex-home", required=True, type=Path)
    propose.add_argument("--agent-timeout-seconds", type=int, default=900)

    validate = operations.add_parser(
        "validate",
        help="contrôler un contrat présent sans authentification",
        description=(
            "Valide le format d’un contrat présent, résout ses exécutables et "
            "sonde ses profils sandbox, sans agent ni authentification."
        ),
    )
    add_repository_option(validate)
    add_contract_option(validate)

    write = operations.add_parser(
        "write",
        help="valider une proposition relue puis l’enregistrer dans le dépôt",
        description=(
            "Extrait le contrat d’une proposition produite par configure propose, "
            "éventuellement modifiée, le valide puis l’enregistre. Un contrat "
            "existant n’est remplacé qu’avec --overwrite."
        ),
    )
    add_repository_option(write)
    write.add_argument(
        "--proposal",
        required=True,
        type=Path,
        help="document JSON produit par configure propose",
    )
    add_contract_option(write)
    write.add_argument(
        "--overwrite",
        action="store_true",
        help="remplacer un contrat existant",
    )

    change = commands.add_parser(
        "change",
        help="invoquer Codex sur un dépôt propre puis contrôler le candidat",
        description="Invoque Codex sur un dépôt local et contrôle le candidat produit.",
    )
    change.add_argument("--repository", required=True, type=Path)
    change.add_argument("--contract", required=True, type=Path)
    change.add_argument("--request-file", required=True, type=Path)
    change.add_argument("--codex-home", required=True, type=Path)
    change.add_argument("--agent-timeout-seconds", type=int, default=900)
    return parser


def normalize_arguments(arguments: Sequence[str] | None) -> list[str]:
    """Traite l’invocation historique, sans sous-commande, comme `change`."""

    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if arguments and arguments[0].startswith("--"):
        return ["change", *arguments]
    return arguments


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(normalize_arguments(arguments))


def command_label(options: argparse.Namespace) -> str:
    if options.command == "configure":
        return f"configure {options.operation}"
    return options.command


def default_contract(options: argparse.Namespace) -> Path:
    if options.contract is None:
        return options.repository / "495.json"
    return options.contract


def require_positive_agent_timeout(options: argparse.Namespace) -> None:
    if options.agent_timeout_seconds <= 0:
        raise ChangeError("configuration", "le timeout de l’agent doit être positif")


def verify_command(options: argparse.Namespace) -> dict[str, Any]:
    return verify_with_codex_sandbox(
        repository=options.repository,
        contract_path=default_contract(options),
        reference=options.baseline,
    )


def configure_command(options: argparse.Namespace) -> dict[str, Any]:
    if options.operation == "propose":
        require_positive_agent_timeout(options)
        return propose_with_codex(
            repository=options.repository,
            codex_home=options.codex_home,
            agent_timeout_seconds=options.agent_timeout_seconds,
        )
    if options.operation == "validate":
        return validate_with_codex_sandbox(
            repository=options.repository,
            contract_path=default_contract(options),
        )
    return write_with_codex_sandbox(
        repository=options.repository,
        proposal_path=options.proposal,
        contract_path=default_contract(options),
        overwrite=options.overwrite,
    )


def change_command(options: argparse.Namespace) -> dict[str, Any]:
    require_positive_agent_timeout(options)
    try:
        request = options.request_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ChangeError(
            "precondition",
            f"demande illisible : {options.request_file}: {error}",
        ) from error
    if not request.strip():
        raise ChangeError("precondition", "la demande doit être non vide")
    return run_codex_change(
        repository=options.repository,
        contract_path=options.contract,
        request=request,
        codex_home=options.codex_home,
        agent_timeout_seconds=options.agent_timeout_seconds,
    )


def main(arguments: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = normalize_arguments(arguments)
    if not arguments:
        parser.print_help()
        return 0
    options = parser.parse_args(arguments)
    if options.command == "configure" and options.operation is None:
        options.configure_parser.print_help()
        return 0
    try:
        if options.command == "verify":
            result = verify_command(options)
        elif options.command == "configure":
            result = configure_command(options)
        else:
            result = change_command(options)
    except ChangeError as error:
        result = error_result(error, command_label(options))
    sys.stdout.buffer.write(result_bytes(result))
    sys.stdout.buffer.flush()
    return exit_code_for(result)


if __name__ == "__main__":
    raise SystemExit(main())
