"""Interface en ligne de commande de 495."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from harness495.change import error_result
from harness495.composition import run_codex_change
from harness495.errors import ChangeError
from harness495.serialization import canonical_bytes


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Invoque Codex sur un dépôt local et contrôle le candidat produit."
    )
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--request-file", required=True, type=Path)
    parser.add_argument("--codex-home", required=True, type=Path)
    parser.add_argument("--agent-timeout-seconds", type=int, default=900)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        if options.agent_timeout_seconds <= 0:
            raise ChangeError(
                "configuration", "le timeout de l’agent doit être positif"
            )
        try:
            request = options.request_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ChangeError(
                "precondition",
                f"demande illisible : {options.request_file}: {error}",
            ) from error
        if not request.strip():
            raise ChangeError("precondition", "la demande doit être non vide")
        result, exit_code = run_codex_change(
            repository=options.repository,
            contract_path=options.contract,
            request=request,
            codex_home=options.codex_home,
            agent_timeout_seconds=options.agent_timeout_seconds,
        )
    except ChangeError as error:
        result = error_result(error)
        exit_code = 2
    sys.stdout.buffer.write(canonical_bytes(result))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
