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

from harness495.core import catalogue, coverage, git
from harness495.core.coverage import Tree, read_ci
from harness495.core.models import (
    ProjectCommand,
    ProjectConfig,
    ProjectProfile,
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


GEM = re.compile(r"""^\s*gem\s+['"]([A-Za-z0-9_.-]+)['"]""", re.M)


def _shell_tree(root: Path, tooling: list[str]) -> Tree:
    """What the shell markers read: the tools the detector recognised, the gems a ``Gemfile``
    lists, the test files (``.bats``, ``.sh``, ``.rb``, ``.py`` and ``.feature`` under the test
    directories and ``features/``), the CI files."""
    tree = Tree(root=root, recognised=frozenset(tooling))
    gemfile = root / "Gemfile"
    if gemfile.is_file():
        for name in GEM.findall(_read_small(gemfile)):
            tree.dependencies.setdefault(name, "Gemfile")

    def is_test(path: Path) -> bool:
        parts = path.relative_to(root).parts[:-1]
        in_test_dir = any(part.lower() in TEST_DIRS for part in parts)
        return in_test_dir and path.suffix in (".bats", ".sh", ".rb", ".py", ".feature")

    for path in _walk(root, is_test):
        tree.tests[tree.rel(path)] = _read_small(path)
    read_ci(tree, _read_small)
    return tree


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


def _python_tree(root: Path, data: Mapping[str, Any]) -> Tree:
    """What the Python markers read: dependencies from ``pyproject.toml`` (PEP 621 and 735
    tables, poetry, pdm, uv) and ``requirements*.txt`` at the root or under ``requirements/``,
    the ``[tool]`` table, the test and feature files, the CI files."""
    tree = Tree(root=root, tool=data.get("tool", {}))

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
    read_ci(tree, _read_small)
    return tree


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
    prof.role_coverage.extend(
        coverage.rows("python", _python_tree(root, data), coverage.PYTHON_TOOLS)
    )


NODE_TEST_SUFFIXES = (".test.", ".spec.", ".bench.", ".fuzz.")


def _node_tree(root: Path, data: Mapping[str, Any]) -> Tree:
    """What the JavaScript / TypeScript markers read: the ``dependencies`` and
    ``devDependencies`` of ``package.json``, the test files (under the test directories, or
    named ``.test``, ``.spec``, ``.bench``, ``.fuzz``), the CI files and ``package.json``
    itself for its scripts."""
    tree = Tree(root=root)
    for key in ("dependencies", "devDependencies"):
        for name in data.get(key, {}):
            tree.dependencies.setdefault(name, "package.json")

    def is_test(path: Path) -> bool:
        if path.suffix not in (".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".tsx", ".jsx"):
            return path.suffix == ".feature"
        parts = path.relative_to(root).parts[:-1]
        in_test_dir = any(part.lower() in TEST_DIRS for part in parts)
        return in_test_dir or any(mark in path.name for mark in NODE_TEST_SUFFIXES)

    for path in _walk(root, is_test):
        tree.tests[tree.rel(path)] = _read_small(path)
    read_ci(tree, _read_small)
    tree.ci["package.json"] = json.dumps(data.get("scripts", {}))
    return tree


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
    prof.role_coverage.extend(
        coverage.rows("javascript/typescript", _node_tree(root, data), coverage.NODE_TOOLS)
    )
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


def _cargo_dependencies(text: str) -> list[str]:
    """The names of every dependency table of a Cargo manifest: regular, dev, build, workspace,
    per target."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    tables = [
        data.get("dependencies", {}),
        data.get("dev-dependencies", {}),
        data.get("build-dependencies", {}),
        data.get("workspace", {}).get("dependencies", {}),
        *(t.get("dependencies", {}) for t in data.get("target", {}).values()),
        *(t.get("dev-dependencies", {}) for t in data.get("target", {}).values()),
    ]
    names: list[str] = []
    for table in tables:
        for name, spec in table.items():
            names.append(spec.get("package", name) if isinstance(spec, dict) else name)
    return names


def _rust_tree(root: Path) -> Tree:
    """What the Rust markers read: the dependencies of ``Cargo.toml``, of the workspace members
    one level down and of ``fuzz/Cargo.toml``; the text of ``Cargo.toml`` and ``deny.toml``;
    the files under ``tests/``, ``benches/`` and ``features/``; the CI files."""
    tree = Tree(root=root)
    manifests = [root / "Cargo.toml", *sorted(root.glob("*/Cargo.toml"))]
    for manifest in manifests:
        if not manifest.is_file() or any(p in NOT_THE_PROJECT for p in manifest.parts):
            continue
        text = _read_small(manifest)
        tree.manifests[tree.rel(manifest)] = text
        for name in _cargo_dependencies(text):
            tree.dependencies.setdefault(name, tree.rel(manifest))
    deny = root / "deny.toml"
    if deny.is_file():
        tree.manifests["deny.toml"] = _read_small(deny)

    def is_test(path: Path) -> bool:
        parts = path.relative_to(root).parts[:-1]
        return bool(parts) and parts[0] in ("tests", "benches", "features")

    for path in _walk(root, is_test):
        tree.tests[tree.rel(path)] = _read_small(path)
    read_ci(tree, _read_small)
    return tree


GO_REQUIRE = re.compile(r"^\s*(?:require\s+)?([A-Za-z0-9][A-Za-z0-9._~/-]*)\s+v[0-9]", re.M)


def _go_tree(root: Path) -> Tree:
    """What the Go markers read: the module paths ``go.mod`` requires, the ``_test.go`` and
    ``.feature`` files, the golangci-lint configuration, the CI files."""
    tree = Tree(root=root)
    for name in GO_REQUIRE.findall(_read_small(root / "go.mod")):
        tree.dependencies.setdefault(name, "go.mod")
    for name in (".golangci.yml", ".golangci.yaml", ".golangci.toml"):
        if (root / name).is_file():
            tree.manifests[name] = _read_small(root / name)
    for path in _walk(root, lambda p: p.name.endswith("_test.go") or p.suffix == ".feature"):
        tree.tests[tree.rel(path)] = _read_small(path)
    read_ci(tree, _read_small)
    return tree


POM_ARTIFACT = re.compile(r"<artifactId>\s*([A-Za-z0-9_.-]+)\s*</artifactId>")
GRADLE_COORDINATE = re.compile(r"""['"][A-Za-z0-9_.-]+:([A-Za-z0-9_.-]+)(?::[^'"]*)?['"]""")
GRADLE_PLUGIN = re.compile(r"""id\s*\(?\s*['"]([A-Za-z0-9_.-]+)['"]""")
CATALOGUE_NAME = re.compile(
    r"""(?:module\s*=\s*['"][A-Za-z0-9_.-]+:|name\s*=\s*['"])([A-Za-z0-9_.-]+)['"]"""
)
GRADLE_FILES = ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")


def _jvm_tree(root: Path) -> Tree:
    """What the Java / Kotlin markers read: the ``artifactId``s of ``pom.xml``, the artifact
    names and plugin ids of the Gradle build files (root and one level down) and of
    ``gradle/libs.versions.toml``; the text of those files; the files under ``src/test``;
    the CI files."""
    tree = Tree(root=root)
    manifests = [
        root / "pom.xml",
        *sorted(root.glob("*/pom.xml")),
        *(root / name for name in GRADLE_FILES),
        *sorted(p for name in GRADLE_FILES for p in root.glob(f"*/{name}")),
        root / "gradle" / "libs.versions.toml",
    ]
    for manifest in manifests:
        if not manifest.is_file() or any(p in NOT_THE_PROJECT for p in manifest.parts):
            continue
        text = _read_small(manifest)
        rel = tree.rel(manifest)
        tree.manifests[rel] = text
        if manifest.name == "pom.xml":
            names = POM_ARTIFACT.findall(text)
        elif manifest.name == "libs.versions.toml":
            names = CATALOGUE_NAME.findall(text) + GRADLE_PLUGIN.findall(text)
        else:
            names = GRADLE_COORDINATE.findall(text) + GRADLE_PLUGIN.findall(text)
        for name in names:
            tree.dependencies.setdefault(name, rel)

    def is_test(path: Path) -> bool:
        parts = path.relative_to(root).parts
        return "test" in parts[:-1] and "src" in parts[:-1]

    for path in _walk(root, is_test, max_depth=6):
        tree.tests[tree.rel(path)] = _read_small(path)
    read_ci(tree, _read_small)
    return tree


def _detect_others(root: Path, prof: ProjectProfile, cmds: dict[str, ProjectCommand]) -> None:
    if (root / "Cargo.toml").exists():
        prof.languages.append("rust")
        prof.detected_from.append("Cargo.toml")
        prof.role_coverage.extend(coverage.rows("rust", _rust_tree(root), coverage.RUST_TOOLS))
        cmds.setdefault("test", _cmd("test", "cargo test", VerificationKind.test, "detected"))
        cmds.setdefault(
            "lint", _cmd("lint", "cargo clippy -- -D warnings", VerificationKind.lint, "detected")
        )
        cmds.setdefault("build", _cmd("build", "cargo build", VerificationKind.build, "detected"))
    if (root / "go.mod").exists():
        prof.languages.append("go")
        prof.detected_from.append("go.mod")
        prof.role_coverage.extend(coverage.rows("go", _go_tree(root), coverage.GO_TOOLS))
        cmds.setdefault("test", _cmd("test", "go test ./...", VerificationKind.test, "detected"))
        cmds.setdefault(
            "build", _cmd("build", "go build ./...", VerificationKind.build, "detected")
        )
        cmds.setdefault("lint", _cmd("lint", "go vet ./...", VerificationKind.lint, "detected"))
    if (root / "pom.xml").exists() or any(
        (root / name).exists() for name in ("build.gradle", "build.gradle.kts")
    ):
        prof.role_coverage.extend(coverage.rows("java/kotlin", _jvm_tree(root), coverage.JVM_TOOLS))
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
        prof.role_coverage.extend(
            coverage.rows("shell", _shell_tree(root, prof.tooling), coverage.SHELL_TOOLS)
        )
    prof.commands = list(cmds.values())
    prof.conventions = list(project.conventions)
    _collect_docs(root, prof, project.docs)
    prof.languages = list(dict.fromkeys(prof.languages))
    # A tool that measures a role is part of the tooling the agents are told about.
    prof.tooling = list(
        dict.fromkeys([*prof.tooling, *(t for r in prof.role_coverage for t in r.tools)])
    )
    prof.catalogue_gaps = catalogue.compare(prof)
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
