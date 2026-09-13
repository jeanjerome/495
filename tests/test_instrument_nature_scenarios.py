"""Scenarios of ``tests/features/instrument_nature.feature``: the nature of a failure without
the change, the unconfirmed verification it yields, and the test_quality reviewer a test to
create calls for.

The reader scenarios build a pair of runs and call ``classify_instrument``; the decision
scenario calls ``assess``; the reviewer scenarios call ``RolesConfig.reviewers_for``; the run
scenario walks a change run with the scripted agents of ``conftest`` and reads the run, the
prompts and the report back. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.decide import Assessment, assess
from harness495.core.models import (
    Evidence,
    EvidenceKind,
    Requirement,
    RequirementStatus,
    ReviewerSpec,
    ReviewVerdict,
    Role,
    RolesConfig,
    RunMode,
    Spec,
    Sufficiency,
    Verdict,
    Verification,
    VerificationKind,
)
from harness495.core.report import render_markdown
from harness495.core.verification import classify_instrument
from harness495.sandbox.base import CommandResult
from tests.conftest import Scenario

scenarios("features/instrument_nature.feature")


@dataclass
class World:
    verification: Verification | None = None
    control: CommandResult | None = None
    discriminates: bool | None = None
    sufficiency: Sufficiency | None = None
    rationale: str = ""
    spec: Spec = field(default_factory=Spec)
    evidence: list[Evidence] = field(default_factory=list)
    reviews: list[ReviewVerdict] = field(default_factory=list)
    assessment: Assessment | None = None
    roles: RolesConfig = field(default_factory=RolesConfig)
    reviewers: list[ReviewerSpec] = field(default_factory=list)
    engine: Any = None
    run: Any = None
    extra: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def world() -> World:
    return World()


def _names(text: str) -> list[str]:
    return [t.strip() for t in text.split(",") if t.strip()]


# --------------------------------------------------------------------------- reading the pair


@given(parsers.parse("a verification {vid} that passed on the change"))
def a_verification_that_passed(world: World, vid: str) -> None:
    world.verification = Verification(
        id=vid, kind=VerificationKind.test, description=vid, command="c", to_create=True
    )


@given(parsers.parse("without the change it exited {code:d} printing"))
def without_the_change_it_printed(world: World, code: int, docstring: str) -> None:
    world.control = CommandResult(command="c", exit_code=code, output=docstring, duration_s=0.1)


@when("the pair of runs is read")
def the_pair_is_read(world: World) -> None:
    assert world.verification is not None and world.control is not None
    world.discriminates, world.sufficiency, world.rationale = classify_instrument(
        world.verification, True, 0, "1 passed", False, world.control, "abc123def456", ["t.py"]
    )


@then(parsers.parse("the verification {vid} discriminates"))
def it_discriminates(world: World, vid: str) -> None:
    if world.run is not None:
        assert world.run.spec.verification(vid).discriminates is True
    else:
        assert world.discriminates is True


@then(parsers.parse("the verification {vid} is {sufficiency}"))
def it_has_the_sufficiency(world: World, vid: str, sufficiency: str) -> None:
    if world.run is not None:
        assert world.run.spec.verification(vid).sufficiency is Sufficiency(sufficiency)
    else:
        assert world.sufficiency is Sufficiency(sufficiency)


@then(parsers.parse('the rationale says "{text}"'))
def the_rationale_says(world: World, text: str) -> None:
    assert text in world.rationale, world.rationale


# --------------------------------------------------------------------------- the decision


@given(parsers.parse("a requirement {rid} verified by the test {vid}"))
def a_requirement_verified_by_a_test(world: World, rid: str, vid: str) -> None:
    world.spec.requirements.append(Requirement(id=rid, statement=rid, verification_ids=[vid]))
    world.spec.verifications.append(
        Verification(id=vid, kind=VerificationKind.test, description=vid, command="true")
    )


@given(parsers.parse('{vid} is unconfirmed because "{why}"'))
def a_verification_is_unconfirmed(world: World, vid: str, why: str) -> None:
    v = world.spec.verification(vid)
    assert v is not None
    v.sufficiency = Sufficiency.unconfirmed
    v.discriminates = True
    v.rationale = why


@given(parsers.parse("the verification {vid} passed on the change"))
def a_verification_passed_on_the_change(world: World, vid: str) -> None:
    world.evidence.append(
        Evidence(
            id=f"ev-{vid}",
            kind=EvidenceKind.command_result,
            iteration=1,
            verification_id=vid,
            passed=True,
            summary="exit 0",
        )
    )


@given("a reviewer accepted the change")
def a_reviewer_accepted(world: World) -> None:
    world.reviews.append(
        ReviewVerdict(intervention_id="int-p", perspective="p", verdict=Verdict.accept)
    )


@when("the harness assesses the change")
def the_harness_assesses(world: World) -> None:
    world.assessment = assess(world.spec, world.evidence, world.reviews)


@then(parsers.parse("the requirement {rid} is {status}"))
def the_requirement_is(world: World, rid: str, status: str) -> None:
    if world.run is not None:
        assert world.run.spec.requirement(rid).status is RequirementStatus(status)
    else:
        assert world.assessment is not None
        assert world.assessment.requirement_status[rid] is RequirementStatus(status)


@then(parsers.parse('the reason for {rid} says "{text}"'))
def the_reason_says(world: World, rid: str, text: str) -> None:
    assert world.assessment is not None
    assert text in world.assessment.reasons[rid], world.assessment.reasons[rid]


@then(parsers.parse("the outcome is {outcome}"))
def the_outcome_is(world: World, outcome: str) -> None:
    assert world.assessment is not None
    assert world.assessment.outcome is Verdict(outcome)


# --------------------------------------------------------------------------- the reviewers


@given(parsers.parse('the configured reviewers are "{names}"'))
def the_configured_reviewers(world: World, names: str) -> None:
    world.roles = RolesConfig(reviewers=[ReviewerSpec(perspective=n) for n in _names(names)])


@given("a specification with a test to create")
def a_specification_with_a_test_to_create(world: World) -> None:
    world.spec = Spec(
        verifications=[
            Verification(id="V1", kind=VerificationKind.test, description="d", to_create=True)
        ]
    )


@given("a specification with no test to create")
def a_specification_without_a_test_to_create(world: World) -> None:
    world.spec = Spec(
        verifications=[Verification(id="V1", kind=VerificationKind.test, description="d")]
    )


@when("the reviewers for the specification are listed")
def the_reviewers_are_listed(world: World) -> None:
    world.reviewers = world.roles.reviewers_for(world.spec)


@then(parsers.parse('they are "{names}"'))
def they_are(world: World, names: str) -> None:
    assert [r.perspective for r in world.reviewers] == _names(names)


@then(parsers.parse('the "{perspective}" reviewer runs with the agent of "{other}"'))
def the_reviewer_runs_with_the_agent_of(world: World, perspective: str, other: str) -> None:
    by_name = {r.perspective: r.agent for r in world.reviewers}
    assert by_name[perspective] == by_name[other]


# --------------------------------------------------------------------------- through the engine


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any
) -> None:
    world.extra["project"] = sample_project
    world.extra["config"] = config
    world.engine = engine_factory()


@when("a change run walks the workflow")
def a_change_run_walks_the_workflow(world: World) -> None:
    run = world.engine.create_run(
        "add subtract to calc", world.extra["project"], world.extra["config"], RunMode.change
    )
    world.run = world.engine.run(run.id)


@then("the run ends delivered")
def the_run_is_delivered(world: World) -> None:
    assert world.run.status.value == "delivered", (world.run.stop_reason, world.run.warnings)


@then(parsers.parse('the "{perspective}" reviewer\'s prompt says "{text}"'))
def the_reviewers_prompt_says(scenario: Scenario, perspective: str, text: str) -> None:
    marker = f"Review the change from the perspective: **{perspective}**"
    prompts = [t.prompt for t in scenario.calls if t.role is Role.reviewer and marker in t.prompt]
    assert prompts, f"no {perspective} reviewer was called"
    assert text in prompts[0], prompts[0]


@then(parsers.parse('the report says "{text}"'))
def the_report_says(world: World, text: str) -> None:
    report = render_markdown(world.run, world.engine.store)
    assert text in report, report
