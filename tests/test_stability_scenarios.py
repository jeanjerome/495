"""Scenarios of ``tests/features/stability.feature``: a verification is run twice on the same
version, and one that does not report the same thing twice decides nothing.

The pair scenarios call ``core.reading.verification.reports_the_same_twice``; the decision scenarios
call ``core.decide.assess`` once; the run scenarios walk a change run with the scripted agents
of ``conftest``, giving the specification a check whose outcome alternates from one run to the
next, and read the run, the prompts and the report back. The last section reaches
``core.engine.checks.stability`` on its own, through a ``RunServices`` over a recording store
and a scripted sandbox, so that what the check does with a command the requirements do not
lean on, or with a run the requester stopped, is measured without a run reaching ``produced``.
Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.engine.checks.stability import repeat
from harness495.core.models import (
    DecisionKind,
    Evidence,
    EvidenceKind,
    Finding,
    Iteration,
    Requirement,
    RequirementKind,
    RequirementStatus,
    ReviewVerdict,
    Role,
    RunMode,
    RunStatus,
    Severity,
    Spec,
    Verdict,
    Verification,
    VerificationKind,
)
from harness495.core.reading.decide import Assessment, assess
from harness495.core.reading.verification import reports_the_same_twice
from harness495.core.report import render_markdown
from harness495.sandbox.base import CommandResult
from tests.conftest import Measured, Region, Scenario, measure

scenarios("features/stability.feature")


@dataclass
class World:
    first: CommandResult | None = None
    second: CommandResult | None = None
    stable: bool | None = None
    reading: str = ""
    spec: Spec = field(default_factory=Spec)
    evidence: list[Evidence] = field(default_factory=list)
    reviews: list[ReviewVerdict] = field(default_factory=list)
    assessment: Assessment | None = None
    engine: Any = None
    run: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def result(self) -> Assessment:
        assert self.assessment is not None, "the harness has not assessed the change yet"
        return self.assessment


@pytest.fixture
def world() -> World:
    return World()


def _unescape(text: str) -> str:
    return text.replace("\\n", "\n")


def _run(exit_code: int | None, output: str, timed_out: bool = False) -> CommandResult:
    return CommandResult(
        command="pytest -q",
        exit_code=exit_code,
        output=_unescape(output),
        duration_s=0.4,
        timed_out=timed_out,
    )


# --------------------------------------------------------------------------- reading the pair


@given(parsers.parse('a first run that exited {code:d} printing "{output}"'))
def a_first_run(world: World, code: int, output: str) -> None:
    world.first = _run(code, output)


@given(parsers.parse('a second run that exited {code:d} printing "{output}"'))
def a_second_run(world: World, code: int, output: str) -> None:
    world.second = _run(code, output)


@given(parsers.parse('a second run that timed out printing "{output}"'))
def a_second_run_that_timed_out(world: World, output: str) -> None:
    world.second = _run(None, output, timed_out=True)


@when("the harness reads the pair")
def the_harness_reads_the_pair(world: World) -> None:
    assert world.first is not None and world.second is not None
    world.stable, world.reading = reports_the_same_twice(
        0, world.first.exit_code, world.first.output, world.first.timed_out, world.second
    )


@then("the command reported the same thing twice")
def the_command_reported_the_same_thing_twice(world: World) -> None:
    assert world.stable is True, world.reading


@then("the command did not report the same thing twice")
def the_command_did_not(world: World) -> None:
    assert world.stable is False, world.reading


@then(parsers.parse('the reading says "{text}"'))
def the_reading_says(world: World, text: str) -> None:
    assert text in world.reading, world.reading


# --------------------------------------------------------------------------- the decision


def _verification(vid: str) -> Verification:
    return Verification(id=vid, kind=VerificationKind.test, description=vid, command="true")


@given(parsers.parse("a {kind} requirement {rid} verified by the test {vid}"))
def a_requirement_verified_by_a_test(world: World, kind: str, rid: str, vid: str) -> None:
    world.spec.requirements.append(
        Requirement(
            id=rid,
            statement=rid,
            kind=RequirementKind(kind.replace("-", "_")),
            verification_ids=[vid],
        )
    )
    world.spec.verifications.append(_verification(vid))


@given(parsers.parse("{rid} is also verified by the test {vid}"))
def also_verified_by(world: World, rid: str, vid: str) -> None:
    world.spec.requirement(rid).verification_ids.append(vid)
    world.spec.verifications.append(_verification(vid))


@given(parsers.parse("{vid} {result} on the change"))
def a_verification_ran_on_the_change(world: World, vid: str, result: str) -> None:
    world.evidence.append(
        Evidence(
            id=f"ev-{vid}-{result}",
            kind=EvidenceKind.command_result,
            iteration=1,
            verification_id=vid,
            passed=result == "passed",
            summary=result,
        )
    )


@given(parsers.parse('{vid} did not report the same thing twice, saying "{summary}"'))
def an_unstable_verification(world: World, vid: str, summary: str) -> None:
    world.evidence.append(
        Evidence(
            id=f"ev-{vid}-repeat",
            kind=EvidenceKind.stability_check,
            iteration=1,
            verification_id=vid,
            requirement_ids=[r.id for r in world.spec.requirements if vid in r.verification_ids],
            passed=False,
            summary=summary,
        )
    )


@given(parsers.parse("{vid} reported the same thing twice"))
def a_stable_verification(world: World, vid: str) -> None:
    world.evidence.append(
        Evidence(
            id=f"ev-{vid}-repeat",
            kind=EvidenceKind.stability_check,
            iteration=1,
            verification_id=vid,
            passed=True,
            summary=f"{vid} reported success twice on the same version (exit 0, exit 0)",
        )
    )


@given("a reviewer accepted the change")
def a_reviewer_accepted(world: World) -> None:
    world.reviews.append(
        ReviewVerdict(intervention_id="int-p", perspective="p", verdict=Verdict.accept)
    )


@given(parsers.parse('a reviewer reported a violation of {rid} citing "{observation}"'))
def a_reviewer_reported_a_violation(world: World, rid: str, observation: str) -> None:
    world.reviews.append(
        ReviewVerdict(
            intervention_id="int-p",
            perspective="correctness",
            verdict=Verdict.reject,
            findings=[
                Finding(
                    severity=Severity.major,
                    title="subtract is wrong",
                    detail="",
                    requirement_id=rid,
                    evidence=observation,
                )
            ],
        )
    )


@when("the harness assesses the change")
def the_harness_assesses_the_change(world: World) -> None:
    world.assessment = assess(world.spec, world.evidence, world.reviews)


@then(parsers.parse("the outcome is {outcome}"))
def the_outcome_is(world: World, outcome: str) -> None:
    assert world.result().outcome is Verdict(outcome), world.result()


@then(parsers.parse('the reason for {rid} says "{text}"'))
def the_reason_says(world: World, rid: str, text: str) -> None:
    assert text in world.result().reasons[rid], world.result().reasons


@then(parsers.parse('a requirement was not credited: "{text}"'))
def a_requirement_was_not_credited(world: World, text: str) -> None:
    assert text in world.result().uncredited, world.result().uncredited


@then("no correction was requested")
def no_correction_was_requested(world: World) -> None:
    assert world.result().correction_requests == [], world.result().correction_requests


# --------------------------------------------------------------------------- through the engine


def _alternating(counter: Path, first_exit: int) -> str:
    """A command that exits 0 and 1 in turn, one run after the other.

    It counts its own runs in a file outside the worktree, so that resetting the tree between
    phases does not reset it: the harness runs it once at the gate, before anything is
    produced, then once on the change and once more for the stability check. ``first_exit`` is
    what the run on the change reports; the second run reports the other.
    """
    parity = 1 if first_exit == 0 else 0
    return (
        f"{sys.executable} -c "
        f'"import pathlib,sys; p = pathlib.Path({str(counter)!r}); '
        "n = len(p.read_text()) if p.exists() else 0; p.write_text('x' * (n + 1)); "
        f'sys.exit(0 if n % 2 == {parity} else 1)"'
    )


def _add_alternating_check(world: World, first_exit: int) -> None:
    spec = world.extra["scenario"].spec
    spec["requirements"].append(
        {
            "id": "R3",
            "statement": "the counter stays where the project left it",
            "kind": "non_regression",
            "rationale": "non-regression",
            "verification_ids": ["V3"],
        }
    )
    spec["verifications"].append(
        {
            "id": "V3",
            "kind": "command",
            "description": "the project's counter check",
            "command": _alternating(world.extra["project"].parent / "counter", first_exit),
            "to_create": False,
        }
    )


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    world.extra["project"] = sample_project
    world.extra["config"] = config
    world.extra["scenario"] = scenario
    world.engine = engine_factory()


@given("a check that reports success and then failure")
def a_check_that_passes_then_fails(world: World) -> None:
    _add_alternating_check(world, first_exit=0)


@given("a check that reports failure and then success")
def a_check_that_fails_then_passes(world: World) -> None:
    _add_alternating_check(world, first_exit=1)


@given("no check is given time for a second run")
def no_check_is_given_time(world: World) -> None:
    world.extra["config"].budget.repeat_command_max_s = 0


@given("the stability check is allowed no command")
def the_stability_check_is_disabled(world: World) -> None:
    world.extra["config"].budget.max_repeated_commands = 0


@when("a change run walks the workflow")
def a_change_run_walks_the_workflow(world: World) -> None:
    run = world.engine.create_run(
        "add subtract to calc", world.extra["project"], world.extra["config"], RunMode.change
    )
    world.run = world.engine.run(run.id)


@when(parsers.parse('the requester accepts the risk with the note "{note}"'))
def the_requester_accepts_the_risk(world: World, note: str) -> None:
    world.engine.decide(world.run.id, "accept_with_risk", note=note)
    world.run = world.engine.run(world.run.id)


def _stability_checks(world: World, n: int) -> list[Evidence]:
    it = world.run.iterations[n - 1]
    return [
        e
        for e in (world.run.evidence_by_id(x) for x in it.evidence_ids)
        if e is not None and e.kind is EvidenceKind.stability_check
    ]


@then(parsers.parse("every check of iteration {n:d} reported the same thing twice"))
def every_check_reported_the_same_thing_twice(world: World, n: int) -> None:
    checks = _stability_checks(world, n)
    assert checks and all(e.passed is True for e in checks), [e.summary for e in checks]


@then(parsers.parse("the check of iteration {n:d} did not report the same thing twice"))
def the_check_did_not_report_the_same_thing_twice(world: World, n: int) -> None:
    checks = _stability_checks(world, n)
    assert [e for e in checks if e.passed is False and e.verification_id == "V3"], [
        e.summary for e in checks
    ]


@then("nothing was run a second time")
def nothing_was_run_a_second_time(world: World) -> None:
    assert _stability_checks(world, 1) == []


@then(parsers.parse('the run warns "{text}"'))
def the_run_warns(world: World, text: str) -> None:
    assert any(text in w for w in world.run.warnings), world.run.warnings


@then(parsers.parse("the requirement {rid} is {status}"))
def the_requirement_is(world: World, rid: str, status: str) -> None:
    if world.run is not None:
        assert world.run.spec.requirement(rid).status is RequirementStatus(status)
    else:
        assert world.result().requirement_status[rid] is RequirementStatus(status)


@then(parsers.parse('the run\'s reason for {rid} says "{text}"'))
def the_reason_in_the_run_says(world: World, rid: str, text: str) -> None:
    reason = world.run.spec.requirement(rid).status_reason
    assert text in reason, reason


@then("no correction was requested of the producer")
def no_correction_was_requested_of_the_producer(world: World) -> None:
    requested = [c for it in world.run.iterations for c in it.correction_requests]
    assert requested == [], requested


@then("the run kept to one iteration")
def the_run_kept_to_one_iteration(world: World) -> None:
    assert len(world.run.iterations) == 1, [it.n for it in world.run.iterations]


@then("the run awaits the requester on an undetermined verdict")
def the_run_awaits_the_requester(world: World) -> None:
    assert world.run.status is RunStatus.awaiting_decision, world.run.status
    assert world.run.pending_decision.kind is DecisionKind.undetermined


@then("the run ends delivered")
def the_run_ends_delivered(world: World) -> None:
    assert world.run.status is RunStatus.delivered, (world.run.stop_reason, world.run.warnings)


@then(parsers.parse('the "{perspective}" reviewer\'s prompt says "{text}"'))
def the_reviewers_prompt_says(world: World, perspective: str, text: str) -> None:
    marker = f"Review the change from the perspective: **{perspective}**"
    prompts = [
        t.prompt
        for t in world.extra["scenario"].calls
        if t.role is Role.reviewer and marker in t.prompt
    ]
    assert prompts, f"no {perspective} reviewer was called"
    assert text in prompts[0], prompts[0]


@then(parsers.parse('the report says "{text}"'))
def the_report_says(world: World, text: str) -> None:
    assert text in render_markdown(world.run, world.engine.store)


# --------------------------------------------------------------------- the check on its own


@given("a version under review", target_fixture="region")
def a_version_under_review(produced_version: Callable[..., Region]) -> Region:
    return produced_version()


@given("a version under review at the second iteration", target_fixture="region")
def a_version_under_review_at_the_second_iteration(
    produced_version: Callable[..., Region],
) -> Region:
    region = produced_version()
    region.run.iterations.append(Iteration(n=2, version=region.iteration.version))
    return region


@given(parsers.parse("a command {vid} that passed in {seconds:d}s, which no requirement leans on"))
def a_command_no_requirement_leans_on(region: Region, vid: str, seconds: int) -> None:
    region.verification(vid)
    region.ran_command(vid, seconds=float(seconds), output="4 passed")


@given(
    parsers.parse(
        "a command {vid} that passed in {seconds:d}s, which the requirement {rid} leans on"
    )
)
def a_command_a_requirement_leans_on(region: Region, vid: str, seconds: int, rid: str) -> None:
    region.verification(vid, requirement=rid)
    region.ran_command(vid, seconds=float(seconds), output="4 passed")


@given(parsers.parse("a manual verification {vid}, which the requirement {rid} leans on"))
def a_manual_verification(region: Region, vid: str, rid: str) -> None:
    region.verification(vid, command=None, kind=VerificationKind.manual, requirement=rid)


@given(parsers.parse("{vid} reported failure on the previous iteration"))
def a_command_that_failed_on_the_previous_iteration(region: Region, vid: str) -> None:
    region.ran_command(vid, passed=False, output="1 failed", iteration=1)


@given(parsers.parse("only one command may be run a second time"))
def only_one_command_may_be_repeated(region: Region) -> None:
    region.run.budget.max_repeated_commands = 1


@given("the requester asked the run to stop")
def the_requester_asked_the_run_to_stop(region: Region) -> None:
    region.services.stop_requested = True


@when("the stability check measures the version", target_fixture="measured")
def the_stability_check_measures_the_version(region: Region) -> Measured:
    return measure(
        lambda: repeat(
            region.services,
            region.run,
            region.iteration,
            [e for e in region.run.evidence if e.iteration == region.iteration.n],
        )
    )


@then("no command was run a second time")
def no_command_was_run_a_second_time(region: Region) -> None:
    assert region.services.fake_sandbox.commands == [], region.services.fake_sandbox.commands


@then("the stability check left no evidence")
def the_stability_check_left_no_evidence(measured: Measured) -> None:
    assert measured.evidence == [], [e.summary for e in measured.evidence]


@then(parsers.parse("{vid} is the only command that was run a second time"))
def one_command_was_run_a_second_time(region: Region, measured: Measured, vid: str) -> None:
    assert [e.verification_id for e in measured.evidence] == [vid], [
        e.summary for e in measured.evidence
    ]


@then("the run stops rather than reading the pair")
def the_run_stops_rather_than_reading_the_pair(measured: Measured) -> None:
    assert measured.interrupted, "the check read the interrupted run as a second reading"


@then(parsers.parse("{vid} is left with no stability reading"))
def a_verification_is_left_with_no_reading(region: Region, vid: str) -> None:
    assert region.run.spec.verification(vid).stable is None
