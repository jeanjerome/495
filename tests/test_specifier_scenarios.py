"""Scenarios of ``tests/features/specifier.feature``: what the specifier is given about the
catalogue, and how a verification that names a catalogue role is judged.

The audit scenarios build a profile and a specification from the scenario text and call the
sufficiency audit; the engine scenario walks a change run with the scripted agents of
``conftest`` and reads the specifier's prompt and the gate back. Nothing is asserted outside a
``Then``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.models import (
    CatalogueRole,
    ProjectProfile,
    Requirement,
    RoleCoverage,
    Run,
    RunMode,
    RunStatus,
    Spec,
    Verification,
    VerificationKind,
)
from harness495.core.profile import ROLES_BY_TECHNOLOGY
from harness495.core.verification import assess_sufficiency
from tests.conftest import Scenario

scenarios("features/specifier.feature")


@dataclass
class World:
    profile: ProjectProfile | None = None
    spec: Spec | None = None
    last_verification: Verification | None = None
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


def _rows(technology: str, measured: dict[CatalogueRole, str]) -> list[RoleCoverage]:
    return [
        RoleCoverage(
            technology=technology,
            role=role,
            tools=[measured[role]] if role in measured else [],
            markers=[f"pyproject.toml: dependency {measured[role]}"] if role in measured else [],
        )
        for role in ROLES_BY_TECHNOLOGY[technology]
    ]


@given(parsers.parse('a profile that measures the role "{role}" of "{technology}" with "{tool}"'))
def a_profile_measuring_one_role(world: World, role: str, technology: str, tool: str) -> None:
    world.profile = ProjectProfile(
        root=".", role_coverage=_rows(technology, {CatalogueRole(role): tool})
    )


@given(parsers.parse('a profile that measures no role of "{technology}"'))
def a_profile_measuring_no_role(world: World, technology: str) -> None:
    world.profile = ProjectProfile(root=".", role_coverage=_rows(technology, {}))


@given("a profile with no role coverage")
def a_profile_with_no_coverage(world: World) -> None:
    world.profile = ProjectProfile(root=".")


@given(parsers.parse('a specification with the requirement "{rid}" verified by "{vids}"'))
def a_specification(world: World, rid: str, vids: str) -> None:
    world.spec = Spec(
        requirements=[
            Requirement(
                id=rid, statement="it holds", verification_ids=[v.strip() for v in vids.split(",")]
            )
        ]
    )


@given(parsers.parse('"{vid}" is a test with a command, naming the role "{role}"'))
def a_test_naming_a_role(world: World, vid: str, role: str) -> None:
    world.the_spec().verifications.append(
        Verification(
            id=vid,
            kind=VerificationKind.test,
            description="a test",
            command="pytest -q",
            to_create=True,
            role=CatalogueRole(role),
        )
    )


@given(parsers.parse('"{vid}" is a test with a command, naming no role'))
def a_test_naming_no_role(world: World, vid: str) -> None:
    world.the_spec().verifications.append(
        Verification(id=vid, kind=VerificationKind.test, description="a test", command="pytest -q")
    )


@when("the harness audits the specification against the profile")
def the_harness_audits(world: World) -> None:
    assess_sufficiency(world.the_spec(), {"pytest -q"}, set(), world.profile)


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


# --------------------------------------------------------------------------- through the engine


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any
) -> None:
    world.extra["project"] = sample_project
    world.extra["config"] = config
    world.engine = engine_factory()


@given(parsers.parse('the scripted specifier names the role "{role}" on "{vid}"'))
def the_scripted_specifier_names_a_role(scenario: Scenario, role: str, vid: str) -> None:
    for v in scenario.spec["verifications"]:
        v["role"] = role if v["id"] == vid else None


@when("a change run walks the workflow")
def a_change_run_walks_the_workflow(world: World) -> None:
    run = world.engine.create_run(
        "add subtract to calc", world.extra["project"], world.extra["config"], RunMode.change
    )
    world.run = world.engine.run(run.id)


@then(parsers.parse('the specifier\'s prompt carries the fact "{title}"'))
def the_specifiers_prompt_carries_the_fact(scenario: Scenario, title: str) -> None:
    prompt = scenario.calls[0].prompt
    facts = prompt.split("# Established facts")[1].split("# Untrusted content")[0]
    assert f"## {title}" in facts, prompt


@then(parsers.parse('the specifier\'s prompt says "{text}"'))
def the_specifiers_prompt_says(scenario: Scenario, text: str) -> None:
    assert text in scenario.calls[0].prompt, scenario.calls[0].prompt


@then(parsers.parse('the specification records "{vid}" with the role "{role}"'))
def the_specification_records_the_role(world: World, vid: str, role: str) -> None:
    v = world.the_run().spec.verification(vid)
    assert v is not None and v.role is CatalogueRole(role)


@then(parsers.parse('the run waits at the gate with a question saying "{text}"'))
def the_run_waits_at_the_gate(world: World, text: str) -> None:
    run = world.the_run()
    assert run.status is RunStatus.awaiting_decision, (run.status, run.stop_reason)
    assert run.pending_decision is not None
    assert text in run.pending_decision.question, run.pending_decision.question
