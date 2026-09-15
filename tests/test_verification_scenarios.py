"""Scenarios of ``tests/features/verification.feature``: what ``core/reading/verification.py``
makes of a specification's verifications and of the runs they produced.

The steps build a specification, or a pair of runs, from the scenario text and call one
reader — ``assess_sufficiency``, ``failure_signature``, ``measures_the_change``,
``classify_instrument``, ``instrument_files``. Nothing is executed and nothing is asserted
outside a ``Then``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.models import (
    BehaviourScenario,
    Requirement,
    RequirementKind,
    Spec,
    Sufficiency,
    Verification,
    VerificationKind,
)
from harness495.core.reading.verification import (
    assess_sufficiency,
    classify_instrument,
    failure_signature,
    instrument_files,
    measures_the_change,
)
from harness495.sandbox.base import CommandResult

scenarios("features/verification.feature")


@dataclass
class World:
    spec: Spec = field(default_factory=Spec)
    executable: set[str] = field(default_factory=set)
    passing_on_base: set[str] | None = None
    gaps: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    signatures: list[str] = field(default_factory=list)
    subject_exit: int | None = None
    subject_output: str = ""
    subject_timed_out: bool = False
    subject_passed: bool | None = None
    control: CommandResult | None = None
    applied: list[str] = field(default_factory=list)
    differs: bool | None = None
    discriminates: bool | None = None
    sufficiency: Sufficiency | None = None
    rationale: str = ""
    files_changed: list[str] = field(default_factory=list)
    instruments: list[str] = field(default_factory=list)

    def verification(self, vid: str) -> Verification:
        found = self.spec.verification(vid)
        assert found is not None, f"no verification {vid}"
        return found

    def the_control(self) -> CommandResult:
        assert self.control is not None, "no run without the change was given"
        return self.control


@pytest.fixture
def world() -> World:
    return World()


def _commands(text: str) -> set[str]:
    return {c.strip() for c in text.split(",") if c.strip()}


def _add(world: World, rid: str, kind: RequirementKind, vid: str | None) -> None:
    world.spec.requirements.append(
        Requirement(id=rid, statement=rid, kind=kind, verification_ids=[vid] if vid else [])
    )


# --------------------------------------------------------------------------- the audit


@given(
    parsers.parse('the requirement "{rid}" is verified by "{vid}", a {kind} running "{command}"')
)
def a_requirement_verified_by_a_command(
    world: World, rid: str, vid: str, kind: str, command: str
) -> None:
    to_create = kind.startswith("test to create")
    world.spec.verifications.append(
        Verification(
            id=vid,
            kind=VerificationKind.test if kind.startswith("test") else VerificationKind.command,
            description=vid,
            command=command,
            to_create=to_create,
        )
    )
    _add(world, rid, RequirementKind.behaviour, vid)


@given(parsers.parse('the requirement "{rid}" is verified by "{vid}", a review'))
def a_requirement_verified_by_a_review(world: World, rid: str, vid: str) -> None:
    world.spec.verifications.append(
        Verification(id=vid, kind=VerificationKind.review, description=vid)
    )
    _add(world, rid, RequirementKind.behaviour, vid)


@given(parsers.parse('the requirement "{rid}" is verified by nothing'))
def a_requirement_verified_by_nothing(world: World, rid: str) -> None:
    _add(world, rid, RequirementKind.behaviour, None)


@given(parsers.parse('the non-regression requirement "{rid}" is verified by "{vid}"'))
def a_non_regression_requirement(world: World, rid: str, vid: str) -> None:
    _add(world, rid, RequirementKind.non_regression, vid)


@given(parsers.parse('"{vid}" states the scenario when "{when_step}" then "{then_step}"'))
def a_verification_states_a_scenario(
    world: World, vid: str, when_step: str, then_step: str
) -> None:
    world.verification(vid).scenario = BehaviourScenario(when=[when_step], then=[then_step])


@given(parsers.parse('the project\'s verified commands are "{commands}"'))
def the_projects_verified_commands(world: World, commands: str) -> None:
    world.executable = _commands(commands)


@given(parsers.parse('the command "{command}" already passed on the base version'))
def a_command_passed_on_the_base(world: World, command: str) -> None:
    world.passing_on_base = {command}


@given("no command passed on the base version")
def no_command_passed_on_the_base(world: World) -> None:
    world.passing_on_base = set()


@when("the harness audits the specification")
def the_harness_audits(world: World) -> None:
    world.gaps = assess_sufficiency(world.spec, world.executable, world.passing_on_base)


@then(parsers.parse('the verification "{vid}" is "{sufficiency}"'))
def the_verification_is(world: World, vid: str, sufficiency: str) -> None:
    assert world.verification(vid).sufficiency is Sufficiency(sufficiency)


@then(parsers.parse('the rationale of "{vid}" says "{text}"'))
def the_rationale_says(world: World, vid: str, text: str) -> None:
    rationale = world.verification(vid).rationale
    assert text in rationale, rationale


@then(parsers.parse('"{vid}" states no rationale'))
def it_states_no_rationale(world: World, vid: str) -> None:
    assert world.verification(vid).rationale == ""


@then(parsers.parse('the command of "{vid}" is "{command}"'))
def the_command_of_is(world: World, vid: str, command: str) -> None:
    assert world.verification(vid).command == command


@then(parsers.parse('the specification\'s gaps name "{rids}"'))
def the_gaps_name(world: World, rids: str) -> None:
    assert [g.split(" ")[0] for g in world.gaps] == [r.strip() for r in rids.split(",")]


@then("the specification states no gap")
def the_specification_states_no_gap(world: World) -> None:
    assert world.gaps == []


@then(parsers.parse('the gap on "{rid}" says "{text}"'))
def the_gap_says(world: World, rid: str, text: str) -> None:
    gap = next(g for g in world.gaps if g.startswith(rid))
    assert text in gap, gap


@then(parsers.parse('the gap on "{rid}" reads "{text}"'))
def the_gap_reads(world: World, rid: str, text: str) -> None:
    gap = next(g for g in world.gaps if g.startswith(rid))
    assert gap == text, gap


# --------------------------------------------------------------------------- the failure signature


@given(parsers.parse('one run printed "{output}"'))
def one_run_printed(world: World, output: str) -> None:
    world.outputs.append(output)


@given(parsers.parse('the other run printed "{output}"'))
def the_other_run_printed(world: World, output: str) -> None:
    world.outputs.append(output)


@when("the two failures are signed")
def the_two_failures_are_signed(world: World) -> None:
    world.signatures = [failure_signature(o) for o in world.outputs]


@then("the two signatures are the same")
def the_signatures_are_the_same(world: World) -> None:
    assert world.signatures[0] == world.signatures[1]


@then("the two signatures differ")
def the_signatures_differ(world: World) -> None:
    assert world.signatures[0] != world.signatures[1]


# --------------------------------------------------------------------------- the pair of runs


@given(parsers.parse('the change ran the command to exit {code:d} printing "{output}"'))
def the_change_ran_the_command(world: World, code: int, output: str) -> None:
    world.subject_exit = code
    world.subject_output = output


@given(parsers.parse('the command timed out on the change printing "{output}"'))
def the_command_timed_out_on_the_change(world: World, output: str) -> None:
    world.subject_exit = None
    world.subject_output = output
    world.subject_timed_out = True


@given(parsers.parse('without the change it exited {code:d} printing "{output}"'))
def without_the_change_it_exited(world: World, code: int, output: str) -> None:
    world.control = CommandResult(command="c", exit_code=code, output=output, duration_s=0.1)


@given(parsers.parse('without the change it timed out printing "{output}"'))
def without_the_change_it_timed_out(world: World, output: str) -> None:
    world.control = CommandResult(
        command="c", exit_code=None, output=output, duration_s=0.1, timed_out=True
    )


@when("the pair is read for what it tells of the change")
def the_pair_is_read(world: World) -> None:
    world.differs = measures_the_change(
        world.subject_exit, world.subject_output, world.the_control(), world.subject_timed_out
    )


@then("the command is measuring the change")
def the_command_is_measuring(world: World) -> None:
    assert world.differs is True


@then("the command is not measuring the change")
def the_command_is_not_measuring(world: World) -> None:
    assert world.differs is False


# --------------------------------------------------------------------------- the nature of the pair


@given(parsers.parse('a verification "{vid}" that passed on the change printing "{output}"'))
def a_verification_that_passed(world: World, vid: str, output: str) -> None:
    world.spec.verifications.append(
        Verification(id=vid, kind=VerificationKind.test, description=vid, command="c")
    )
    world.subject_passed = True
    world.subject_exit = 0
    world.subject_output = output


@given(parsers.parse('a verification "{vid}" that failed on the change printing "{output}"'))
def a_verification_that_failed(world: World, vid: str, output: str) -> None:
    world.spec.verifications.append(
        Verification(id=vid, kind=VerificationKind.test, description=vid, command="c")
    )
    world.subject_passed = False
    world.subject_exit = 1
    world.subject_output = output


@given("the change's test files were carried over")
def the_test_files_were_carried_over(world: World) -> None:
    world.applied = ["tests/t.py"]


@given("none of the change's test files could be carried over")
def no_test_file_was_carried_over(world: World) -> None:
    world.applied = []


@when("the pair of runs is classified")
def the_pair_is_classified(world: World) -> None:
    v = world.spec.verifications[0]
    world.discriminates, world.sufficiency, world.rationale = classify_instrument(
        v,
        world.subject_passed,
        world.subject_exit,
        world.subject_output,
        world.subject_timed_out,
        world.the_control(),
        "abc123def456",
        world.applied,
    )
    # The verification carries the reading, the way the calibration check records it.
    v.sufficiency, v.rationale = world.sufficiency, world.rationale
    v.discriminates = world.discriminates


@then(parsers.parse('"{vid}" discriminates'))
def it_discriminates(world: World, vid: str) -> None:
    assert world.verification(vid).discriminates is True


@then(parsers.parse('"{vid}" does not discriminate'))
def it_does_not_discriminate(world: World, vid: str) -> None:
    assert world.verification(vid).discriminates is False


@then(parsers.parse('whether "{vid}" discriminates is not known'))
def whether_it_discriminates_is_unknown(world: World, vid: str) -> None:
    assert world.verification(vid).discriminates is None


# --------------------------------------------------------------------------- the instrument files


@given(parsers.parse('the change touched "{path}"'))
def the_change_touched(world: World, path: str) -> None:
    world.files_changed.append(path)


@when("the instrument files of the change are read")
def the_instrument_files_are_read(world: World) -> None:
    world.instruments = instrument_files(world.files_changed)


@then(parsers.parse('"{path}" is one of them'))
def it_is_one_of_them(world: World, path: str) -> None:
    assert path in world.instruments


@then(parsers.parse('"{path}" is not one of them'))
def it_is_not_one_of_them(world: World, path: str) -> None:
    assert path not in world.instruments
