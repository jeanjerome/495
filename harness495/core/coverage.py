"""Role coverage: which tool a project measures each catalogue role with, per technology.

A technology enters here with the study that fills its section of ``docs/test-libraries.md``
(``docs/studies/``): the study's "What a profile can detect" section is the marker table of
the technology (``PYTHON_TOOLS``, ``SHELL_TOOLS``, ...), the recommended tools first in their
role, then the alternatives the catalogue rejected or the ecosystem commonly uses, named so
that a role measured with another tool than the recommended one is reported as such rather
than as unmeasured. ``ROLES_BY_TECHNOLOGY`` lists the roles of the technology's table, and
``tests/test_catalogue.py`` keeps it equal to the document. A technology absent from it has
no rows at all, rather than a row per role saying "not measured": the latter would read as a
finding about the project when it is a gap in the profile
(``docs/decisions/0012-tests-use-proven-libraries-from-a-catalogue.md``).

Every marker reads a ``Tree``: what one technology's markers look at, gathered once by
``profile.py`` (the dependencies its manifest lists, the text of its test files and CI files,
the tools an earlier detector recognised).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness495.core.models import CatalogueRole, RoleCoverage

ROLES_BY_TECHNOLOGY: dict[str, tuple[CatalogueRole, ...]] = {
    "python": tuple(CatalogueRole),
    "shell": (
        CatalogueRole.runner,
        CatalogueRole.bdd,
        CatalogueRole.static,
        CatalogueRole.security,
    ),
}
"""The roles the catalogue (``docs/test-libraries.md``) has a table for, per technology."""


@dataclass
class Tree:
    """Everything the markers of one technology read, gathered once.

    ``dependencies`` maps a dependency name, as the manifest spells it, to the file that lists
    it. ``tool`` is ``pyproject.toml``'s ``[tool]`` table (Python only). ``tests``, ``ci`` and
    ``manifests`` map a path relative to the root to the file's text. ``recognised`` names
    the tools an earlier detector found in the tree (shell: the tools ``_detect_shell`` reads
    from configuration and directives).
    """

    root: Path
    dependencies: dict[str, str] = field(default_factory=dict)
    tool: Mapping[str, Any] = field(default_factory=dict)
    tests: dict[str, str] = field(default_factory=dict)
    ci: dict[str, str] = field(default_factory=dict)
    manifests: dict[str, str] = field(default_factory=dict)
    recognised: frozenset[str] = frozenset()

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()


Marker = Callable[[Tree], str | None]
"""What one tool is recognised from: the description of the evidence, or None when absent."""

ToolTable = tuple[tuple[CatalogueRole, str, tuple[Marker, ...]], ...]
"""Which tool measures which role, and what it is recognised from, for one technology."""


def dependency(name: str) -> Marker:
    return lambda t: (
        f"{t.dependencies[name]}: dependency {name}" if name in t.dependencies else None
    )


def tool_table(name: str) -> Marker:
    return lambda t: f"pyproject.toml: [tool.{name}]" if name in t.tool else None


def config_file(name: str) -> Marker:
    return lambda t: name if (t.root / name).is_file() else None


def config_glob(pattern: str) -> Marker:
    """A configuration file named by a glob at the root: ``vitest.config.*``."""

    def found(t: Tree) -> str | None:
        for path in sorted(t.root.glob(pattern)):
            if path.is_file():
                return path.name
        return None

    return found


def directory(name: str) -> Marker:
    return lambda t: f"{name}/ directory" if (t.root / name).is_dir() else None


def _in(files: str, text: str) -> Marker:
    def found(t: Tree) -> str | None:
        for rel, source in getattr(t, files).items():
            if text in source:
                return f"{rel}: {text}"
        return None

    return found


def in_tests(text: str) -> Marker:
    return _in("tests", text)


def in_ci(text: str) -> Marker:
    return _in("ci", text)


def in_manifest(text: str) -> Marker:
    return _in("manifests", text)


def recognised(tool: str) -> Marker:
    return lambda t: f"{tool} recognised in the tree" if tool in t.recognised else None


def rows(technology: str, tree: Tree, table: ToolTable) -> list[RoleCoverage]:
    """One row per role of the technology's table, with the tools whose markers hold."""
    out = {
        role: RoleCoverage(technology=technology, role=role)
        for role in ROLES_BY_TECHNOLOGY[technology]
    }
    for role, tool, markers in table:
        for marker in markers:
            found = marker(tree)
            if found is not None:
                out[role].tools.append(tool)
                out[role].markers.append(found)
                break
    return list(out.values())


CI_FILES = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".gitlab-ci.yml",
    ".pre-commit-config.yaml",
    "tox.ini",
    "noxfile.py",
    "Makefile",
    "justfile",
    "Justfile",
    "Taskfile.yml",
)
"""Where a project says which commands it runs: read for the tools only a command names."""


def read_ci(tree: Tree, read: Callable[[Path], str]) -> None:
    for pattern in CI_FILES:
        for path in sorted(tree.root.glob(pattern)):
            if path.is_file():
                tree.ci[tree.rel(path)] = read(path)


# ------------------------------------------------------------------------------- python


def _ruff_selects_s(t: Tree) -> str | None:
    """ruff measures security when its ``S`` rules (the flake8-bandit port) are selected."""
    lint = t.tool.get("ruff", {}).get("lint", {})
    selected = [*lint.get("select", []), *lint.get("extend-select", [])]
    if any(rule == "S" or rule == "ALL" or re.fullmatch(r"S\d+", rule) for rule in selected):
        return "pyproject.toml: [tool.ruff.lint] select S"
    for name in ("ruff.toml", ".ruff.toml"):
        path = t.root / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r'(?:extend-)?select\s*=\s*\[[^\]]*"(?:S|ALL|S\d+)"', text):
                return f"{name}: select S"
    return None


def _setup_cfg_section(name: str) -> Marker:
    def found(t: Tree) -> str | None:
        path = t.root / "setup.cfg"
        if path.is_file() and f"[{name}]" in path.read_text(encoding="utf-8", errors="ignore"):
            return f"setup.cfg: [{name}]"
        return None

    return found


PYTHON_TOOLS: ToolTable = (
    (
        CatalogueRole.runner,
        "pytest",
        (
            dependency("pytest"),
            tool_table("pytest"),
            config_file("pytest.ini"),
            in_tests("import pytest"),
            in_tests("from pytest import"),
        ),
    ),
    (
        CatalogueRole.runner,
        "unittest",
        (in_tests("import unittest"), in_tests("from unittest import")),
    ),
    (CatalogueRole.runner, "nose2", (dependency("nose2"),)),
    (
        CatalogueRole.bdd,
        "pytest-bdd",
        (
            dependency("pytest-bdd"),
            in_tests("from pytest_bdd import"),
            in_tests("import pytest_bdd"),
        ),
    ),
    (
        CatalogueRole.bdd,
        "behave",
        (dependency("behave"), directory("features/steps"), config_file("behave.ini")),
    ),
    (
        CatalogueRole.property,
        "hypothesis",
        (
            dependency("hypothesis"),
            tool_table("hypothesis"),
            in_tests("from hypothesis import"),
            in_tests("import hypothesis"),
        ),
    ),
    (CatalogueRole.property, "pytest-quickcheck", (dependency("pytest-quickcheck"),)),
    (
        CatalogueRole.fuzzing,
        "atheris",
        (dependency("atheris"), in_tests("atheris.Setup("), directory("oss-fuzz")),
    ),
    (CatalogueRole.fuzzing, "pythonfuzz", (dependency("pythonfuzz"),)),
    (
        CatalogueRole.mutation,
        "mutmut",
        (
            tool_table("mutmut"),
            _setup_cfg_section("mutmut"),
            dependency("mutmut"),
            directory("mutants"),
        ),
    ),
    (CatalogueRole.mutation, "mutatest", (dependency("mutatest"),)),
    (CatalogueRole.mutation, "cosmic-ray", (dependency("cosmic-ray"),)),
    (
        CatalogueRole.coverage,
        "coverage.py",
        (
            tool_table("coverage"),
            config_file(".coveragerc"),
            dependency("coverage"),
            dependency("pytest-cov"),
        ),
    ),
    (CatalogueRole.coverage, "diff-cover", (dependency("diff-cover"), in_ci("diff-cover"))),
    (
        CatalogueRole.architecture,
        "import-linter",
        (
            tool_table("importlinter"),
            config_file(".importlinter"),
            _setup_cfg_section("importlinter"),
            dependency("import-linter"),
        ),
    ),
    (CatalogueRole.architecture, "pytest-archon", (dependency("pytest-archon"),)),
    (
        CatalogueRole.static,
        "ruff",
        (
            tool_table("ruff"),
            config_file("ruff.toml"),
            config_file(".ruff.toml"),
            dependency("ruff"),
        ),
    ),
    (CatalogueRole.static, "flake8", (config_file(".flake8"), dependency("flake8"))),
    (
        CatalogueRole.static,
        "pylint",
        (tool_table("pylint"), config_file(".pylintrc"), dependency("pylint")),
    ),
    (CatalogueRole.static, "black", (tool_table("black"), dependency("black"))),
    (
        CatalogueRole.types,
        "mypy",
        (tool_table("mypy"), config_file("mypy.ini"), dependency("mypy")),
    ),
    (
        CatalogueRole.types,
        "pyright",
        (tool_table("pyright"), config_file("pyrightconfig.json"), dependency("pyright")),
    ),
    (CatalogueRole.security, "ruff", (_ruff_selects_s,)),
    (CatalogueRole.security, "pip-audit", (dependency("pip-audit"), in_ci("pip-audit"))),
    (
        CatalogueRole.security,
        "bandit",
        (tool_table("bandit"), config_file(".bandit"), dependency("bandit"), in_ci("bandit")),
    ),
    (CatalogueRole.security, "safety", (dependency("safety"),)),
    (
        CatalogueRole.contract,
        "schemathesis",
        (dependency("schemathesis"), in_tests("schemathesis"), in_tests("schema.parametrize(")),
    ),
    (
        CatalogueRole.performance,
        "pytest-benchmark",
        (dependency("pytest-benchmark"), config_file(".benchmarks"), in_tests("benchmark")),
    ),
    (
        CatalogueRole.performance,
        "pytest-memray",
        (dependency("pytest-memray"), in_tests("limit_memory")),
    ),
    (CatalogueRole.doubles, "pytest-mock", (dependency("pytest-mock"), in_tests("mocker"))),
    (CatalogueRole.doubles, "respx", (dependency("respx"),)),
    (CatalogueRole.doubles, "time-machine", (dependency("time-machine"),)),
    (
        CatalogueRole.doubles,
        "unittest.mock",
        (in_tests("unittest.mock"), in_tests("from unittest import mock")),
    ),
)
"""The Python markers (``docs/studies/2026-09-13-python-test-libraries.md`` and
``-bdd-libraries.md``). ``pytest-cov`` names ``coverage.py``: it is its pytest integration,
not a second engine."""


# -------------------------------------------------------------------------------- shell

SHELL_TOOLS: ToolTable = (
    (CatalogueRole.runner, "bats", (recognised("bats"),)),
    (CatalogueRole.runner, "shellspec", (recognised("shellspec"),)),
    (CatalogueRole.runner, "shunit2", (recognised("shunit2"),)),
    (
        CatalogueRole.runner,
        "bashunit",
        (config_file("bashunit"), config_file("lib/bashunit"), in_tests("function test_")),
    ),
    (CatalogueRole.bdd, "cucumber", (dependency("cucumber"), in_tests("aruba/cucumber"))),
    (CatalogueRole.bdd, "aruba", (dependency("aruba"), in_tests("aruba/cucumber"))),
    (
        CatalogueRole.bdd,
        "@cucumber/cucumber",
        tuple(
            config_file(f"cucumber.{ext}") for ext in ("js", "mjs", "cjs", "json", "yaml", "yml")
        ),
    ),
    (CatalogueRole.bdd, "behave", (directory("features/steps"), config_file("behave.ini"))),
    (CatalogueRole.static, "shellcheck", (recognised("shellcheck"),)),
    (CatalogueRole.static, "shfmt", (recognised("shfmt"),)),
    (CatalogueRole.security, "shellcheck", (recognised("shellcheck"),)),
    (CatalogueRole.security, "gitleaks", (config_file(".gitleaks.toml"), in_ci("gitleaks"))),
)
"""The shell markers (``docs/studies/2026-09-13-shell-test-libraries.md``).

The runner and static tools are those ``_detect_shell`` recognises from configuration and
directives; ``dependencies`` are the gems a ``Gemfile`` lists, ``tests`` the files under the
test directories and ``features/``. shellcheck measures security as well as static: its
warnings are the analysis there is for shell.
"""

TABLES: dict[str, ToolTable] = {"python": PYTHON_TOOLS, "shell": SHELL_TOOLS}
"""The marker table of each technology that has coverage rows."""
