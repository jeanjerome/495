from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from harness495.core import git
from harness495.core.models import (
    DecisionKind,
    InterventionStatus,
    Role,
    Run,
    RunMode,
    RunStatus,
    Verdict,
)
from harness495.core.store import DRIVER_FLAG, RunBusy
from tests.conftest import Scenario, good_producer


def _create(
    engine: Any, project: Path, config: Any, mode: RunMode = RunMode.change, **kw: Any
) -> Run:
    return engine.create_run("add subtract to calc", project, config, mode, **kw)


def test_reviewer_tampering_discards_verdict(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    def tamper(task: Any) -> None:
        (task.cwd / "calc.py").write_text("tampered")

    scenario.reviewer_hook = tamper
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)
    assert all(rv.discarded for rv in run.reviews)
    assert all(
        i.status is InterventionStatus.tampered
        for i in run.interventions
        if i.role is Role.reviewer
    )
    assert (
        run.status is RunStatus.awaiting_decision
        and run.pending_decision.kind is DecisionKind.undetermined
    )
    wt = engine.worktree_path(run)
    assert "tampered" not in (wt / "calc.py").read_text()


def test_evaluate_mode_reviews_existing_commit(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    # Commit a change directly in the project, then evaluate it without a producer.
    good_producer(sample_project)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "add subtract"],
        cwd=sample_project,
        check=True,
    )
    head = git.head_commit(sample_project)
    engine = engine_factory()
    run = _create(engine, sample_project, config, RunMode.evaluate, evaluate_ref=head)
    run = engine.run(run.id)
    assert run.status is RunStatus.delivered and run.result.outcome is Verdict.accept
    assert Role.producer not in [t.role for t in scenario.calls]
    assert run.iterations[0].version.head_commit == head
    # The clarifier, the specifier, the two configured reviewers, and test_quality for the
    # test to create.
    assert run.consumption.interventions == 5


def test_evaluate_working_tree_and_patch(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    good_producer(sample_project)  # uncommitted changes in the working tree
    engine = engine_factory()
    run = _create(engine, sample_project, config, RunMode.evaluate, evaluate_ref="WORKTREE")
    run = engine.run(run.id)
    assert run.status is RunStatus.delivered
    assert sorted(run.iterations[0].version.files_changed) == ["calc.py", "tests/test_calc.py"]
    patch = engine.store.resolve(run.id, run.result.patch_ref)
    subprocess.run(["git", "checkout", "--", "."], cwd=sample_project, check=True)
    run2 = _create(
        engine_factory(), sample_project, config, RunMode.evaluate, evaluate_ref=f"patch:{patch}"
    )
    run2 = engine_factory().run(run2.id)
    assert run2.status is RunStatus.delivered and run2.result.outcome is Verdict.accept


def test_worktree_is_outside_project_and_escape_is_detected(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    wt = engine.worktree_path(run)
    assert not str(wt).startswith(str(sample_project))
    assert run.worktree == str(wt)

    def escaping_producer(cwd: Path) -> None:
        good_producer(cwd)
        (sample_project / "calc.py").write_text("escaped")

    scenario.producers = [escaping_producer]
    run = engine.run(run.id)
    assert (
        run.status is RunStatus.failed
        and "escaped" in (run.stop_reason or "")
        or "modified the project" in (run.stop_reason or "")
    )
    assert any(e.kind.value == "integrity" and e.passed is False for e in run.evidence)
    assert any(
        i.status is InterventionStatus.tampered
        for i in run.interventions
        if i.role is Role.producer
    )
    # The user's tree is left for inspection, nothing was committed on their behalf.
    assert (sample_project / "calc.py").read_text() == "escaped"


def test_a_run_being_advanced_elsewhere_is_refused_not_joined(
    sample_project: Path, config: Any, engine_factory: Any
) -> None:
    """Two engines stepping one run write the same document from two phases; the last wins."""
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    (engine.store.run_dir(run.id) / DRIVER_FLAG).write_text(
        json.dumps({"pid": 1, "host": socket.gethostname(), "label": "495 run", "since": "now"}),
        encoding="utf-8",
    )
    try:
        with pytest.raises(RunBusy):
            engine.run(run.id)
        assert engine.store.load(run.id).status is RunStatus.created
    finally:
        (engine.store.run_dir(run.id) / DRIVER_FLAG).unlink()
    assert engine.run(run.id).status is RunStatus.delivered


def test_the_claim_is_given_back_when_the_run_blocks(
    sample_project: Path, config: Any, engine_factory: Any
) -> None:
    config.auto_approve = False
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)
    assert run.status is RunStatus.awaiting_decision
    assert not (engine.store.run_dir(run.id) / DRIVER_FLAG).exists()
