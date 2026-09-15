"""Configuration loading.

Precedence (lowest to highest): built-in defaults, ``~/.config/495/config.toml``,
``<project>/.495/config.toml``, ``<project>/.495/project.toml`` (project criteria only),
then command-line overrides applied by the interface layer.

The project criteria carry one thing no file states: the lessons earlier runs showed and the
requester accepted (``core/reading/lessons.py``). They are read from
``<state_dir>/lessons.json`` and added to what ``project.toml`` declares, so that a command, a
convention or a scope admitted once is in force in every run that follows, whether or not
anyone copied it into the file.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from harness495.core.models import (
    AgentSpec,
    Budget,
    HarnessConfig,
    ProjectCommand,
    ProjectConfig,
    ReviewerSpec,
    RolesConfig,
    SandboxConfig,
    ScopeConfig,
    VerificationKind,
)
from harness495.core.reading.lessons import criteria
from harness495.core.store import RunStore

USER_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "495"


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _agents_from(data: dict[str, Any]) -> dict[str, AgentSpec]:
    agents: dict[str, AgentSpec] = {}
    for name, spec in (data.get("agents") or {}).items():
        agents[name] = AgentSpec(name=name, **spec)
    if "default" not in agents:
        agents["default"] = AgentSpec(name="default")
    return agents


def _roles_from(data: dict[str, Any]) -> RolesConfig:
    roles = data.get("roles") or {}
    kwargs: dict[str, Any] = {}
    if "clarifier" in roles:
        kwargs["clarifier"] = roles["clarifier"]
    if "specifier" in roles:
        kwargs["specifier"] = roles["specifier"]
    if "producer" in roles:
        kwargs["producer"] = roles["producer"]
    if "test_designer" in roles:
        # `false` (or an empty string) in TOML, where there is no null: the producer writes
        # the tests to create itself.
        designer = roles["test_designer"]
        kwargs["test_designer"] = designer if isinstance(designer, str) and designer else None
    if "reviewers" in roles:
        kwargs["reviewers"] = [ReviewerSpec(**r) for r in roles["reviewers"]]
    return RolesConfig(**kwargs)


def _project_from(data: dict[str, Any]) -> ProjectConfig:
    commands = []
    for c in data.get("commands") or []:
        c = dict(c)
        if "kind" in c:
            c["kind"] = VerificationKind(c["kind"])
        c.setdefault("source", "project.toml")
        commands.append(ProjectCommand(**c))
    scope = ScopeConfig(**(data.get("scope") or {}))
    return ProjectConfig(
        commands=commands,
        conventions=list(data.get("conventions") or []),
        docs=list(data.get("docs") or []),
        scope=scope,
    )


def build_config(data: dict[str, Any], project_data: dict[str, Any] | None = None) -> HarnessConfig:
    project_data = project_data if project_data is not None else data.get("project") or {}
    return HarnessConfig(
        agents=_agents_from(data),
        roles=_roles_from(data),
        budget=Budget(**(data.get("budget") or {})),
        sandbox=SandboxConfig(**(data.get("sandbox") or {})),
        project=_project_from(project_data),
        auto_approve=bool(data.get("auto_approve", False)),
    )


def load_config(project_root: Path, state_dir: Path | None = None) -> HarnessConfig:
    state_dir = state_dir or (project_root / ".495")
    data: dict[str, Any] = {}
    for path in (USER_CONFIG / "config.toml", state_dir / "config.toml"):
        data = _deep_merge(data, _read_toml(path))
    project_data = _deep_merge(data.get("project") or {}, _read_toml(state_dir / "project.toml"))
    config = build_config(data, project_data)
    config.project = criteria(config.project, RunStore(state_dir).load_lessons())
    return config


CONFIG_TEMPLATE = """# 495 harness configuration (TOML). All keys are optional.

[agents.default]
kind = "claude_code"        # claude_code | codex | openai_compat
model = "sonnet"            # any model accepted by the CLI; omit to use the CLI default
# effort = "high"

[agents.codex]
kind = "codex"
# model = "gpt-5-codex"

[agents.local]
kind = "openai_compat"
base_url = "http://localhost:11434/v1"
model = "qwen2.5-coder:7b"
api_key_env = "OPENAI_API_KEY"
context_window = 32768

[roles]
clarifier = "default"       # asks you what the intent leaves open, before the specifier
specifier = "default"
test_designer = "default"   # writes the tests to create before the producer; false hands them to the producer
producer = "default"
reviewers = [
  { perspective = "spec_compliance", agent = "default" },
  { perspective = "correctness", agent = "default" },
  { perspective = "security", agent = "default" },
]
# test_quality is added to the reviewers whenever a verification is a test to create.

[budget]
max_cost_usd = 10.0
max_iterations = 3
max_clarify_rounds = 2
max_interventions = 40
intervention_timeout_s = 1800
command_timeout_s = 600
context_warn_ratio = 0.75
context_abort_ratio = 0.95
max_mutants = 5             # wrong versions of the change measured per iteration; 0 leaves the check out
mutant_command_max_s = 60   # a command slower than this on the change is not run against a mutant
max_coverage_commands = 2   # test commands run again under the project's coverage tool; 0 leaves the check out

[sandbox]
backend = "auto"            # auto | host | seatbelt | docker
docker_image = "python:3.12-slim"
allow_network = false
"""

PROJECT_TEMPLATE = """# Project criteria for 495 (TOML). Commands are run from the worktree root.
# Top-level keys must stay above the [[commands]] tables.
# The lessons you accept (495 lessons) add commands, conventions and allowed paths to what this
# file declares; 495 lessons show <id> states the lines each one would take here.

conventions = [
  # "All public functions carry a docstring",
]

docs = [
  # "CONTRIBUTING.md",
]

[scope]
allowed_paths = []          # e.g. ["src/**", "tests/**"]; empty means everything except forbidden
forbidden_paths = [".495/**", ".git/**", ".github/**", ".gitlab-ci.yml"]

# Commands are detected from pyproject.toml, package.json, Makefile...; declare them here to
# override or add. Each command runs from the worktree root and must exit 0 to pass.
# [[commands]]
# name = "test"
# command = "pytest -q"
# kind = "test"          # command | test | lint | build | typecheck
"""
