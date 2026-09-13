"""Scenarios of ``tests/features/expected_test.feature``: a test to create is specified as a
scenario, the audit requires it, and its steps reach the requester and the producer.

The audit scenarios build a specification from the scenario text and call the sufficiency
audit; the engine scenarios walk a change run with the scripted agents of ``conftest`` and
read the prompts, the persisted specification and the approval display back. Nothing is
asserted outside a ``Then``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.models import (
    BehaviourScenario,
    Requirement,
    Role,
    Run,
    RunMode,
    RunStatus,
    Spec,
    Verification,
    VerificationKind,
)
from harness495.core.verification import assess_sufficiency
from harness495.interfaces import render
from tests.conftest import Scenario

scenarios("features/expected_test.feature")


@dataclass
class World:
    spec: Spec | None = None
    last_verification: Verification | None = None
    behaviour: BehaviourScenario | None = None
    steps: list[str] = field(default_factory=list)
    run: Run | None = None
    engine: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def the_spec(self) -> Spec:
        assert self.spec is not None, "no specification was given"
        return self.spec

    def verification(self, vid: str) -> Verification:
        v = self.the_spec().verification(vid)
        assert v is not None, f"no verification {vid}"
        self.last_verification = v
        return v

    def the_run(self) -> Run:
        assert self.run is not None, "no run was walked"
        return self.run


@pytest.fixture
def world() -> World:
    return World()


def _steps(text: str) -> list[str]:
    return [s.strip() for s in text.split("|") if s.strip()]


def _test(vid: str, to_create: bool, scenario: BehaviourScenario | None) -> Verification:
    return Verification(
        id=vid,
        kind=VerificationKind.test,
        description="a test",
        command="pytest -q",
        to_create=to_create,
        scenario=scenario,
    )


# --------------------------------------------------------------------------- the audit


@given(parsers.parse('a specification with the requirement "{rid}" verified by "{vids}"'))
def a_specification(world: World, rid: str, vids: str) -> None:
    world.spec = Spec(
        requirements=[
            Requirement(
                id=rid, statement="it holds", verification_ids=[v.strip() for v in vids.split(",")]
            )
        ]
    )


@given(parsers.parse('"{vid}" is a test to create with a command and no scenario'))
def a_test_to_create_without_a_scenario(world: World, vid: str) -> None:
    world.the_spec().verifications.append(_test(vid, True, None))


@given(parsers.parse('"{vid}" is an existing test with a command and no scenario'))
def an_existing_test_without_a_scenario(world: World, vid: str) -> None:
    world.the_spec().verifications.append(_test(vid, False, None))


@given(
    parsers.parse(
        '"{vid}" is a test to create with the scenario given "{given}" when "{when}" then "{then}"'
    )
)
def a_test_to_create_with_a_scenario(
    world: World, vid: str, given: str, when: str, then: str
) -> None:
    behaviour = BehaviourScenario(given=_steps(given), when=_steps(when), then=_steps(then))
    world.the_spec().verifications.append(_test(vid, True, behaviour))


@given(
    parsers.parse(
        '"{vid}" is a test to create with the scenario given "{given}" when "{when}" and no then step'
    )
)
def a_test_to_create_observing_nothing(world: World, vid: str, given: str, when: str) -> None:
    behaviour = BehaviourScenario(given=_steps(given), when=_steps(when))
    world.the_spec().verifications.append(_test(vid, True, behaviour))


@when("the harness audits the specification")
def the_harness_audits(world: World) -> None:
    assess_sufficiency(world.the_spec(), {"pytest -q"}, set())


@then(parsers.parse('the verification "{vid}" is "{sufficiency}"'))
def the_verification_is(world: World, vid: str, sufficiency: str) -> None:
    assert world.verification(vid).sufficiency.value == sufficiency


@then(parsers.parse('its rationale says "{text}"'))
def its_rationale_says(world: World, text: str) -> None:
    assert world.last_verification is not None
    assert text in world.last_verification.rationale, world.last_verification.rationale


@then(parsers.parse('the specification states the gap "{text}"'))
def the_specification_states_the_gap(world: World, text: str) -> None:
    assert any(text in gap for gap in world.the_spec().gaps), world.the_spec().gaps


@then("the specification states no gap")
def the_specification_states_no_gap(world: World) -> None:
    assert world.the_spec().gaps == []


# --------------------------------------------------------------------------- the Gherkin form


@given(parsers.parse('a scenario given "{given}" when "{when}" then "{then}"'))
def a_scenario(world: World, given: str, when: str, then: str) -> None:
    world.behaviour = BehaviourScenario(given=_steps(given), when=_steps(when), then=_steps(then))


@when("the scenario is written as Gherkin steps")
def the_scenario_is_written(world: World) -> None:
    assert world.behaviour is not None
    world.steps = world.behaviour.lines()


@then(parsers.parse('its steps are "{steps}"'))
def its_steps_are(world: World, steps: str) -> None:
    assert world.steps == _steps(steps)


# --------------------------------------------------------------------------- through the engine


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any
) -> None:
    world.extra["project"] = sample_project
    world.extra["config"] = config
    world.engine = engine_factory()


@given(
    parsers.parse(
        'the scripted specifier states "{vid}" as the scenario given "{given}" when "{when}" then "{then}"'
    )
)
def the_scripted_specifier_states_a_scenario(
    scenario: Scenario, vid: str, given: str, when: str, then: str
) -> None:
    for v in scenario.spec["verifications"]:
        if v["id"] == vid:
            v["scenario"] = {"given": [given], "when": [when], "then": [then]}


@given(parsers.parse('the scripted specifier states "{vid}" as a scenario of blank steps only'))
def the_scripted_specifier_states_blank_steps(scenario: Scenario, vid: str) -> None:
    for v in scenario.spec["verifications"]:
        if v["id"] == vid:
            v["scenario"] = {"given": [" "], "when": [""], "then": []}


@when("a change run walks the workflow")
def a_change_run_walks_the_workflow(world: World) -> None:
    run = world.engine.create_run(
        "add subtract to calc", world.extra["project"], world.extra["config"], RunMode.change
    )
    world.run = world.engine.run(run.id)


@then(parsers.parse('the specifier\'s prompt says "{text}"'))
def the_specifiers_prompt_says(scenario: Scenario, text: str) -> None:
    assert text in scenario.calls[0].prompt, scenario.calls[0].prompt


@then(parsers.parse('the specification records "{vid}" with the steps "{steps}"'))
def the_specification_records_the_steps(world: World, vid: str, steps: str) -> None:
    v = world.the_run().spec.verification(vid)
    assert v is not None and v.scenario is not None
    assert v.scenario.lines() == _steps(steps)


@then(parsers.parse('the specification records "{vid}" with no scenario'))
def the_specification_records_no_scenario(world: World, vid: str) -> None:
    v = world.the_run().spec.verification(vid)
    assert v is not None and v.scenario is None


@then(parsers.parse('the specification printed for approval shows "{vid}" with the step "{step}"'))
def the_printed_specification_shows_the_step(world: World, vid: str, step: str) -> None:
    with render.console.capture() as capture:
        render.print_spec(world.the_run().spec)
    printed = capture.get()
    assert vid in printed and step in printed, printed


@then(parsers.parse('the producer\'s prompt shows "{vid}" with the step "{step}"'))
def the_producers_prompt_shows_the_step(scenario: Scenario, vid: str, step: str) -> None:
    prompts = [t.prompt for t in scenario.calls if t.role is Role.producer]
    assert prompts, "no producer was called"
    after = prompts[0].split(f"- {vid} (", 1)
    assert len(after) == 2 and step in after[1].split("\n- ", 1)[0], prompts[0]


@then(parsers.parse('the run waits at the gate with a question saying "{text}"'))
def the_run_waits_at_the_gate(world: World, text: str) -> None:
    run = world.the_run()
    assert run.status is RunStatus.awaiting_decision, (run.status, run.stop_reason)
    assert run.pending_decision is not None
    assert text in run.pending_decision.question, run.pending_decision.question
