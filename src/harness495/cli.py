"""Interface en ligne de commande de 495."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from harness495.composition import run_codex_change, verify_with_codex_sandbox
from harness495.errors import ChangeError, ConfigurationError
from harness495.serialization import result_bytes


# Table unique qui dérive le code de sortie de l’issue du document JSON.
EXIT_CODES = {
    "candidate_verified": 0,
    "candidate_failed": 1,
    "execution_impossible": 2,
    "configuration_invalid": 2,
    "agent_failed": 3,
    "no_candidate": 4,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="495",
        description=(
            "Vérifie un candidat Git présent ou invoque Codex sur un dépôt local "
            "et contrôle le candidat produit."
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
    verify.add_argument(
        "--repository",
        type=Path,
        default=Path("."),
        help="racine du dépôt Git cible (défaut : répertoire courant)",
    )
    verify.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="contrat de l’application cible (défaut : 495.json à la racine)",
    )
    verify.add_argument(
        "--baseline",
        default="HEAD",
        help="référence Git de l’état de départ, HEAD ou un ancêtre (défaut : HEAD)",
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


def verify_command(options: argparse.Namespace) -> dict[str, Any]:
    contract_path = options.contract
    if contract_path is None:
        contract_path = options.repository / "495.json"
    return verify_with_codex_sandbox(
        repository=options.repository,
        contract_path=contract_path,
        reference=options.baseline,
    )


def change_command(options: argparse.Namespace) -> dict[str, Any]:
    if options.agent_timeout_seconds <= 0:
        raise ChangeError("configuration", "le timeout de l’agent doit être positif")
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
    try:
        if options.command == "verify":
            result = verify_command(options)
        else:
            result = change_command(options)
    except ChangeError as error:
        result = error_result(error, options.command)
    sys.stdout.buffer.write(result_bytes(result))
    sys.stdout.buffer.flush()
    return exit_code_for(result)


if __name__ == "__main__":
    raise SystemExit(main())
