"""Whether the conditional entry of a catalogue cell applies, read from the project.

Each condition answers, of one project, whether the entry the catalogue lists after a cell's
default is the one that applies: a file of the tree, a dependency it declares, or a tool the
role coverage names. ``conditions_holding`` evaluates them all once, while the project is
being profiled and the tree is the one the run was asked about, and ``ProjectProfile.conditions``
keeps the names that held. Every later reading of the catalogue takes the answer from there
and opens no file (``core/reading/catalogue.py``,
``docs/decisions/0015-a-retrospective-states-what-each-tool-showed.md``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from harness495.core.models import CatalogueRole, ProjectProfile


def _measures_with(
    technology: str, role: CatalogueRole, tool: str
) -> Callable[[ProjectProfile], bool]:
    def holds(profile: ProjectProfile) -> bool:
        row = profile.coverage(technology, role)
        return row is not None and tool in row.tools

    return holds


def _no_pytest_suite_or_standalone_features(profile: ProjectProfile) -> bool:
    runner = profile.coverage("python", CatalogueRole.runner)
    has_pytest = runner is not None and "pytest" in runner.tools
    return not has_pytest or (Path(profile.root) / "features" / "steps").is_dir()


def _specs_in_shellspec_or_coverage_measured(profile: ProjectProfile) -> bool:
    """shellspec is the runner when the project already keeps its specs in it, or measures
    coverage: kcov traces the shell shellspec runs the script in (``When run source``), and
    bats under kcov did not finish (``docs/studies/2026-09-13-shell-test-libraries.md``)."""
    return _measures_with("shell", CatalogueRole.runner, "shellspec")(profile) or _measures_with(
        "shell", CatalogueRole.coverage, "kcov"
    )(profile)


def _uses_express(profile: ProjectProfile) -> bool:
    return (Path(profile.root) / "node_modules" / "express").is_dir() or _lists_dependency(
        Path(profile.root) / "package.json", "express"
    )


def _lists_dependency(package_json: Path, name: str) -> bool:
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return any(name in data.get(key, {}) for key in ("dependencies", "devDependencies"))


def _is_kotlin(profile: ProjectProfile) -> bool:
    root = Path(profile.root)
    if (root / "src" / "main" / "kotlin").is_dir():
        return True
    for name, marks in (
        ("build.gradle.kts", ("kotlin(", "org.jetbrains.kotlin")),
        ("build.gradle", ("org.jetbrains.kotlin",)),
        ("pom.xml", ("kotlin-maven-plugin",)),
    ):
        try:
            text = (root / name).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(mark in text for mark in marks):
            return True
    return False


def _is_kotlin_on_gradle(profile: ProjectProfile) -> bool:
    root = Path(profile.root)
    return _is_kotlin(profile) and any(
        (root / name).is_file() for name in ("build.gradle.kts", "build.gradle")
    )


CONDITIONS: dict[str, Callable[[ProjectProfile], bool]] = {
    "no_pytest_suite_or_standalone_features": _no_pytest_suite_or_standalone_features,
    "specs_in_shellspec_or_coverage_measured": _specs_in_shellspec_or_coverage_measured,
    "uses_express": _uses_express,
    "runs_cargo_audit": _measures_with("rust", CatalogueRole.security, "cargo-audit"),
    "runs_golangci_lint": _measures_with("go", CatalogueRole.static, "golangci-lint"),
    "is_kotlin": _is_kotlin,
    "runs_kotest": _measures_with("java/kotlin", CatalogueRole.runner, "kotest"),
    "is_kotlin_on_gradle": _is_kotlin_on_gradle,
}
"""What selects the second entry of a cell, by the name a ``Recommendation`` names it with.

These are the only functions of the harness that read the project to place a catalogue entry:
a file of the tree, or the role coverage detection has just established. What reads the
catalogue reads the names they left on the profile.
"""


def conditions_holding(profile: ProjectProfile) -> list[str]:
    """The names of the conditions that hold on the project, in the order of ``CONDITIONS``.

    Evaluated once, while the project is being profiled and the tree is the one the run was
    asked about; ``ProjectProfile.conditions`` keeps the answer, and every later reading of
    the catalogue takes it from there.
    """
    return [name for name, holds in CONDITIONS.items() if holds(profile)]
