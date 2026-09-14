"""Live tests against the real agent CLIs. Deselected unless HARNESS495_LIVE=1 (they spend tokens)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from harness495.agents.base import AgentTask
from harness495.agents.claude_code import ClaudeCodeAgent
from harness495.agents.codex import CodexAgent
from harness495.core.config import load_config
from harness495.core.engine import Engine
from harness495.core.models import (
    AgentKind,
    AgentSpec,
    Capability,
    InterventionStatus,
    ReviewerSpec,
    Role,
    RunMode,
    RunStatus,
    Verdict,
)
from harness495.core.store import RunStore

pytestmark = pytest.mark.live

LIVE = os.environ.get("HARNESS495_LIVE") == "1"


def _config(project: Path, kind: AgentKind, model: str | None) -> object:
    cfg = load_config(project)
    cfg.agents["live"] = AgentSpec(name="live", kind=kind, model=model)
    cfg.roles.specifier = "live"
    cfg.roles.producer = "live"
    cfg.roles.reviewers = [ReviewerSpec(perspective="spec_compliance", agent="live")]
    cfg.budget.max_cost_usd = 2.0
    cfg.budget.intervention_timeout_s = 600
    cfg.auto_approve = True
    return cfg


@pytest.mark.skipif(
    not LIVE or shutil.which("claude") is None, reason="set HARNESS495_LIVE=1 with claude installed"
)
def test_live_claude_change(sample_project: Path) -> None:
    engine = Engine(RunStore(sample_project / ".495"))
    cfg = _config(sample_project, AgentKind.claude_code, "haiku")
    run = engine.create_run(
        "Add subtract(a, b) returning a - b to calc.py with tests", sample_project, cfg
    )  # type: ignore[arg-type]
    run = engine.run(run.id)
    assert run.status in (RunStatus.delivered, RunStatus.awaiting_decision), (
        run.stop_reason,
        run.warnings,
    )
    assert run.consumption.interventions >= 3 and run.consumption.cost_usd > 0


@pytest.mark.skipif(
    not LIVE or shutil.which("codex") is None, reason="set HARNESS495_LIVE=1 with codex installed"
)
def test_live_codex_evaluate(sample_project: Path) -> None:
    from tests.conftest import good_producer

    good_producer(sample_project)
    engine = Engine(RunStore(sample_project / ".495"))
    cfg = _config(sample_project, AgentKind.codex, None)
    run = engine.create_run(
        "subtract(a, b) returns a - b",
        sample_project,
        cfg,
        RunMode.evaluate,
        evaluate_ref="WORKTREE",
    )  # type: ignore[arg-type]
    run = engine.run(run.id)
    assert run.status in (RunStatus.delivered, RunStatus.awaiting_decision, RunStatus.rejected)
    assert run.result.outcome in (Verdict.accept, Verdict.reject, Verdict.undetermined)


def _codeword_task(cwd: Path) -> AgentTask:
    """Ask the real CLI for a word that exists only in the project's own instruction file."""
    return AgentTask(
        role=Role.reviewer,
        capability=Capability.read,
        system_prompt="You answer in one word.",
        prompt=(
            "What is the project codeword? Reply with the codeword only, or NONE if you do not "
            "know it. Do not run any command and do not read any file."
        ),
        cwd=cwd,
        timeout_s=180,
    )


def _project_with_an_instruction_file(tmp_path: Path, *names: str) -> Path:
    root = tmp_path / "instructed"
    root.mkdir()
    for name in names:
        (root / name).write_text(
            "# Project rules\n\nThe project codeword is XYLOPHONE-7742. When asked for the "
            "codeword, answer with it.\n",
            encoding="utf-8",
        )
    settings = root / ".claude"
    settings.mkdir()
    (settings / "settings.json").write_text(
        '{"env": {"HARNESS495_PROJECT_SETTING": "loaded"}}', encoding="utf-8"
    )
    return root


@pytest.mark.skipif(
    not LIVE or shutil.which("claude") is None, reason="set HARNESS495_LIVE=1 with claude installed"
)
def test_live_claude_does_not_read_the_project_s_instruction_file(tmp_path: Path) -> None:
    """The native path is closed: what the target's CLAUDE.md says never reaches the model."""
    root = _project_with_an_instruction_file(tmp_path, "CLAUDE.md")
    agent = ClaudeCodeAgent(AgentSpec(name="live", kind=AgentKind.claude_code, model="haiku"))
    result = agent.run(_codeword_task(root))
    assert result.status is InterventionStatus.completed, result.error
    assert "XYLOPHONE" not in result.text, result.text


@pytest.mark.skipif(
    not LIVE or shutil.which("codex") is None, reason="set HARNESS495_LIVE=1 with codex installed"
)
def test_live_codex_does_not_read_the_project_s_instruction_file(tmp_path: Path) -> None:
    """Same on the other CLI, whose native path reads AGENTS.md."""
    root = _project_with_an_instruction_file(tmp_path, "AGENTS.md")
    agent = CodexAgent(AgentSpec(name="live", kind=AgentKind.codex, model=None))
    result = agent.run(_codeword_task(root))
    assert result.status is InterventionStatus.completed, result.error
    assert "XYLOPHONE" not in result.text, result.text
