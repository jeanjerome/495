"""Scenarios of ``tests/features/calibration.feature``: every verification is run on the base
version too, and one that reports the same thing with and without the change decides nothing.

The scenarios walk a change run with the scripted agents of ``conftest``, giving the
specification a command that cannot run or one that reports success whatever the tree holds,
and read back what the run asked the requester, what the control run recorded, and what the
answer did to the specification. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.engine import EngineError
from harness495.core.models import (
    DecisionKind,
    EvidenceKind,
    RequirementStatus,
    Role,
    RunMode,
    RunStatus,
    Sufficiency,
)
from tests.conftest import Scenario, bad_producer, good_producer

scenarios("features/calibration.feature")

BROKEN = f'{sys.executable} -c "import module_that_never_existed"'
VACUOUS = f'{sys.executable} -c "pass"'


@dataclass
class World:
    engine: Any = None
    run: Any = None
    refusal: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def scenario(self) -> Scenario:
        return self.extra["scenario"]  # type: ignore[no-any-return]


@pytest.fixture
def world() -> World:
    return World()


# --------------------------------------------------------------------------- the project


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    world.extra["project"] = sample_project
    world.extra["config"] = config
    world.extra["scenario"] = scenario
    world.extra["working"] = scenario.spec["verifications"][0]["command"]
    world.engine = engine_factory()


@given("the check of the new behaviour is a command that cannot run")
def the_check_cannot_run(world: World) -> None:
    world.scenario.spec["verifications"][0]["command"] = BROKEN


@given("the check of the new behaviour is a command that passes on any tree")
def the_check_passes_anyway(world: World) -> None:
    world.scenario.spec["verifications"][0]["command"] = VACUOUS


@given("the producer gets the behaviour wrong once")
def the_producer_gets_it_wrong_once(world: World) -> None:
    world.scenario.producers = [bad_producer, good_producer]


@given("the producer reports that another command worked")
def the_producer_reports_another_command(world: World) -> None:
    world.scenario.producer_commands = [
        {"command": world.scenario.spec["verifications"][0]["command"], "exit_code": 1},
        {"command": world.extra["working"], "exit_code": 0},
    ]


# --------------------------------------------------------------------------- walking the run


@when("a change run walks the workflow")
def a_change_run_walks_the_workflow(world: World) -> None:
    run = world.engine.create_run(
        "add subtract to calc", world.extra["project"], world.extra["config"], RunMode.change
    )
    world.run = world.engine.run(run.id)


@when("the run goes on")
def the_run_goes_on(world: World) -> None:
    world.run = world.engine.run(world.run.id)


@when(
    parsers.parse(
        'the requester asks for a specification these commands can check, with the note "{note}"'
    )
)
def the_requester_asks_for_a_specification(world: World, note: str) -> None:
    world.run = world.engine.decide(world.run.id, "respecify", note)


@when("the requester leaves the command as proof of nothing")
def the_requester_leaves_the_command(world: World) -> None:
    world.run = world.engine.decide(world.run.id, "ignore")


@when("the requester replaces the command with the one that works")
def the_requester_replaces_the_command(world: World) -> None:
    world.run = world.engine.decide(world.run.id, "recalibrate", f"V1: {world.extra['working']}")


@when(parsers.parse("the requester names {vid}, which is not at fault"))
def the_requester_names_the_wrong_check(world: World, vid: str) -> None:
    try:
        world.engine.decide(world.run.id, "recalibrate", f"{vid}: echo hi")
    except EngineError as exc:
        world.refusal = str(exc)
    world.run = world.engine.store.load(world.run.id)


# --------------------------------------------------------------------------- what was asked


@then("the run asks the requester about an instrument at fault")
def the_run_asks_about_an_instrument(world: World) -> None:
    assert world.run.status is RunStatus.awaiting_decision, world.run.status
    assert world.run.pending_decision.kind is DecisionKind.instrument_fault


@then(parsers.parse("the fault names {vid}"))
def the_fault_names(world: World, vid: str) -> None:
    it = world.run.current_iteration
    assert it.instrument_faults and it.instrument_faults[0].startswith(f"{vid}:")


@then("the control run was made on the base version")
def the_control_run_was_made_on_the_base(world: World) -> None:
    control = _controls(world)
    assert len(control) == 1
    assert control[0].subject_version == world.run.profile.base_commit


@then("the control run carried the change's own test files")
def the_control_run_carried_the_test_files(world: World) -> None:
    control = _controls(world)
    assert len(control) == 1
    assert "test file(s) of the change applied" in control[0].summary


@then(parsers.parse("{vid} is recorded vacuous and blind to the change"))
def the_verification_is_vacuous(world: World, vid: str) -> None:
    assert world.run.spec.verification(vid).sufficiency is Sufficiency.vacuous
    assert world.run.spec.verification(vid).discriminates is False


@then("the question offers the command the producer reported")
def the_question_offers_the_command(world: World) -> None:
    assert world.run.pending_decision.context["measured"] == {"V1": world.extra["working"]}


@then("the requester was asked about an instrument at fault once")
def asked_once(world: World) -> None:
    kinds = [d.kind for d in world.run.decisions]
    assert kinds.count(DecisionKind.instrument_fault) == 1, [k.value for k in kinds]


# --------------------------------------------------------------------------- who was not called


@then("no reviewer was asked to read the change")
def no_reviewer_was_called(world: World) -> None:
    assert not [t for t in world.scenario.calls if t.role is Role.reviewer]


@then("both reviewers were asked to read the change")
def the_reviewers_were_called(world: World) -> None:
    assert [t.role for t in world.scenario.calls].count(Role.reviewer) == 3


@then("no correction was requested of the producer")
def no_correction_was_requested(world: World) -> None:
    assert not world.run.current_iteration.correction_requests


@then(parsers.parse("no correction request names {vid}"))
def no_correction_request_names(world: World, vid: str) -> None:
    requests = [c for it in world.run.iterations for c in it.correction_requests]
    assert not [c for c in requests if vid in c], requests


@then("the change was produced once")
def the_change_was_produced_once(world: World) -> None:
    assert len([t for t in world.scenario.calls if t.role is Role.producer]) == 1


# --------------------------------------------------------------------------- what the answer did


@then("the specification is open again and the decisions taken hold")
def the_specification_is_open_again(world: World) -> None:
    assert world.run.status is RunStatus.clarified
    assert not world.run.spec.approved


@then(parsers.parse("{vid} runs the command that works"))
def the_verification_runs_the_working_command(world: World, vid: str) -> None:
    assert world.run.spec.verification(vid).command == world.extra["working"]


@then(parsers.parse("{vid} reports something else without the change"))
def the_verification_discriminates(world: World, vid: str) -> None:
    assert world.run.spec.verification(vid).discriminates is True


@then(parsers.parse("{vid} still runs the command that cannot run"))
def the_verification_still_runs_the_broken_command(world: World, vid: str) -> None:
    assert world.run.spec.verification(vid).command == BROKEN


@then(parsers.parse('the harness answers "{text}"'))
def the_harness_answers(world: World, text: str) -> None:
    assert text in world.refusal, world.refusal


@then("the run is still awaiting the requester")
def the_run_is_still_awaiting(world: World) -> None:
    assert world.run.status is RunStatus.awaiting_decision


@then(parsers.parse("the requirement {rid} is {status}"))
def the_requirement_is(world: World, rid: str, status: str) -> None:
    assert world.run.spec.requirement(rid).status is RequirementStatus(status)


@then("the run ends delivered")
def the_run_ends_delivered(world: World) -> None:
    assert world.run.status is RunStatus.delivered, (world.run.stop_reason, world.run.warnings)


def _controls(world: World) -> list[Any]:
    return [e for e in world.run.evidence if e.kind is EvidenceKind.instrument_check]
