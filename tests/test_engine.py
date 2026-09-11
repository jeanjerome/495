from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from harness495.core import git
from harness495.core.models import (
    DecisionKind,
    InterventionStatus,
    RequirementStatus,
    Role,
    Run,
    RunMode,
    RunStatus,
    Verdict,
)
from harness495.core.report import render_markdown
from tests.conftest import Scenario, accept_review, bad_producer, good_producer, reject_review


def _create(
    engine: Any, project: Path, config: Any, mode: RunMode = RunMode.change, **kw: Any
) -> Run:
    return engine.create_run("add subtract to calc", project, config, mode, **kw)


def test_full_change_workflow_accepts(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)
    assert run.status is RunStatus.delivered, (run.stop_reason, run.warnings)
    assert run.result.outcome is Verdict.accept
    assert [r.status for r in run.spec.requirements] == [RequirementStatus.satisfied] * 2
    # Readiness ran the project's test command on the base version.
    assert run.profile is not None and run.profile.readiness[0].executable
    # Roles were mobilised in order: specifier, producer, 2 reviewers.
    assert [t.role for t in scenario.calls] == [
        Role.specifier,
        Role.producer,
        Role.reviewer,
        Role.reviewer,
    ]
    # Reviewers received only the diff, spec, evidence: never the producer transcript.
    reviewer_prompt = scenario.calls[2].prompt
    assert "Untrusted content" in reviewer_prompt and "git diff base..head" in reviewer_prompt
    assert "fake transcript" not in reviewer_prompt and "Established facts" in reviewer_prompt
    # Exact version: a commit on the run branch, patch hash recorded, evidence bound to it.
    it = run.current_iteration
    assert it and it.version and it.version.head_commit and it.version.patch_sha256
    assert it.version.branch == f"495/{run.id}"
    assert all(
        e.subject_version == it.version.head_commit
        for e in run.evidence
        if e.kind.value == "command_result"
    )
    assert sorted(it.version.files_changed) == ["calc.py", "tests/test_calc.py"]
    # Evidence: scope ok, V1 and V2 passed, two review verdicts.
    kinds = [e.kind.value for e in run.evidence]
    assert (
        kinds.count("command_result") == 2
        and kinds.count("review_verdict") == 2
        and "scope_check" in kinds
    )
    assert all(e.passed for e in run.evidence if e.kind.value == "command_result")
    # Consumption and cost accounted.
    assert run.consumption.interventions == 4 and run.consumption.cost_usd > 0
    assert run.consumption.cost_basis.value == "reported"
    # Decisions: auto approval + acceptance.
    assert [d.kind for d in run.decisions] == [DecisionKind.approve_spec, DecisionKind.acceptance]
    # Artifacts: patch and report exist and the state validates.
    store = engine.store
    assert store.resolve(run.id, run.result.patch_ref).exists()
    report = render_markdown(run, store)
    assert "## Requirements" in report and "PASS" in report and "git merge --no-ff" in report
    Run.model_validate_json(store.run_path(run.id).read_text())
    events = [e.type for e in store.events(run.id)]
    assert "run.delivered" in events and "version.frozen" in events
    # Nothing was merged into the project; the branch exists.
    assert "subtract" not in (sample_project / "calc.py").read_text()
    assert f"495/{run.id}" in git.git(["branch", "--list", f"495/{run.id}"], sample_project)


def test_rejection_loop_then_accept(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    scenario.producers = [bad_producer, good_producer]
    scenario.reviews["correctness"] = [reject_review("correctness"), accept_review("correctness")]
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)
    assert run.status is RunStatus.delivered and run.result.outcome is Verdict.accept
    assert [i.outcome for i in run.iterations] == [Verdict.reject, Verdict.accept]
    first = run.iterations[0]
    assert any("[R1]" in c for c in first.correction_requests)
    # The failed test output and the findings reached the producer of iteration 2 as untrusted content.
    second_producer = [t for t in scenario.calls if t.role is Role.producer][1]
    assert (
        "Correction requests" in second_producer.prompt
        and "reviewer findings" in second_producer.prompt
    )
    assert run.iterations[1].version.head_commit != first.version.head_commit
    assert len(engine.store.artifacts_dir(run.id).glob("iteration-*.patch").__class__.__name__) > 0


def test_iteration_limit_asks_human(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    scenario.producers = [bad_producer]
    scenario.reviews["correctness"] = [reject_review("correctness")]
    config.budget.max_iterations = 1
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)
    assert run.status is RunStatus.awaiting_decision
    assert run.pending_decision and run.pending_decision.kind is DecisionKind.iteration_limit
    run = engine.decide(run.id, "stop")
    assert run.status is RunStatus.rejected and run.result.outcome is Verdict.reject


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

    def handler(run: Run, pending: Any) -> tuple[str, str]:
        asked.append(pending.kind.value)
        return "approve", ""

    engine = engine_factory(decision_handler=handler)
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)
    assert asked == ["approve_spec"] and run.status is RunStatus.delivered


def test_pause_and_resume(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    original = scenario.next_producer

    def interrupting_producer(cwd: Path) -> None:
        good_producer(cwd)
        engine.request_stop(run.id, "test stop")
        raise KeyboardInterrupt

    scenario.producers = [interrupting_producer]
    run = engine.run(run.id)
    assert run.status is RunStatus.paused and run.resume_status is RunStatus.ready
    assert any(i.status is InterventionStatus.interrupted for i in run.interventions)
    scenario.producers = [good_producer]
    run = engine.run(run.id)
    assert run.status is RunStatus.delivered
    assert [i.n for i in run.iterations] == [1, 2]
    del original


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


def test_scope_violation_is_rejected(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    def out_of_scope(cwd: Path) -> None:
        good_producer(cwd)
        (cwd / "README.md").write_text("changed")

    def back_in_scope(cwd: Path) -> None:
        good_producer(cwd)
        subprocess.run(["git", "checkout", "HEAD~1", "--", "README.md"], cwd=cwd, check=True)

    scenario.producers = [out_of_scope, back_in_scope]
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)
    assert run.iterations[0].outcome is Verdict.reject
    assert any("[scope]" in c and "README.md" in c for c in run.iterations[0].correction_requests)
    assert run.status is RunStatus.delivered and run.iterations[1].outcome is Verdict.accept


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
    assert run.consumption.interventions == 3


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


def test_check_integration(sample_project: Path, config: Any, engine_factory: Any) -> None:
    engine = engine_factory()
    run = engine.run(_create(engine, sample_project, config).id)
    assert run.status is RunStatus.delivered
    run = engine.check_integration(run.id, "HEAD")
    assert (
        run.result.integration
        and not run.result.integration.contains_commit
        and not run.result.integration.files_identical
    )
    subprocess.run(
        ["git", "merge", "-q", "--no-ff", "-m", "merge", f"495/{run.id}"],
        cwd=sample_project,
        check=True,
        env={
            **__import__("os").environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )
    run = engine.check_integration(run.id, "HEAD", rerun_verifications=True)
    ic = run.result.integration
    assert ic and ic.contains_commit and ic.files_identical and ic.verifications_passed is True
    engine.cleanup_worktree(run.id)
    assert not engine.worktree_path(run).exists()


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


def test_verification_blind_to_the_change_is_not_turned_into_a_correction(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    """A command that fails with and without the change accuses the spec, not the producer."""
    import sys

    scenario.spec["verifications"][0]["command"] = (
        f'{sys.executable} -c "import module_that_never_existed"'
    )
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)

    assert run.status is RunStatus.awaiting_decision
    assert run.pending_decision and run.pending_decision.kind is DecisionKind.instrument_fault
    it = run.current_iteration
    assert it and it.instrument_faults and it.instrument_faults[0].startswith("V1:")
    # The control run is kept as evidence, on the base version rather than on the change.
    control = [e for e in run.evidence if e.kind.value == "instrument_check"]
    assert len(control) == 1 and control[0].subject_version == run.profile.base_commit
    # R1 is undetermined, not violated, and nobody was asked to make the command pass.
    assert run.spec.requirements[0].status is RequirementStatus.undetermined
    assert not any("not demonstrated: V1" in c for c in it.correction_requests)

    run = engine.decide(run.id, "respecify", "V1 never reaches the new code")
    assert run.status is RunStatus.profiled and not run.spec.approved


def test_an_iteration_that_changes_nothing_stops_instead_of_being_reviewed_again(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    scenario.producers = [bad_producer, bad_producer]
    scenario.reviews["correctness"] = [reject_review("correctness")]
    scenario.producer_not_done = ["V1 cannot pass without editing files outside the scope"]
    config.budget.max_iterations = 3
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)

    assert run.status is RunStatus.awaiting_decision
    assert run.pending_decision and run.pending_decision.kind is DecisionKind.no_progress
    # Two productions, but only the first version was verified and reviewed.
    assert sum(1 for t in scenario.calls if t.role is Role.producer) == 2
    assert len(run.iterations) == 2
    assert run.iterations[0].version.patch_sha256 == run.iterations[1].version.patch_sha256
    assert run.iterations[1].review_ids == []
    # What the producer said it could not do reaches the human, unverified and labelled as such.
    assert run.iterations[1].blocked_claims == scenario.producer_not_done
    # The question stays one sentence; the claim itself travels in the decision's context.
    assert run.pending_decision.context["blocked_claims"] == scenario.producer_not_done
    assert len(run.pending_decision.question) < 200
    assert all(o.consequence for o in run.pending_decision.options)

    run = engine.decide(run.id, "stop")
    assert run.status is RunStatus.rejected


def test_correction_prompt_carries_observations_not_the_reviewer_s_conclusions(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    scenario.producers = [bad_producer, good_producer]
    scenario.reviews["correctness"] = [reject_review("correctness"), accept_review("correctness")]
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)

    corrective = [t for t in scenario.calls if t.role is Role.producer][1].prompt
    # The claim and where to look travel; the reviewer's fix does not.
    assert "subtract adds instead of subtracting" in corrective
    assert "calc.py:8" in corrective
    assert "use a - b" not in corrective
    # Nothing in the prompt tells the producer to chase an exit code.
    assert "make verification pass" not in corrective
    assert "not demonstrated" in corrective or "observed:" in corrective


def test_ignoring_a_blind_verification_holds_for_the_rest_of_the_run(
    sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    import sys

    scenario.spec["verifications"][0]["command"] = (
        f'{sys.executable} -c "import module_that_never_existed"'
    )
    scenario.producers = [bad_producer, good_producer]
    engine = engine_factory()
    run = _create(engine, sample_project, config)
    run = engine.run(run.id)
    assert run.pending_decision and run.pending_decision.kind is DecisionKind.instrument_fault

    run = engine.decide(run.id, "ignore")
    run = engine.run(run.id)
    # The question is not put again, and the blind command never becomes a correction request.
    assert sum(1 for d in run.decisions if d.kind is DecisionKind.instrument_fault) == 1, [
        d.kind.value for d in run.decisions
    ]
    assert all(not any("V1" in c for c in it.correction_requests) for it in run.iterations), [
        it.correction_requests for it in run.iterations
    ]
    assert run.status in (RunStatus.undetermined, RunStatus.awaiting_decision, RunStatus.delivered)


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
