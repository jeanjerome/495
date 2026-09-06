"""Environnement transmis aux processus lancés sur une application cible."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from harness495.errors import ChangeError


@dataclass(frozen=True)
class PreparedEnvironment:
    """Variables filtrées et chemins temporaires d’une exécution."""

    variables: dict[str, str]
    report: dict[str, list[str]]
    artifacts: Path


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


@contextmanager
def prepared_environment(
    names: list[str],
    *,
    repository: Path,
    fixed: dict[str, str],
) -> Iterator[PreparedEnvironment]:
    """Crée hors du dépôt un répertoire temporaire et un HOME dédié, puis filtre les variables."""

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
        variables, report = inherited_environment(
            names, fixed=fixed, temporary_home=temporary_home
        )
        yield PreparedEnvironment(
            variables=variables, report=report, artifacts=artifacts
        )
