"""Project adaptation: detect the stack, its verification commands and its conventions.

Detection is heuristic and file-based. Anything the user declares in ``.495/project.toml``
takes precedence over what is detected. Readiness is then established by actually running
each command once on the base version inside the sandbox.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness495.core import git
from harness495.core.models import (
    CatalogueRole,
    ProjectCommand,
    ProjectConfig,
    ProjectProfile,
    RoleCoverage,
    VerificationKind,
)

DOC_CANDIDATES = [
    "CLAUDE.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "CODING_STANDARDS.md",
    "docs/CONTRIBUTING.md",
    "README.md",
]


NOT_THE_PROJECT = frozenset(
    {"node_modules", "vendor", "target", "build", "dist", "venv", "__pycache__", "site-packages"}
)
"""Directories whose contents belong to something else: dependencies, and what a build wrote.

A script found in one of them says what a library ships with, not what this project is written
in. Directories whose name starts with a dot are skipped for the same reason, and because that
is where the caches are.
"""


def _cmd(name: str, command: str, kind: VerificationKind, source: str) -> ProjectCommand:
    return ProjectCommand(name=name, command=command, kind=kind, source=source)


SHFMT_KEYS = (
    "shell_variant",
    "binary_next_line",
    "switch_case_indent",
    "space_redirects",
    "keep_padding",
    "function_next_line",
)
"""EditorConfig properties nothing but shfmt reads.

``indent_style`` and ``indent_size`` are in every ``.editorconfig`` ever written and say
nothing about who formats the shell.
"""


@dataclass(frozen=True)
class _ShellTree:
    """What one bounded walk found, for every shell question there is to ask."""

    scripts: tuple[Path, ...]
    bats: tuple[Path, ...]
    shunit2: bool

    def __bool__(self) -> bool:
        return bool(self.scripts or self.bats or self.shunit2)


def _walk(
    root: Path, keep: Callable[[Path], bool], max_depth: int = 3, limit: int = 400
) -> list[Path]:
    """The files ``keep`` selects, down to ``max_depth`` levels, outside what is not the project.

    Three levels reaches ``scripts/``, ``tests/unit/`` and ``src/pkg/tests/`` without walking a
    monorepo to the bottom; ``limit`` bounds what a pathological tree costs.
    """
    kept: list[Path] = []
    edge = [(root, 0)]
    while edge and len(kept) < limit:
        here, depth = edge.pop()
        try:
            entries = sorted(here.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if (
                    depth < max_depth
                    and entry.name not in NOT_THE_PROJECT
                    and not entry.name.startswith(".")
                ):
                    edge.append((entry, depth + 1))
            elif keep(entry) and len(kept) < limit:
                kept.append(entry)
    return kept


def _read_small(path: Path, max_bytes: int = 256_000) -> str:
    """The text of a file, or nothing when it is unreadable or too large to be a source."""
    try:
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _walk_shell(root: Path) -> _ShellTree:
    """Look for what a shell project is made of, wherever it keeps it.

    Every other stack here is recognised by a manifest — ``pyproject.toml``, ``package.json``,
    ``Cargo.toml``, ``go.mod``. Shell has none, so the files are the only evidence there is,
    and looking at the root alone finds nothing in the ordinary layout: scripts live in
    ``scripts/``, ``bin/`` or ``tools/``, and tests in ``test/`` or ``tests/``.
    """
    found = _walk(root, lambda p: p.suffix in (".sh", ".bats") or p.name == "shunit2")
    scripts = tuple(p for p in found if p.suffix == ".sh")
    bats = tuple(p for p in found if p.suffix == ".bats")
    return _ShellTree(scripts, bats, any(p.name == "shunit2" for p in found))


def _uses_shellcheck(root: Path, scripts: tuple[Path, ...], sample: int = 40) -> bool:
    """Whether the project lints its shell, by its configuration or by its own directives.

    ``.shellcheckrc`` is the declaration, and the rarer of the two: most projects that run
    shellcheck never write one. A ``# shellcheck`` comment is what someone leaves behind on
    the day they silence a finding, which is the same evidence one step further on.
    """
    if (root / ".shellcheckrc").exists():
        return True
    return any("# shellcheck" in _read_small(script) for script in scripts[:sample])


def _uses_shfmt(root: Path) -> bool:
    """Whether the project formats its shell, by the EditorConfig keys only shfmt reads."""
    config = root / ".editorconfig"
    try:
        text = config.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return any(key in text for key in SHFMT_KEYS)


def _detect_shell(root: Path, prof: ProjectProfile, cmds: dict[str, ProjectCommand]) -> None:
    """The stack with no manifest: what it is written in, and what keeps it honest.

    Last of the detectors, and the only one that reads what the others concluded. Most
    projects carry a script or two in ``scripts/`` or ``bin/`` without being written in shell,
    so a ``.sh`` file names the language only where nothing else was found — otherwise naming
    it would make a Django application part shell because it has a deploy script.

    The tools are reported either way, because they really are used here and the agents are
    told what a project is kept honest with. Their *commands* are not: a repository whose lint
    is shellcheck would be told that two helper scripts are all it checks.
    """
    tree = _walk_shell(root)
    if not tree:
        return

    written_in_shell = not prof.languages and bool(tree.scripts)
    if written_in_shell:
        prof.languages.append("shell")

    def propose(name: str, command: str, kind: VerificationKind) -> None:
        if written_in_shell:
            cmds.setdefault(name, _cmd(name, command, kind, "detected"))

    if _uses_shellcheck(root, tree.scripts):
        prof.tooling.append("shellcheck")
        # Through git rather than a glob: the command is run from the worktree root by a
        # shell, and what is tracked there is exactly what the project is answerable for.
        propose("lint", "shellcheck $(git ls-files '*.sh')", VerificationKind.lint)
    if _uses_shfmt(root):
        prof.tooling.append("shfmt")
        propose("format", "shfmt -d .", VerificationKind.lint)
    if (root / ".shellspec").exists() or (
        (root / "spec").is_dir() and any((root / "spec").glob("*_spec.sh"))
    ):
        prof.tooling.append("shellspec")
        propose("test", "shellspec", VerificationKind.test)
    if tree.bats:
        prof.tooling.append("bats")
        where = tree.bats[0].parent.relative_to(root)
        propose("test", f"bats {where}", VerificationKind.test)
    if tree.shunit2:
        # No command. shunit2 is sourced by the test script that uses it, and which script
        # that is, is the project's to say.
        prof.tooling.append("shunit2")


# --------------------------------------------------------------------------- role coverage

ROLES_BY_TECHNOLOGY: dict[str, tuple[CatalogueRole, ...]] = {
    "python": tuple(CatalogueRole),
    "shell": (
        CatalogueRole.runner,
        CatalogueRole.bdd,
        CatalogueRole.static,
        CatalogueRole.security,
    ),
}
"""The roles the catalogue (``docs/test-libraries.md``) has a table for, per technology.

Only the technologies whose tools the profile has markers for are listed. A technology absent
here gets no coverage rows at all, rather than a row per role saying "not measured": the
latter would read as a finding about the project when it is a gap in the profile. A
technology enters with the study that fills its section of the catalogue; the markers come
from that study (``docs/studies/``). ``tests/test_catalogue.py`` keeps this in step with the
document.
"""

TEST_DIRS = frozenset({"test", "tests", "spec", "specs", "testing", "features"})
DEPENDENCY_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _dependency_name(spec: str) -> str | None:
    """The distribution name of a requirement, normalised the way PyPI compares names."""
    m = DEPENDENCY_NAME.match(spec.strip())
    if m is None:
        return None
    return re.sub(r"[._]+", "-", m.group(0)).lower()


def _names_in(specs: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for spec in specs:
        if isinstance(spec, str):
            name = _dependency_name(spec)
            if name:
                out.append(name)
    return out


@dataclass
class _PythonTree:
    """Everything the Python markers read, gathered once.

    ``dependencies`` maps a normalised distribution name to the file that lists it, from
    ``pyproject.toml`` (PEP 621 and 735 tables, poetry, pdm, uv) and from ``requirements*.txt``
    at the root or under ``requirements/``. ``tool`` is the ``[tool]`` table. ``tests`` and
    ``ci`` map a path relative to the root to the file's text.
    """

    root: Path
    dependencies: dict[str, str] = field(default_factory=dict)
    tool: Mapping[str, Any] = field(default_factory=dict)
    tests: dict[str, str] = field(default_factory=dict)
    ci: dict[str, str] = field(default_factory=dict)

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()


def _python_tree(root: Path, data: Mapping[str, Any]) -> _PythonTree:
    tree = _PythonTree(root=root, tool=data.get("tool", {}))

    def add(names: Iterable[str], source: str) -> None:
        for name in names:
            tree.dependencies.setdefault(name, source)

    project = data.get("project", {})
    tool = tree.tool
    add(_names_in(project.get("dependencies", [])), "pyproject.toml")
    for specs in project.get("optional-dependencies", {}).values():
        add(_names_in(specs), "pyproject.toml")
    for specs in data.get("dependency-groups", {}).values():
        add(_names_in(specs), "pyproject.toml")
    poetry = tool.get("poetry", {})
    add(_names_in(poetry.get("dependencies", {})), "pyproject.toml")
    add(_names_in(poetry.get("dev-dependencies", {})), "pyproject.toml")
    for group in poetry.get("group", {}).values():
        add(_names_in(group.get("dependencies", {})), "pyproject.toml")
    for specs in tool.get("pdm", {}).get("dev-dependencies", {}).values():
        add(_names_in(specs), "pyproject.toml")
    add(_names_in(tool.get("uv", {}).get("dev-dependencies", [])), "pyproject.toml")
    for req in sorted([*root.glob("requirements*.txt"), *root.glob("requirements/*.txt")]):
        lines = [
            line
            for line in _read_small(req).splitlines()
            if line.strip() and line.lstrip()[0] not in "#-"
        ]
        add(_names_in(lines), tree.rel(req))

    def is_test(path: Path) -> bool:
        parts = path.relative_to(root).parts[:-1]
        in_test_dir = any(part.lower() in TEST_DIRS for part in parts)
        if path.suffix == ".py":
            return in_test_dir or path.name.startswith("test_") or path.name.endswith("_test.py")
        return path.suffix == ".feature"

    for path in _walk(root, is_test):
        tree.tests[tree.rel(path)] = _read_small(path)
    ci_files = [
        *sorted((root / ".github" / "workflows").glob("*.yml")),
        *sorted((root / ".github" / "workflows").glob("*.yaml")),
        root / ".gitlab-ci.yml",
        root / ".pre-commit-config.yaml",
        root / "tox.ini",
        root / "noxfile.py",
        root / "Makefile",
    ]
    for path in ci_files:
        if path.is_file():
            tree.ci[tree.rel(path)] = _read_small(path)
    return tree


Marker = Callable[[_PythonTree], str | None]
"""What one tool is recognised from: the description of the evidence, or None when absent."""


def dependency(name: str) -> Marker:
    return lambda t: (
        f"{t.dependencies[name]}: dependency {name}" if name in t.dependencies else None
    )


def tool_table(name: str) -> Marker:
    return lambda t: f"pyproject.toml: [tool.{name}]" if name in t.tool else None


def config_file(name: str) -> Marker:
    return lambda t: name if (t.root / name).is_file() else None


def directory(name: str) -> Marker:
    return lambda t: f"{name}/ directory" if (t.root / name).is_dir() else None


def in_tests(text: str) -> Marker:
    def found(t: _PythonTree) -> str | None:
        for rel, source in t.tests.items():
            if text in source:
                return f"{rel}: {text}"
        return None

    return found


def in_ci(text: str) -> Marker:
    def found(t: _PythonTree) -> str | None:
        for rel, source in t.ci.items():
            if text in source:
                return f"{rel}: {text}"
        return None

    return found


def _ruff_selects_s(t: _PythonTree) -> str | None:
    """ruff's ``S`` rules are the port of bandit's; selecting them is a security measure."""

    def selected(table: Mapping[str, Any]) -> list[str]:
        return [str(x) for x in [*table.get("select", []), *table.get("extend-select", [])]]

    def has_s(rules: list[str]) -> bool:
        return any(r == "ALL" or r == "S" or re.fullmatch(r"S\d+", r) for r in rules)

    ruff = t.tool.get("ruff", {})
    if has_s(selected(ruff.get("lint", {}))) or has_s(selected(ruff)):
        return "pyproject.toml: [tool.ruff.lint] select includes S"
    for name in ("ruff.toml", ".ruff.toml"):
        path = t.root / name
        if not path.is_file():
            continue
        try:
            data = tomllib.loads(_read_small(path))
        except tomllib.TOMLDecodeError:
            continue
        if has_s(selected(data.get("lint", {}))) or has_s(selected(data)):
            return f"{name}: select includes S"
    return None


def _setup_cfg_section(name: str) -> Marker:
    return lambda t: (
        f"setup.cfg: [{name}]" if f"[{name}]" in _read_small(t.root / "setup.cfg") else None
    )


PYTHON_TOOLS: tuple[tuple[CatalogueRole, str, tuple[Marker, ...]], ...] = (
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
"""Which tool measures which role, and what it is recognised from.

The recommended tools come first in their role with the markers the studies list
(``docs/studies/2026-09-13-python-test-libraries.md`` and ``-bdd-libraries.md``, section "What
a profile can detect"); the tools after them are the alternatives the catalogue rejected or
the ecosystem commonly uses, named so that a role measured with another tool than the
recommended one is reported as such rather than as unmeasured. ``pytest-cov`` names
``coverage.py``: it is its pytest integration, not a second engine.
"""


def _python_coverage(tree: _PythonTree) -> list[RoleCoverage]:
    rows = {
        role: RoleCoverage(technology="python", role=role) for role in ROLES_BY_TECHNOLOGY["python"]
    }
    for role, tool, markers in PYTHON_TOOLS:
        for marker in markers:
            found = marker(tree)
            if found is not None:
                rows[role].tools.append(tool)
                rows[role].markers.append(found)
                break
    return list(rows.values())


SHELL_TOOLS: dict[CatalogueRole, tuple[str, ...]] = {
    CatalogueRole.runner: ("shellspec", "bats", "shunit2"),
    CatalogueRole.static: ("shellcheck", "shfmt"),
}
"""The shell roles, measured with the tools ``_detect_shell`` already recognises.

``bdd`` and ``security`` have no marker yet: shellspec's describe/it is not Gherkin, and the
catalogue's shell section awaits its study.
"""


def _shell_coverage(tooling: list[str]) -> list[RoleCoverage]:
    rows = []
    for role in ROLES_BY_TECHNOLOGY["shell"]:
        used = [tool for tool in SHELL_TOOLS.get(role, ()) if tool in tooling]
        rows.append(
            RoleCoverage(
                technology="shell",
                role=role,
                tools=used,
                markers=[f"{tool} recognised in the tree" for tool in used],
            )
        )
    return rows


def _detect_python(root: Path, prof: ProjectProfile, cmds: dict[str, ProjectCommand]) -> None:
    pyproject = root / "pyproject.toml"
    has_py = pyproject.exists() or (root / "setup.py").exists() or (root / "setup.cfg").exists()
    if not has_py and not any(root.glob("*.py")):
        return
    prof.languages.append("python")
    data: dict[str, Any] = {}
    if pyproject.exists():
        prof.detected_from.append("pyproject.toml")
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            data = {}
    tool = data.get("tool", {})
    deps = (
        json.dumps(data.get("project", {}).get("dependencies", []))
        + json.dumps(data.get("project", {}).get("optional-dependencies", {}))
        + json.dumps(tool.get("poetry", {}).get("dev-dependencies", {}))
        + json.dumps(tool.get("poetry", {}).get("group", {}))
        + json.dumps(data.get("dependency-groups", {}))
    )
    runner = "python -m"
    if (root / "uv.lock").exists():
        runner = "uv run --frozen python -m"
        prof.tooling.append("uv")
    elif (root / "poetry.lock").exists():
        runner = "poetry run python -m"
        prof.tooling.append("poetry")
    if (
        "pytest" in tool
        or "pytest" in deps
        or (root / "pytest.ini").exists()
        or (root / "tests").is_dir()
    ):
        prof.tooling.append("pytest")
        cmds.setdefault(
            "test", _cmd("test", f"{runner} pytest -q", VerificationKind.test, "detected")
        )
    if "ruff" in tool or "ruff" in deps or (root / "ruff.toml").exists():
        prof.tooling.append("ruff")
        cmds.setdefault(
            "lint", _cmd("lint", f"{runner} ruff check .", VerificationKind.lint, "detected")
        )
    elif "flake8" in deps or (root / ".flake8").exists():
        cmds.setdefault("lint", _cmd("lint", f"{runner} flake8", VerificationKind.lint, "detected"))
    if "mypy" in tool or "mypy" in deps or (root / "mypy.ini").exists():
        prof.tooling.append("mypy")
        cmds.setdefault(
            "typecheck",
            _cmd("typecheck", f"{runner} mypy .", VerificationKind.typecheck, "detected"),
        )
    elif "pyright" in tool or "pyright" in deps or (root / "pyrightconfig.json").exists():
        cmds.setdefault(
            "typecheck", _cmd("typecheck", "pyright", VerificationKind.typecheck, "detected")
        )
    prof.role_coverage.extend(_python_coverage(_python_tree(root, data)))


def _detect_node(root: Path, prof: ProjectProfile, cmds: dict[str, ProjectCommand]) -> None:
    pkg = root / "package.json"
    if not pkg.exists():
        return
    prof.languages.append("javascript/typescript")
    prof.detected_from.append("package.json")
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pm = "npm run"
    if (root / "pnpm-lock.yaml").exists():
        pm = "pnpm run"
        prof.tooling.append("pnpm")
    elif (root / "yarn.lock").exists():
        pm = "yarn"
        prof.tooling.append("yarn")
    elif (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        pm = "bun run"
        prof.tooling.append("bun")
    else:
        prof.tooling.append("npm")
    scripts = data.get("scripts", {})
    mapping = {
        "test": VerificationKind.test,
        "lint": VerificationKind.lint,
        "typecheck": VerificationKind.typecheck,
        "build": VerificationKind.build,
    }
    for name, kind in mapping.items():
        if name in scripts:
            cmds.setdefault(name, _cmd(name, f"{pm} {name}", kind, "package.json scripts"))
    if "typecheck" not in scripts and (root / "tsconfig.json").exists():
        cmds.setdefault(
            "typecheck",
            _cmd("typecheck", "npx tsc --noEmit", VerificationKind.typecheck, "tsconfig.json"),
        )


def _detect_others(root: Path, prof: ProjectProfile, cmds: dict[str, ProjectCommand]) -> None:
    if (root / "Cargo.toml").exists():
        prof.languages.append("rust")
        prof.detected_from.append("Cargo.toml")
        cmds.setdefault("test", _cmd("test", "cargo test", VerificationKind.test, "detected"))
        cmds.setdefault(
            "lint", _cmd("lint", "cargo clippy -- -D warnings", VerificationKind.lint, "detected")
        )
        cmds.setdefault("build", _cmd("build", "cargo build", VerificationKind.build, "detected"))
    if (root / "go.mod").exists():
        prof.languages.append("go")
        prof.detected_from.append("go.mod")
        cmds.setdefault("test", _cmd("test", "go test ./...", VerificationKind.test, "detected"))
        cmds.setdefault(
            "build", _cmd("build", "go build ./...", VerificationKind.build, "detected")
        )
        cmds.setdefault("lint", _cmd("lint", "go vet ./...", VerificationKind.lint, "detected"))
    if (root / "pom.xml").exists():
        prof.languages.append("java")
        prof.detected_from.append("pom.xml")
        mvn = "./mvnw" if (root / "mvnw").exists() else "mvn"
        cmds.setdefault(
            "test", _cmd("test", f"{mvn} -q -B test", VerificationKind.test, "detected")
        )
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        prof.languages.append("java/kotlin")
        prof.detected_from.append("build.gradle")
        gradle = "./gradlew" if (root / "gradlew").exists() else "gradle"
        cmds.setdefault("test", _cmd("test", f"{gradle} test", VerificationKind.test, "detected"))
    makefile = root / "Makefile"
    if makefile.exists():
        prof.detected_from.append("Makefile")
        targets = set(re.findall(r"^([A-Za-z0-9_-]+):", makefile.read_text(encoding="utf-8"), re.M))
        for name, kind in (
            ("test", VerificationKind.test),
            ("lint", VerificationKind.lint),
            ("check", VerificationKind.lint),
            ("build", VerificationKind.build),
        ):
            if name in targets:
                cmds.setdefault(name, _cmd(name, f"make {name}", kind, "Makefile"))
    if (root / ".pre-commit-config.yaml").exists():
        prof.tooling.append("pre-commit")


def _collect_docs(root: Path, prof: ProjectProfile, declared: list[str]) -> None:
    for rel in [*declared, *DOC_CANDIDATES]:
        p = root / rel
        if p.is_file() and rel not in prof.doc_files:
            prof.doc_files.append(rel)


def detect_profile(root: Path, project: ProjectConfig | None = None) -> ProjectProfile:
    root = root.resolve()
    project = project or ProjectConfig()
    prof = ProjectProfile(root=str(root))
    cmds: dict[str, ProjectCommand] = {}
    # User-declared commands win.
    for c in project.commands:
        cmds[c.name] = c
    _detect_python(root, prof, cmds)
    _detect_node(root, prof, cmds)
    _detect_others(root, prof, cmds)
    # Last: it is the one that asks what the others concluded.
    _detect_shell(root, prof, cmds)
    if "shell" in prof.languages:
        prof.role_coverage.extend(_shell_coverage(prof.tooling))
    prof.commands = list(cmds.values())
    prof.conventions = list(project.conventions)
    _collect_docs(root, prof, project.docs)
    prof.languages = list(dict.fromkeys(prof.languages))
    # A tool that measures a role is part of the tooling the agents are told about.
    prof.tooling = list(
        dict.fromkeys([*prof.tooling, *(t for r in prof.role_coverage for t in r.tools)])
    )
    if git.is_repo(root):
        try:
            prof.base_commit = git.head_commit(root)
            prof.default_branch = git.current_branch(root)
        except git.GitError:
            pass
    return prof


def read_doc_excerpts(root: Path, files: list[str], max_chars_each: int = 4000) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in files:
        p = root / rel
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > max_chars_each:
            text = text[:max_chars_each] + "\n[... truncated by 495 ...]\n"
        out[rel] = text
    return out
