"""Scenarios of ``tests/features/workflow.feature`` and ``tests/features/questions.feature``:
the walk ``core/engine/engine.py`` makes from an intent to a change it accepts, and the
questions it stops on when it cannot make that walk alone.

The steps script the fake agents of ``tests/conftest.py``, carry one run out over the sample
project, answer what it asks, and read the run document, the interventions' prompts, the
evidence and the store back. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core import git
from harness495.core.config import load_config
from harness495.core.engine import Engine
from harness495.core.models import (
    DecisionAnswer,
    DecisionKind,
    EvidenceKind,
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

scenarios("features/workflow.feature", "features/questions.feature")

INTENT = "add subtract to calc"


@dataclass
class Walk:
    """One run over the sample project, and the scripted agents that walk it."""

    project: Path
    config: HarnessConfig
    script: Scenario
    engines: Callable[..., Engine]
    run_id: str = ""
    asked: list[str] = field(default_factory=list)
    built: Engine | None = None

    @property
    def engine(self) -> Engine:
        """The engine of this run, built on first use so a handler can be given to it."""
        if self.built is None:
            self.built = self.engines()
        return self.built

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
    return Walk(sample_project, config, scenario, engine_factory)


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


@when(parsers.re(r'the requester answers "(?P<choice>[^"]+)"'))
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


# ----------------------------------------------------------------- what the run is asked


@given("approval is not automatic")
def approval_is_not_automatic(world: Walk) -> None:
    world.config.auto_approve = False


@given("the only verification of R1 is a review")
def the_only_verification_of_r1_is_a_review(world: Walk) -> None:
    world.script.spec["verifications"][0] = {
        "id": "V1",
        "kind": "review",
        "description": "eyeball it",
        "command": None,
        "to_create": False,
    }


@given(parsers.parse('a handler that answers every question with "{choice}"'))
def a_handler_answering_every_question(world: Walk, choice: str) -> None:
    def handler(run: Run, pending: PendingDecision) -> DecisionAnswer:
        world.asked.append(pending.kind.value)
        return DecisionAnswer(choice=choice)

    world.built = world.engines(decision_handler=handler)


@given("a budget one intervention fits into and two do not")
def a_budget_one_intervention_fits_into(world: Walk) -> None:
    world.config.budget.max_cost_usd = 0.015


@given("the project's test command is a tool that is not installed")
def the_test_command_is_a_missing_tool(world: Walk) -> None:
    (world.project / ".495" / "project.toml").write_text(
        '[[commands]]\nname = "test"\ncommand = "definitely-missing-tool --run"\nkind = "test"\n'
    )
    reloaded = load_config(world.project)
    reloaded.agents = world.config.agents
    reloaded.roles = world.config.roles
    reloaded.auto_approve = True
    world.config = reloaded


@given("the project's test command passes only with the network open")
def the_test_command_needs_the_network(world: Walk) -> None:
    (world.project / "tests" / "test_calc.py").write_text(
        "import os\n\n\ndef test_needs_network():\n"
        "    assert os.environ.get('HARNESS495_NET') == '1'\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "red"],
        cwd=world.project,
        check=True,
        capture_output=True,
    )


@when(parsers.re(r'the requester answers "(?P<choice>[^"]+)", and the run is carried out'))
def the_requester_answers_and_the_run_goes_on(world: Walk, choice: str) -> None:
    world.engine.decide(world.run_id, choice)
    world.carry_out()


@when(
    parsers.re(
        r'the requester answers "(?P<choice>[^"]+)" saying "(?P<note>[^"]*)", '
        r"and the run is carried out"
    )
)
def the_requester_answers_with_a_note(world: Walk, choice: str, note: str) -> None:
    world.engine.decide(world.run_id, choice, note=note)
    world.carry_out()


@then("the specification is on disk, holding R1 and R2")
def the_specification_is_on_disk(world: Walk) -> None:
    run = world.run
    assert run.spec.artifact_ref
    path = world.engine.store.resolve(run.id, run.spec.artifact_ref)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert [r["id"] for r in written["requirements"]] == ["R1", "R2"]


@then("the question names the path the specification is at")
def the_question_names_the_path(world: Walk) -> None:
    run = world.run
    path = world.engine.store.resolve(run.id, run.spec.artifact_ref)
    pending = world.pending()
    assert str(path) in pending.question
    assert pending.context["spec_path"] == str(path)


@then("the question carries the specification itself, holding R1 and R2")
def the_question_carries_the_specification(world: Walk) -> None:
    carried = world.pending().context["spec"]
    assert [r["id"] for r in carried["requirements"]] == ["R1", "R2"]


@then("the only verification run on the base version is V1")
def the_only_preflight_is_v1(world: Walk) -> None:
    preflight = [
        e for e in world.run.evidence if e.kind is EvidenceKind.baseline and e.verification_id
    ]
    assert [e.verification_id for e in preflight] == ["V1"]


@then("what it reported is judged by nobody, and kept under a reference")
def the_preflight_is_judged_by_nobody(world: Walk) -> None:
    preflight = [
        e for e in world.run.evidence if e.kind is EvidenceKind.baseline and e.verification_id
    ]
    assert preflight[0].passed is None and preflight[0].output_ref


@then("the question says what V1 did on the base version")
def the_question_says_what_v1_did(world: Walk) -> None:
    assert "V1 exits" in world.pending().question


@then("the question carries the preflight, naming V1")
def the_question_carries_the_preflight(world: Walk) -> None:
    assert world.pending().context["preflight"][0]["verification"] == "V1"


@then(parsers.parse('the handler was asked the "{kind}" question, and nothing else'))
def the_handler_was_asked(world: Walk, kind: str) -> None:
    assert world.asked == [kind]


@then("the specification names R1 as a gap")
def the_specification_names_a_gap(world: Walk) -> None:
    gaps = world.run.spec.gaps
    assert gaps and "R1" in gaps[0]


@then(parsers.parse('the answer "{key}" is among those offered'))
def the_answer_is_among_those_offered(world: Walk, key: str) -> None:
    assert key in {o.key for o in world.pending().options}


@then(parsers.parse("the answers offered are: {keys}"))
def the_answers_offered_are(world: Walk, keys: str) -> None:
    assert [o.key for o in world.pending().options] == [k.strip() for k in keys.split(",")]


@then("every answer says what it does to the run")
def every_answer_says_what_it_does(world: Walk) -> None:
    assert all(o.consequence for o in world.pending().options)


@then("the requirement R1 is undetermined")
def the_requirement_r1_is_undetermined(world: Walk) -> None:
    requirement = world.run.spec.requirement("R1")
    assert requirement is not None
    assert requirement.status is RequirementStatus.undetermined


@then("the outcome is undetermined")
def the_outcome_is_undetermined(world: Walk) -> None:
    assert world.run.result.outcome is Verdict.undetermined


@then(parsers.parse('the decision is recorded as taken by a human, answering "{choice}"'))
def the_decision_is_recorded_as_human(world: Walk, choice: str) -> None:
    assert any(d.made_by.value == "human" and d.outcome == choice for d in world.run.decisions)


@then(parsers.parse("the budget now stands above {amount:f} dollars"))
def the_budget_now_stands_above(world: Walk, amount: float) -> None:
    assert world.run.budget.max_cost_usd > amount


@then("the profile holds no command")
def the_profile_holds_no_command(world: Walk) -> None:
    profile = world.run.profile
    assert profile is not None and profile.commands == []


@then("the run carried on past the gate")
def the_run_carried_on_past_the_gate(world: Walk) -> None:
    assert world.run.status in (RunStatus.delivered, RunStatus.awaiting_decision)


@then(parsers.parse("the question records the network as {state}"))
def the_question_records_the_network(world: Walk, state: str) -> None:
    assert world.pending().context["allow_network"] is (state == "open")


@then(parsers.parse('the output of the base version is kept, and names "{text}"'))
def the_baseline_output_is_kept(world: Walk, text: str) -> None:
    baseline = [e for e in world.run.evidence if e.kind is EvidenceKind.baseline]
    assert baseline and baseline[0].output_ref
    assert text in world.engine.store.read_text(world.run_id, baseline[0].output_ref)


@then("the network stands open on the run, which goes back to be profiled again")
def the_network_stands_open(world: Walk) -> None:
    run = world.run
    assert run.config.sandbox.allow_network is True
    assert run.status is RunStatus.created


@then("the run warns that the network was opened")
def the_run_warns_about_the_network(world: Walk) -> None:
    assert any("network access" in w for w in world.run.warnings)


@then(parsers.parse('the question no longer says "{text}"'))
def the_question_no_longer_says(world: Walk, text: str) -> None:
    assert text not in world.pending().question


@then("the run stands profiled")
def the_run_stands_profiled(world: Walk) -> None:
    assert world.run.status is RunStatus.profiled
