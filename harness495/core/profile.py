"""Project adaptation: detect the stack, its verification commands and its conventions.

Detection is heuristic and file-based. Anything the user declares in ``.495/project.toml``
takes precedence over what is detected. Readiness is then established by actually running
each command once on the base version inside the sandbox.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from harness495.core import git
from harness495.core.models import ProjectCommand, ProjectConfig, ProjectProfile, VerificationKind

DOC_CANDIDATES = [
    "CLAUDE.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "CODING_STANDARDS.md",
    "docs/CONTRIBUTING.md",
    "README.md",
]


def _cmd(name: str, command: str, kind: VerificationKind, source: str) -> ProjectCommand:
    return ProjectCommand(name=name, command=command, kind=kind, source=source)


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
    if (
        (root / ".shellspec").exists()
        or (root / "spec").is_dir()
        and any((root / "spec").glob("*_spec.sh"))
    ):
        prof.tooling.append("shellspec")
        cmds.setdefault("test", _cmd("test", "shellspec", VerificationKind.test, "detected"))
    if any(root.glob("*.sh")) and "shell" not in prof.languages:
        prof.languages.append("shell")
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
    prof.commands = list(cmds.values())
    prof.conventions = list(project.conventions)
    _collect_docs(root, prof, project.docs)
    prof.languages = list(dict.fromkeys(prof.languages))
    prof.tooling = list(dict.fromkeys(prof.tooling))
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
