"""Scenarios of ``tests/features/workflow.feature``: the walk ``core/engine/engine.py`` makes
from an intent to a change it accepts, or stops on.

The steps script the fake agents of ``tests/conftest.py``, carry one run out over the sample
project, and read the run document, the interventions' prompts, the evidence and the store
back. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core import git
from harness495.core.engine import Engine
from harness495.core.models import (
    DecisionKind,
    HarnessConfig,
    InterventionStatus,
    Iteration,
    PendingDecision,
    RequirementStatus,
    Role,
    Run,
    RunMode,
    RunStatus,
    Verdict,
)
from harness495.core.report import render_markdown
from tests.conftest import (
    Scenario,
    accept_review,
    bad_producer,
    good_producer,
    reject_review,
)

scenarios("features/workflow.feature")

INTENT = "add subtract to calc"


@dataclass
class Walk:
    """One run over the sample project, and the scripted agents that walk it."""

    project: Path
    config: HarnessConfig
    script: Scenario
    engine: Engine
    run_id: str = ""

    @property
    def run(self) -> Run:
        return self.engine.store.load(self.run_id)

    @property
    def iteration_one(self) -> Iteration:
        return self.run.iterations[0]

    def carry_out(self) -> None:
        if not self.run_id:
            self.run_id = self.engine.create_run(
                INTENT, self.project, self.config, RunMode.change
            ).id
        self.engine.run(self.run_id)

    def prompts(self, role: Role) -> list[str]:
        return [task.prompt for task in self.script.calls if task.role is role]

    def pending(self) -> PendingDecision:
        found = self.run.pending_decision
        assert found is not None, "the run stopped on no question"
        return found


@given("a project 495 can work in", target_fixture="world")
def a_project_495_can_work_in(
    sample_project: Path,
    config: HarnessConfig,
    scenario: Scenario,
    engine_factory: Callable[..., Engine],
) -> Walk:
    return Walk(sample_project, config, scenario, engine_factory())


# ----------------------------------------------------------------- what the agents will do


@given("the producer writes a wrong version, then a good one")
def the_producer_writes_a_wrong_then_a_good_version(world: Walk) -> None:
    world.script.producers = [bad_producer, good_producer]


@given("the producer writes a wrong version")
def the_producer_writes_a_wrong_version(world: Walk) -> None:
    world.script.producers = [bad_producer]


@given("the producer writes the same wrong version twice")
def the_producer_writes_the_same_version_twice(world: Walk) -> None:
    world.script.producers = [bad_producer, bad_producer]


@given("the producer writes outside the allowed paths, then back inside them")
def the_producer_writes_out_of_scope_then_back(world: Walk) -> None:
    def out_of_scope(cwd: Path) -> None:
        good_producer(cwd)
        (cwd / "README.md").write_text("changed")

    def back_in_scope(cwd: Path) -> None:
        good_producer(cwd)
        subprocess.run(["git", "checkout", "HEAD~1", "--", "README.md"], cwd=cwd, check=True)

    world.script.producers = [out_of_scope, back_in_scope]


@given("the producer is interrupted after writing the change")
def the_producer_is_interrupted(world: Walk) -> None:
    def interrupting_producer(cwd: Path) -> None:
        good_producer(cwd)
        world.engine.request_stop(world.run_id, "test stop")
        raise KeyboardInterrupt

    world.script.producers = [interrupting_producer]


@given(parsers.parse('the producer says it is blocked by "{claim}"'))
def the_producer_says_it_is_blocked(world: Walk, claim: str) -> None:
    world.script.producer_not_done = [claim]


@given("the correctness reviewer rejects the first version, then accepts")
def the_correctness_reviewer_rejects_then_accepts(world: Walk) -> None:
    world.script.reviews["correctness"] = [
        reject_review("correctness"),
        accept_review("correctness"),
    ]


@given("the correctness reviewer rejects the change")
def the_correctness_reviewer_rejects(world: Walk) -> None:
    world.script.reviews["correctness"] = [reject_review("correctness")]


@given(parsers.parse("the iteration limit is {limit:d}"))
def the_iteration_limit_is(world: Walk, limit: int) -> None:
    world.config.budget.max_iterations = limit


# ----------------------------------------------------------------- carrying the run out


@when("the run is carried out")
def the_run_is_carried_out(world: Walk) -> None:
    world.carry_out()


@when("the producer is put back to normal and the run is carried out again")
def the_run_is_carried_out_again(world: Walk) -> None:
    world.script.producers = [good_producer]
    world.carry_out()


@when(parsers.parse('the requester answers "{choice}"'))
def the_requester_answers(world: Walk, choice: str) -> None:
    world.engine.decide(world.run_id, choice)


# ----------------------------------------------------------------- where the run ended up


@then("the run is delivered, and accepted")
def the_run_is_delivered_and_accepted(world: Walk) -> None:
    run = world.run
    assert run.status is RunStatus.delivered, (run.stop_reason, run.warnings)
    assert run.result.outcome is Verdict.accept


@then("the run is delivered")
def the_run_is_delivered(world: Walk) -> None:
    run = world.run
    assert run.status is RunStatus.delivered, (run.stop_reason, run.warnings)


@then("the run is rejected")
def the_run_is_rejected(world: Walk) -> None:
    assert world.run.status is RunStatus.rejected


@then("the run is rejected, with the outcome reject")
def the_run_is_rejected_with_the_outcome(world: Walk) -> None:
    run = world.run
    assert run.status is RunStatus.rejected and run.result.outcome is Verdict.reject


@then("the run is paused, and will resume as ready")
def the_run_is_paused(world: Walk) -> None:
    run = world.run
    assert run.status is RunStatus.paused and run.resume_status is RunStatus.ready


@then(parsers.re(r'the run stops on an? "(?P<kind>\w+)" question'))
def the_run_stops_on_a_question(world: Walk, kind: str) -> None:
    run = world.run
    assert run.status is RunStatus.awaiting_decision
    assert world.pending().kind is DecisionKind(kind)


@then("every requirement is satisfied")
def every_requirement_is_satisfied(world: Walk) -> None:
    statuses = [r.status for r in world.run.spec.requirements]
    assert statuses == [RequirementStatus.satisfied] * 2


# ----------------------------------------------------------------- what the walk left behind


@then("the project's own test command was run on the base version")
def the_project_command_ran_on_the_base_version(world: Walk) -> None:
    profile = world.run.profile
    assert profile is not None and profile.readiness[0].executable


@then(parsers.parse("the roles were called in order: {names}"))
def the_roles_were_called_in_order(world: Walk, names: str) -> None:
    expected = [Role(name.strip()) for name in names.split(",")]
    assert [task.role for task in world.script.calls] == expected


@then(
    "a reviewer was given the diff and the established facts, and never the producer's transcript"
)
def a_reviewer_was_given_the_diff_and_the_facts(world: Walk) -> None:
    prompt = world.prompts(Role.reviewer)[0]
    assert "Untrusted content" in prompt and "git diff base..head" in prompt
    assert "Established facts" in prompt and "fake transcript" not in prompt


@then("the change is a commit on the run's own branch, with the fingerprint of its patch")
def the_change_is_a_commit_on_the_run_branch(world: Walk) -> None:
    run = world.run
    iteration = run.current_iteration
    assert iteration is not None and iteration.version is not None
    assert iteration.version.head_commit and iteration.version.patch_sha256
    assert iteration.version.branch == f"495/{run.id}"


@then("every command result is bound to that commit")
def every_command_result_is_bound_to_that_commit(world: Walk) -> None:
    run = world.run
    iteration = run.current_iteration
    assert iteration is not None and iteration.version is not None
    assert all(
        e.subject_version == iteration.version.head_commit
        for e in run.evidence
        if e.kind.value == "command_result"
    )


@then(parsers.parse("the change touched {names}"))
def the_change_touched(world: Walk, names: str) -> None:
    iteration = world.run.current_iteration
    assert iteration is not None and iteration.version is not None
    expected = sorted(name.strip() for name in names.replace(" and ", ", ").split(","))
    assert sorted(iteration.version.files_changed) == expected


@then(parsers.parse("the test designer is recorded as having written {path}"))
def the_test_designer_wrote(world: Walk, path: str) -> None:
    design = world.run.test_design
    assert design is not None and design.files == [path]


@then(
    parsers.parse(
        "the evidence holds {commands:d} command results, {reviews:d} review verdicts "
        "and a scope check"
    )
)
def the_evidence_holds(world: Walk, commands: int, reviews: int) -> None:
    kinds = [e.kind.value for e in world.run.evidence]
    assert kinds.count("command_result") == commands
    assert kinds.count("review_verdict") == reviews
    assert "scope_check" in kinds


@then("every command that ran reported success")
def every_command_reported_success(world: Walk) -> None:
    assert all(e.passed for e in world.run.evidence if e.kind.value == "command_result")


@then(parsers.parse("{count:d} interventions were charged, at a cost the agents reported"))
def interventions_were_charged(world: Walk, count: int) -> None:
    consumption = world.run.consumption
    assert consumption.interventions == count and consumption.cost_usd > 0
    assert consumption.cost_basis.value == "reported"


@then(parsers.parse("the decisions taken were: {names}"))
def the_decisions_taken_were(world: Walk, names: str) -> None:
    expected = [DecisionKind(name.strip()) for name in names.split(",")]
    assert [d.kind for d in world.run.decisions] == expected


@then("the patch and the report are on disk, and the run document validates against its schema")
def the_artefacts_are_on_disk(world: Walk) -> None:
    run, store = world.run, world.engine.store
    assert store.resolve(run.id, run.result.patch_ref).exists()
    report = render_markdown(run, store)
    assert "## Requirements" in report and "PASS" in report and "git merge --no-ff" in report
    assert Run.model_validate_json(store.run_path(run.id).read_text()).id == run.id


@then(parsers.parse("the events name {first} and {second}"))
def the_events_name(world: Walk, first: str, second: str) -> None:
    types = [e.type for e in world.engine.store.events(world.run_id)]
    assert first in types and second in types


@then("nothing was merged into the project, and the run's branch is there")
def nothing_was_merged_into_the_project(world: Walk) -> None:
    branch = f"495/{world.run_id}"
    assert "subtract" not in (world.project / "calc.py").read_text()
    assert branch in git.git(["branch", "--list", branch], world.project)


# ----------------------------------------------------------------- the correction loop


@then(parsers.parse("the iterations came out: {outcomes}"))
def the_iterations_came_out(world: Walk, outcomes: str) -> None:
    expected = [Verdict(name.strip()) for name in outcomes.split(",")]
    assert [i.outcome for i in world.run.iterations] == expected


@then(parsers.parse("a correction request of the first iteration names the requirement {rid}"))
def a_correction_request_of_the_first_iteration_names(world: Walk, rid: str) -> None:
    assert any(f"[{rid}]" in c for c in world.iteration_one.correction_requests)


@then("a correction request of the first iteration names the scope and README.md")
def a_correction_request_names_the_scope(world: Walk) -> None:
    requests = world.iteration_one.correction_requests
    assert any("[scope]" in c and "README.md" in c for c in requests)


@then("the second producer was given the correction requests and the reviewer findings")
def the_second_producer_was_given_the_corrections(world: Walk) -> None:
    prompt = world.prompts(Role.producer)[1]
    assert "Correction requests" in prompt and "reviewer findings" in prompt


@then(parsers.parse('the second producer was told "{text}"'))
def the_second_producer_was_told(world: Walk, text: str) -> None:
    assert text in world.prompts(Role.producer)[1]


@then(parsers.parse('the second producer was not told "{text}"'))
def the_second_producer_was_not_told(world: Walk, text: str) -> None:
    assert text not in world.prompts(Role.producer)[1]


@then("the second producer was told what is not demonstrated, or what was observed")
def the_second_producer_was_told_the_claim(world: Walk) -> None:
    prompt = world.prompts(Role.producer)[1]
    assert "not demonstrated" in prompt or "observed:" in prompt


@then("the second version is a different commit from the first")
def the_second_version_is_a_different_commit(world: Walk) -> None:
    first, second = world.run.iterations[0], world.run.iterations[1]
    assert first.version is not None and second.version is not None
    assert second.version.head_commit != first.version.head_commit


@then("a patch is on disk for each iteration")
def a_patch_is_on_disk_for_each_iteration(world: Walk) -> None:
    patches = sorted(p.name for p in world.engine.store.artifacts_dir(world.run_id).glob("*.patch"))
    assert patches == [f"iteration-{i.n}.patch" for i in world.run.iterations]


@then("the first iteration was rejected")
def the_first_iteration_was_rejected(world: Walk) -> None:
    assert world.iteration_one.outcome is Verdict.reject


@then("the run is delivered, the second iteration accepted")
def the_run_is_delivered_the_second_iteration_accepted(world: Walk) -> None:
    run = world.run
    assert run.status is RunStatus.delivered and run.iterations[1].outcome is Verdict.accept


# ----------------------------------------------------------------- a run going nowhere


@then("the producer was called twice")
def the_producer_was_called_twice(world: Walk) -> None:
    assert len(world.prompts(Role.producer)) == 2


@then(parsers.parse("the run holds {n:d} iterations"))
def the_run_holds_iterations(world: Walk, n: int) -> None:
    assert len(world.run.iterations) == n


@then("the two versions carry the same patch fingerprint")
def the_two_versions_carry_the_same_fingerprint(world: Walk) -> None:
    first, second = world.run.iterations[0], world.run.iterations[1]
    assert first.version is not None and second.version is not None
    assert first.version.patch_sha256 == second.version.patch_sha256


@then("the second iteration was read by no reviewer")
def the_second_iteration_was_read_by_nobody(world: Walk) -> None:
    assert world.run.iterations[1].review_ids == []


@then(
    "what the producer said it could not do reaches the requester, "
    "in the iteration and in the question"
)
def the_blocked_claim_reaches_the_requester(world: Walk) -> None:
    claims = world.script.producer_not_done
    assert world.run.iterations[1].blocked_claims == claims
    assert world.pending().context["blocked_claims"] == claims


@then("the question is one sentence, and every option says what it does to the run")
def the_question_is_one_sentence(world: Walk) -> None:
    pending = world.pending()
    assert len(pending.question) < 200
    assert all(o.consequence for o in pending.options)


# ----------------------------------------------------------------- pausing


@then("one intervention is recorded as interrupted")
def one_intervention_is_interrupted(world: Walk) -> None:
    statuses = [i.status for i in world.run.interventions]
    assert statuses.count(InterventionStatus.interrupted) == 1


@then(parsers.parse("the iterations are numbered {numbers}"))
def the_iterations_are_numbered(world: Walk, numbers: str) -> None:
    assert [i.n for i in world.run.iterations] == [int(n) for n in numbers.split(",")]
