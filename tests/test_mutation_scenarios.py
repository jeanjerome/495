"""Scenarios of ``tests/features/mutation.feature``: the verifications are measured against
wrong versions of the change, and one they report success on credits no requirement.

The mutant scenarios call the pure readers of ``core.mutation``; the decision scenarios call
``core.decide.assess`` once; the run scenarios walk a change run with the scripted agents of
``conftest`` and read the run, the prompts and the report back. Nothing is asserted outside a
``Then``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.decide import Assessment, assess
from harness495.core.models import (
    DecisionKind,
    Evidence,
    EvidenceKind,
    Requirement,
    RequirementKind,
    RequirementStatus,
    ReviewVerdict,
    Role,
    RunMode,
    RunStatus,
    Spec,
    Verdict,
    Verification,
    VerificationKind,
)
from harness495.core.mutation import Mutant, mutated_source, plan_mutants
from harness495.core.report import render_markdown
from tests.conftest import (
    SAMPLE_MODULE,
    SAMPLE_TEST,
    Scenario,
    bad_producer,
    good_producer,
)

scenarios("features/mutation.feature")


@dataclass
class World:
    diff: str = ""
    commands: list[str] = field(default_factory=list)
    mutants: list[Mutant] = field(default_factory=list)
    source: str = ""
    written: str | None = None
    mutant: Mutant | None = None
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
    return text.replace("\\n", "\n").replace("\\t", "\t")


def _diff(added: dict[str, str]) -> str:
    """A unified diff adding one line to each file, after one line of context."""
    parts: list[str] = []
    for file, line in added.items():
        parts += [
            f"diff --git a/{file} b/{file}",
            "index 0000000..1111111 100644",
            f"--- a/{file}",
            f"+++ b/{file}",
            "@@ -1,1 +1,2 @@",
            " import calc",
            "+" + line,
        ]
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------- the mutants


@given(parsers.parse('a diff of "{file}" that adds the line "{line}"'))
def a_diff_adding(world: World, file: str, line: str) -> None:
    world.diff = _diff({file: _unescape(line)})


@given(parsers.parse('a diff that adds "{first}" to "{one}" and "{second}" to "{other}"'))
def a_diff_adding_to_two_files(world: World, first: str, one: str, second: str, other: str) -> None:
    world.diff = _diff({one: _unescape(first), other: _unescape(second)})


@given(parsers.parse('the project runs its tests with "{command}"'))
def the_project_runs_its_tests_with(world: World, command: str) -> None:
    world.commands.append(command)


@when("the harness plans the mutants")
def the_harness_plans_the_mutants(world: World) -> None:
    world.mutants = plan_mutants(world.diff, 10, world.commands)


@when(parsers.parse("the harness plans at most {limit:d} mutants"))
def the_harness_plans_at_most(world: World, limit: int) -> None:
    world.mutants = plan_mutants(world.diff, limit, world.commands)


@then(parsers.parse('a {operator} mutant writes "{mutated}"'))
def a_mutant_writes(world: World, operator: str, mutated: str) -> None:
    written = [m.mutated for m in world.mutants if m.operator == operator]
    assert _unescape(mutated) in written, world.mutants


@then("no mutant is planned")
def no_mutant_is_planned(world: World) -> None:
    assert world.mutants == []


@then(parsers.parse('the mutants alter "{one}" and "{other}"'))
def the_mutants_alter(world: World, one: str, other: str) -> None:
    assert {m.file for m in world.mutants} == {one, other}, world.mutants


# --------------------------------------------------------------------------- writing one


@given(parsers.parse('the file "{file}" holding "{content}"'))
def the_file_holding(world: World, file: str, content: str) -> None:
    world.source = _unescape(content)


@given(parsers.parse('a mutant replacing line {line:d} "{original}" with "{mutated}"'))
def a_mutant_replacing(world: World, line: int, original: str, mutated: str) -> None:
    world.mutant = Mutant(
        id="m1",
        file="calc.py",
        line=line,
        operator="arithmetic",
        original=_unescape(original),
        mutated=_unescape(mutated),
    )


@when("the harness writes the mutant")
def the_harness_writes_the_mutant(world: World) -> None:
    assert world.mutant is not None
    world.written = mutated_source(world.source, world.mutant)


@then(parsers.parse('the file reads "{content}"'))
def the_file_reads(world: World, content: str) -> None:
    assert world.written == _unescape(content)


@then("the file is left as it was")
def the_file_is_left_as_it_was(world: World) -> None:
    assert world.written is None


# --------------------------------------------------------------------------- the decision


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
    world.spec.verifications.append(
        Verification(id=vid, kind=VerificationKind.test, description=vid, command="true")
    )


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


@given(parsers.parse('a mutant no verification reported, naming {rid}, saying "{summary}"'))
def a_surviving_mutant(world: World, rid: str, summary: str) -> None:
    world.evidence.append(
        Evidence(
            id="ev-mutant",
            kind=EvidenceKind.mutation_check,
            iteration=1,
            requirement_ids=[rid],
            passed=False,
            summary=summary,
        )
    )


@given(parsers.parse("a mutant {vid} reported"))
def a_killed_mutant(world: World, vid: str) -> None:
    world.evidence.append(
        Evidence(
            id="ev-mutant",
            kind=EvidenceKind.mutation_check,
            iteration=1,
            verification_id=vid,
            passed=True,
            summary=f"m1 calc.py:9 (arithmetic): {vid} reported it (exit 1)",
        )
    )


@given("a reviewer accepted the change")
def a_reviewer_accepted(world: World) -> None:
    world.reviews.append(
        ReviewVerdict(intervention_id="int-p", perspective="p", verdict=Verdict.accept)
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


# --------------------------------------------------------------------------- through the engine

WEAK_TEST = """from calc import subtract


def test_subtract():
    assert subtract(5, 0) == 5
"""
"""A test of subtract that no wrong sign can fail: 5 - 0 and 5 + 0 are the same number."""


def weak_design(cwd: Path) -> None:
    (cwd / "tests" / "test_subtract.py").write_text(WEAK_TEST, encoding="utf-8")


def weak_producer(cwd: Path) -> None:
    """The behaviour implemented, and the producer's own test as weak as the designed one, so
    that no command of the run tells `a - b` from `a + b`."""
    (cwd / "calc.py").write_text(
        SAMPLE_MODULE + "\n\ndef subtract(a: int, b: int) -> int:\n    return a - b\n",
        encoding="utf-8",
    )
    (cwd / "tests" / "test_calc.py").write_text(
        SAMPLE_TEST + "\n\nfrom calc import subtract\n\n\ndef test_subtract_by_zero():\n"
        "    assert subtract(5, 0) == 5\n",
        encoding="utf-8",
    )


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    world.extra["project"] = sample_project
    world.extra["config"] = config
    world.extra["scenario"] = scenario
    # V1 runs the designed test, so that what the mutants meet is the test written for R1.
    scenario.spec["verifications"][0]["command"] = (
        f"{sys.executable} -m pytest -q -p no:cacheprovider tests/test_subtract.py"
    )
    world.engine = engine_factory()


@given(parsers.parse('the only test of the new behaviour checks "{assertion}"'))
def the_only_test_checks(world: World, assertion: str) -> None:
    assert assertion in WEAK_TEST
    world.extra["scenario"].designers = [weak_design]
    world.extra["scenario"].producers = [weak_producer]


@given("the producer gets the behaviour wrong once")
def the_producer_gets_it_wrong_once(world: World) -> None:
    world.extra["scenario"].producers = [bad_producer, good_producer]


@given(parsers.parse('a lint verification that names "{file}"'))
def a_lint_verification_naming(world: World, file: str) -> None:
    spec = world.extra["scenario"].spec
    spec["requirements"].append(
        {
            "id": "R3",
            "statement": f"{file} stays a module python can compile",
            "kind": "non_regression",
            "rationale": "the project's own convention",
            "verification_ids": ["V3"],
        }
    )
    spec["verifications"].append(
        {
            "id": "V3",
            "kind": "lint",
            "description": f"{file} compiles",
            "command": f"{sys.executable} -m py_compile {file}",
            "to_create": False,
        }
    )


@given("the mutation check is allowed no mutant")
def the_mutation_check_is_disabled(world: World) -> None:
    world.extra["config"].budget.max_mutants = 0


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


def _mutation_checks(world: World, n: int) -> list[Evidence]:
    it = world.run.iterations[n - 1]
    return [
        e
        for e in (world.run.evidence_by_id(x) for x in it.evidence_ids)
        if e is not None and e.kind is EvidenceKind.mutation_check
    ]


@then(parsers.parse('a mutant of iteration {n:d} was reported: "{text}"'))
def a_mutant_was_reported(world: World, n: int, text: str) -> None:
    checks = _mutation_checks(world, n)
    assert any(e.passed is True and text in e.summary for e in checks), [e.summary for e in checks]


@then(parsers.parse('a mutant of iteration {n:d} went unreported: "{text}"'))
def a_mutant_went_unreported(world: World, n: int, text: str) -> None:
    checks = _mutation_checks(world, n)
    assert any(e.passed is False and text in e.summary for e in checks), [e.summary for e in checks]


@then("every wrong version of the change was reported")
def every_wrong_version_was_reported(world: World) -> None:
    checks = _mutation_checks(world, 1)
    assert checks and all(e.passed is True for e in checks), [e.summary for e in checks]


@then("no wrong version of the change was measured")
def no_wrong_version_was_measured(world: World) -> None:
    assert _mutation_checks(world, 1) == []


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
