"""Scenarios of ``tests/features/reach.feature``: the lines the change adds are crossed with
what the verifications execute, and a line none of them ran credits no requirement.

The report and crossing scenarios call the pure readers of ``core.reach``; the decision
scenarios call ``core.decide.assess`` once; the run scenarios walk a change run with the
scripted agents of ``conftest``, with coverage.py making the measure for real, and read the
run, the prompts and the report back. The last section reaches ``core.engine.checks.coverage``
on its own, through a ``RunServices`` whose sandbox writes the report the tool would have
written, so that a change with no line to cross, a tool that wrote nothing and a run the
requester stopped are measured without a run reaching ``produced``. Nothing is asserted
outside a ``Then``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.engine.checks.coverage import reach
from harness495.core.git import diff as repo_diff
from harness495.core.models import (
    CatalogueRole,
    DecisionKind,
    Evidence,
    EvidenceKind,
    ProjectProfile,
    Requirement,
    RequirementKind,
    RequirementStatus,
    ReviewVerdict,
    Role,
    RoleCoverage,
    RunMode,
    RunStatus,
    Spec,
    Verdict,
    Verification,
    VerificationKind,
)
from harness495.core.reading.decide import Assessment, assess
from harness495.core.reading.diff import code_lines
from harness495.core.reading.reach import (
    READERS,
    REPORT_DIR,
    Hits,
    Instrumented,
    Reading,
    cross,
    instrument,
)
from harness495.core.report import render_markdown
from tests.conftest import (
    SAMPLE_MODULE,
    SAMPLE_TEST,
    Measured,
    Region,
    Reply,
    Scenario,
    git,
    measure,
)

scenarios("features/reach.feature")

COVERAGERC = "[report]\nshow_missing = true\n"
"""What makes the profile report coverage.py as the tool of the python `coverage` role."""

GUARD = """

def subtract(a: int, b: int) -> int:
    if b < 0:
        raise ValueError("b must not be negative")
    return a - b
"""
"""A change whose guard no test of the run reaches: every test calls subtract with a b that
is zero or more, so the raise is never executed. The comparison is still constrained — a test
calls subtract(5, 0), which `b <= 0` would raise on — so what the coverage check reports is
not what the mutation check reports."""

GUARD_TEST = (
    SAMPLE_TEST + "\n\nfrom calc import subtract\n\n\ndef test_subtract():\n"
    "    assert subtract(5, 3) == 2\n    assert subtract(5, 0) == 5\n"
)


@dataclass
class World:
    hits: Hits = field(default_factory=dict)
    diff: str = ""
    reading: Reading | None = None
    instrumented: Instrumented | None = None
    technology: str = ""
    tools: list[str] = field(default_factory=list)
    command: str = ""
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

    def crossed(self) -> Reading:
        assert self.reading is not None, "the harness has not crossed the change yet"
        return self.reading


@pytest.fixture
def world() -> World:
    return World()


def _unescape(text: str) -> str:
    return text.replace("\\n", "\n")


def _diff(file: str, line: str, number: int) -> str:
    """A unified diff adding one line to a file, at the number the scenario names."""
    context = ["    pass"] * (number - 1)
    return (
        "\n".join(
            [
                f"diff --git a/{file} b/{file}",
                "index 0000000..1111111 100644",
                f"--- a/{file}",
                f"+++ b/{file}",
                f"@@ -1,{len(context)} +1,{number} @@",
                *(f" {c}" for c in context),
                f"+{line}",
            ]
        )
        + "\n"
    )


# --------------------------------------------------------------------------- the reports


@given(parsers.parse("a \"{format}\" report '{text}'"), target_fixture="report")
def a_report(format: str, text: str) -> tuple[str, str]:
    return format, _unescape(text)


@when("the harness reads the report")
def the_harness_reads_the_report(world: World, report: tuple[str, str]) -> None:
    world.hits = READERS[report[0]](report[1])


@then(parsers.parse('it says line {ran:d} of "{file}" ran and line {missed:d} did not'))
def it_says_which_lines_ran(world: World, ran: int, file: str, missed: int) -> None:
    assert world.hits.get(file, {}).get(ran, 0) > 0, world.hits
    assert world.hits.get(file, {}).get(missed, -1) == 0, world.hits


@then("the report holds no line")
def the_report_holds_no_line(world: World) -> None:
    assert world.hits == {}


# --------------------------------------------------------------------------- the crossing


@given(parsers.parse('a diff of "{file}" that adds a line at line {number:d}'))
def a_diff_adding_a_line(world: World, file: str, number: int) -> None:
    world.diff = _diff(file, '    raise ValueError("b must not be negative")', number)


@given(parsers.parse('a report where line {number:d} of "{file}" ran {hits:d} time(s)'))
def a_report_where_a_line_ran(world: World, number: int, file: str, hits: int) -> None:
    world.hits.setdefault(file, {})[number] = hits


@when("the harness crosses the change with the report")
def the_harness_crosses_the_change(world: World) -> None:
    world.reading = cross(code_lines(world.diff), world.hits, ["V1"], ["coverage.py"])


@then(parsers.parse('line {number:d} of "{file}" was executed by no verification'))
def a_line_was_executed_by_nothing(world: World, number: int, file: str) -> None:
    missed = [(u.file, u.line) for u in world.crossed().unreached]
    assert (file, number) in missed, missed


@then("every line the change adds was executed")
def every_line_was_executed(world: World) -> None:
    assert not world.crossed().missed, world.crossed().unreached


@then("no line of the change is charged")
def no_line_is_charged(world: World) -> None:
    assert not world.crossed().missed, world.crossed().unreached


@then("no file is named as one the tool did not instrument")
def no_file_is_named_as_uninstrumented(world: World) -> None:
    assert world.crossed().unmeasured == []


@then(parsers.parse('"{file}" is named as a file the tool did not instrument'))
def a_file_is_named_as_uninstrumented(world: World, file: str) -> None:
    assert file in world.crossed().unmeasured, world.crossed().unmeasured


# --------------------------------------------------------------------------- the command


@given(parsers.parse('a project measuring the coverage role of "{technology}" with "{tool}"'))
def a_project_measuring_the_role(world: World, technology: str, tool: str) -> None:
    world.technology, world.tools = technology, [tool]


@given(parsers.parse('a project measuring the coverage role of "{technology}" with nothing'))
def a_project_measuring_nothing(world: World, technology: str) -> None:
    world.technology, world.tools = technology, []


@given(parsers.parse('a test command "{command}"'))
def a_test_command(world: World, command: str) -> None:
    world.command = command


@when("the harness instruments the command")
def the_harness_instruments_the_command(world: World) -> None:
    world.instrumented = instrument(world.technology, world.tools, world.command)


@then(parsers.parse('the instrumented command holds "{text}"'))
def the_instrumented_command_holds(world: World, text: str) -> None:
    assert world.instrumented is not None, "no command was derived"
    assert text in world.instrumented.command, world.instrumented.command


@then("no instrumented command is derived")
def no_instrumented_command(world: World) -> None:
    assert world.instrumented is None, world.instrumented


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


@given(parsers.parse('a line no verification executed, naming {rid}, saying "{summary}"'))
def an_unexecuted_line(world: World, rid: str, summary: str) -> None:
    world.evidence.append(
        Evidence(
            id="ev-reach",
            kind=EvidenceKind.coverage_check,
            iteration=1,
            requirement_ids=[rid],
            passed=False,
            summary=summary,
        )
    )


@given(parsers.parse("a coverage check {vid} passed"))
def a_passing_coverage_check(world: World, vid: str) -> None:
    world.evidence.append(
        Evidence(
            id="ev-reach",
            kind=EvidenceKind.coverage_check,
            iteration=1,
            passed=True,
            summary=f"{vid} under coverage.py executed the 4 line(s) the change adds",
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


def guard_producer(cwd: Path) -> None:
    """The behaviour implemented behind a guard the tests never take."""
    (cwd / "calc.py").write_text(SAMPLE_MODULE + GUARD, encoding="utf-8")
    (cwd / "tests" / "test_calc.py").write_text(GUARD_TEST, encoding="utf-8")


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    world.extra["project"] = sample_project
    world.extra["config"] = config
    world.extra["scenario"] = scenario
    world.engine = engine_factory()


@given("the sample project measuring its coverage")
def the_sample_project_measuring_coverage(
    world: World, sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    (sample_project / ".coveragerc").write_text(COVERAGERC, encoding="utf-8")
    git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".", cwd=sample_project)
    git(
        "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "coverage", cwd=sample_project
    )
    the_sample_project(world, sample_project, config, engine_factory, scenario)


@given("the change carries a guard no test reaches")
def the_change_carries_a_guard(world: World) -> None:
    world.extra["scenario"].producers = [guard_producer]


@given("the coverage check is allowed no command")
def the_coverage_check_is_disabled(world: World) -> None:
    world.extra["config"].budget.max_coverage_commands = 0


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


def _coverage_checks(world: World, n: int) -> list[Evidence]:
    it = world.run.iterations[n - 1]
    return [
        e
        for e in (world.run.evidence_by_id(x) for x in it.evidence_ids)
        if e is not None and e.kind is EvidenceKind.coverage_check
    ]


@then(parsers.parse("the coverage check of iteration {n:d} {result:w}"))
def the_coverage_check_reported(world: World, n: int, result: str) -> None:
    checks = _coverage_checks(world, n)
    assert checks, "no coverage was measured"
    assert checks[-1].passed is (result == "passed"), checks[-1].summary


@then(parsers.parse('the coverage check of iteration {n:d} says "{text}"'))
def the_coverage_check_says(world: World, n: int, text: str) -> None:
    checks = _coverage_checks(world, n)
    assert any(text in e.summary for e in checks), [e.summary for e in checks]


@then("no coverage was measured")
def no_coverage_was_measured(world: World) -> None:
    assert _coverage_checks(world, 1) == []


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


@then(parsers.parse('the run says "{text}"'))
def the_run_says(world: World, text: str) -> None:
    assert any(text in w for w in world.run.warnings), world.run.warnings


# --------------------------------------------------------------------- the check on its own

SUBTRACT = SAMPLE_MODULE + "\n\ndef subtract(a: int, b: int) -> int:\n    return a - b\n"
ANOTHER_TEST = "def test_nothing():\n    assert True\n"


@given("a version under review whose change adds a test file only", target_fixture="region")
def a_version_adding_a_test_file(produced_version: Callable[..., Region]) -> Region:
    return produced_version({"tests/test_extra.py": ANOTHER_TEST})


@given("a version under review whose change adds a line of source", target_fixture="region")
def a_version_adding_source(produced_version: Callable[..., Region]) -> Region:
    return produced_version({"calc.py": SUBTRACT})


@given(parsers.parse("the project measures its {technology} coverage with {tool}"))
def the_project_measures_its_coverage(region: Region, technology: str, tool: str) -> None:
    region.run.profile = ProjectProfile(
        root=str(region.root),
        role_coverage=[
            RoleCoverage(technology=technology, role=CatalogueRole.coverage, tools=[tool])
        ],
    )


@given(
    parsers.parse(
        "a test command {vid} that passed in {seconds:d}s, which the requirement {rid} leans on"
    )
)
def a_test_command_a_requirement_leans_on(region: Region, vid: str, seconds: int, rid: str) -> None:
    region.verification(vid, requirement=rid)
    region.ran_command(vid, seconds=float(seconds), output="4 passed in 0.3s")


@given("the instrumented run exits 1 and writes no report")
def the_instrumented_run_writes_no_report(region: Region) -> None:
    region.answers(Reply(exit_code=1, output="the tool could not start"))


@given("the instrumented run writes a report holding no hit for the change")
def the_instrumented_run_writes_a_report_with_no_hit(region: Region) -> None:
    files: dict[str, dict[str, list[int]]] = {}
    for added in code_lines(repo_diff(region.root, region.base, region.head)):
        rows = files.setdefault(added.file, {"executed_lines": [], "missing_lines": []})
        rows["missing_lines"].append(added.line)
    region.answers(
        Reply(
            output="4 passed in 0.3s",
            writes={f"{REPORT_DIR}/coverage.json": json.dumps({"files": files})},
        )
    )


@given("the requester asked the run to stop")
def the_requester_asked_the_run_to_stop(region: Region) -> None:
    region.services.stop_requested = True


@when("the coverage check measures the version", target_fixture="measured")
def the_coverage_check_measures_the_version(region: Region) -> Measured:
    return measure(
        lambda: reach(region.services, region.run, region.iteration, list(region.run.evidence))
    )


def _check(measured: Measured) -> Evidence:
    assert len(measured.evidence) == 1, [e.summary for e in measured.evidence]
    return measured.evidence[0]


@then("no command was run under the coverage tool")
def no_command_was_run_under_the_tool(region: Region) -> None:
    assert region.services.fake_sandbox.commands == [], region.services.fake_sandbox.commands


@then("the coverage check left no evidence")
def the_coverage_check_left_no_evidence(measured: Measured) -> None:
    assert measured.evidence == [], [e.summary for e in measured.evidence]


@then(parsers.parse('the run warns "{text}"'))
def the_run_warns(region: Region, text: str) -> None:
    assert any(text in w for w in region.services.warnings), region.services.warnings


@then("the coverage check measured nothing")
def the_coverage_check_measured_nothing(measured: Measured) -> None:
    assert _check(measured).passed is None, _check(measured).summary


@then("the coverage check charges no requirement")
def the_coverage_check_charges_no_requirement(measured: Measured) -> None:
    assert _check(measured).requirement_ids == [], _check(measured).requirement_ids


@then("the coverage check failed")
def the_coverage_check_failed(measured: Measured) -> None:
    assert _check(measured).passed is False, _check(measured).summary


@then(parsers.parse("the coverage check names {rid}"))
def the_coverage_check_names(measured: Measured, rid: str) -> None:
    assert rid in _check(measured).requirement_ids, _check(measured).requirement_ids


@then("what the instrumented run printed is kept under the run")
def the_output_is_kept(region: Region, measured: Measured) -> None:
    ref = _check(measured).output_ref
    assert ref is not None and region.services.store.written.get(ref) == "4 passed in 0.3s"


@then("the run stops rather than crossing anything")
def the_run_stops_rather_than_crossing(measured: Measured) -> None:
    assert measured.interrupted, "the check crossed the change with an interrupted run"


@then("nothing of the measure is left in the worktree")
def nothing_of_the_measure_is_left(region: Region) -> None:
    assert not (region.root / REPORT_DIR).exists()
