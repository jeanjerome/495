from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from harness495.core import git
from harness495.core.models import (
    DecisionAnswer,
    DecisionKind,
    EvidenceKind,
    InterventionStatus,
    RequirementStatus,
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


def test_undetermined_refuses_to_conclude(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    # Remove the automated verification of R1: only a review remains -> insufficient.
    scenario.spec["verifications"][0] = {
        "id": "V1",
        "kind": "review",
        "description": "eyeball it",
        "command": None,
        "to_create": False,
    }
    config.auto_approve = False
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)
    assert (
        run.status is RunStatus.awaiting_decision
        and run.pending_decision.kind is DecisionKind.approve_spec
    )
    assert run.spec.gaps and "R1" in run.spec.gaps[0]
    assert "approve_with_gaps" in {o.key for o in run.pending_decision.options}
    run = engine.decide(run.id, "approve_with_gaps")
    run = engine.run(run.id)
    assert (
        run.status is RunStatus.awaiting_decision
        and run.pending_decision.kind is DecisionKind.undetermined
    )
    assert run.spec.requirement("R1").status is RequirementStatus.undetermined
    assert run.result.outcome is Verdict.undetermined
    run = engine.decide(run.id, "accept_with_risk", note="reviewed by hand")
    run = engine.run(run.id)
    assert run.status is RunStatus.delivered
    assert any(
        d.made_by.value == "human" and d.outcome == "accept_with_risk" for d in run.decisions
    )


def test_decision_handler_answers_inline(
    sample_project: Path, config: Any, engine_factory: Any
) -> None:
    config.auto_approve = False
    asked: list[str] = []

    def handler(run: Run, pending: Any) -> DecisionAnswer:
        asked.append(pending.kind.value)
        return DecisionAnswer(choice="approve")

    engine = engine_factory(decision_handler=handler)
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)
    assert asked == ["approve_spec"] and run.status is RunStatus.delivered


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


def test_budget_exhaustion_asks_human(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    config.budget.max_cost_usd = 0.015  # one intervention of 0.01 fits, the second does not
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)
    assert (
        run.status is RunStatus.awaiting_decision
        and run.pending_decision.kind is DecisionKind.budget
    )
    run = engine.decide(run.id, "raise", note="1.0")
    run = engine.run(run.id)
    assert run.status is RunStatus.delivered and run.budget.max_cost_usd > 1.0


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


def test_readiness_failure_asks_and_drop_continues(
    sample_project: Path, config: Any, engine_factory: Any
) -> None:
    (sample_project / ".495" / "project.toml").write_text(
        '[[commands]]\nname = "test"\ncommand = "definitely-missing-tool --run"\nkind = "test"\n'
    )
    from harness495.core.config import load_config

    cfg = load_config(sample_project)
    cfg.agents = config.agents
    cfg.roles = config.roles
    cfg.auto_approve = True
    engine = engine_factory()
    run = _create(engine, sample_project, cfg)
    run = engine.run(run.id)
    assert (
        run.status is RunStatus.awaiting_decision
        and run.pending_decision.kind is DecisionKind.readiness
    )
    run = engine.decide(run.id, "drop")
    run = engine.run(run.id)
    assert run.profile is not None and run.profile.commands == []
    assert run.status in (RunStatus.delivered, RunStatus.awaiting_decision)


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


def test_the_specification_is_readable_when_approval_is_asked(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    """Being asked to approve something you cannot see is the one thing the gate must not do."""
    config.auto_approve = False
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)

    assert run.pending_decision and run.pending_decision.kind is DecisionKind.approve_spec
    # On disk, at a path the question names.
    assert run.spec.artifact_ref
    path = engine.store.resolve(run.id, run.spec.artifact_ref)
    assert path.exists()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert [r["id"] for r in written["requirements"]] == ["R1", "R2"]
    assert str(path) in run.pending_decision.question
    # And in the decision itself, for whoever reads it as JSON rather than in a terminal.
    context_spec = run.pending_decision.context["spec"]
    assert [r["id"] for r in context_spec["requirements"]] == ["R1", "R2"]
    assert run.pending_decision.context["spec_path"] == str(path)


def test_a_red_baseline_can_be_answered_by_opening_the_network(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    """A build that resolves its dependencies on first use fails offline and nowhere else."""
    (sample_project / "tests" / "test_calc.py").write_text(
        "import os\n\n\ndef test_needs_network():\n    assert os.environ.get('HARNESS495_NET') == '1'\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "red"],
        cwd=sample_project,
        check=True,
        capture_output=True,
    )
    config.auto_approve = False
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)

    assert run.pending_decision and run.pending_decision.kind is DecisionKind.readiness
    keys = [o.key for o in run.pending_decision.options]
    assert keys == ["proceed", "allow_network", "retry", "abort"]
    assert all(o.consequence for o in run.pending_decision.options)
    assert run.pending_decision.context["allow_network"] is False
    # The baseline output is kept, so the failure can be read rather than guessed at.
    baseline = [e for e in run.evidence if e.kind.value == "baseline"]
    assert baseline and baseline[0].output_ref
    assert "test_needs_network" in engine.store.read_text(run.id, baseline[0].output_ref)

    run = engine.decide(run.id, "allow_network")
    assert run.config.sandbox.allow_network is True
    assert run.status is RunStatus.created  # readiness runs again, this time with the network
    assert any("network access" in w for w in run.warnings)

    # The network is open now, so if the command still fails the question comes back without
    # an option that has already been taken.
    run = engine.run(run.id)
    assert run.pending_decision and run.pending_decision.kind is DecisionKind.readiness
    assert [o.key for o in run.pending_decision.options] == ["proceed", "retry", "abort"]
    assert "sandbox denies network access" not in run.pending_decision.question
    assert run.pending_decision.context["allow_network"] is True

    run = engine.decide(run.id, "proceed")
    assert run.status is RunStatus.profiled


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


def test_every_command_is_run_once_before_the_specification_is_approved(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    """Judged by nobody: the output is on file for whoever answers the approval question."""
    config.auto_approve = False
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)

    assert run.pending_decision and run.pending_decision.kind is DecisionKind.approve_spec
    preflight = [e for e in run.evidence if e.kind is EvidenceKind.baseline and e.verification_id]
    # V2 is the project's own command, already run at readiness; V1 is the invented one.
    assert [e.verification_id for e in preflight] == ["V1"]
    assert preflight[0].passed is None and preflight[0].output_ref
    assert "V1 exits 0 on the base version" in run.pending_decision.question or (
        "V1 exits" in run.pending_decision.question
    )
    assert run.pending_decision.context["preflight"][0]["verification"] == "V1"

    run = engine.decide(run.id, "approve")
    run = engine.run(run.id)
    assert run.status is RunStatus.delivered
