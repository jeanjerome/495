"""Live tests against the real agent CLIs. Deselected unless HARNESS495_LIVE=1 (they spend tokens)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from harness495.core.config import load_config
from harness495.core.engine import Engine
from harness495.core.models import AgentKind, AgentSpec, ReviewerSpec, RunMode, RunStatus, Verdict
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
