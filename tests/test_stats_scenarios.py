"""Scenarios of ``tests/features/stats.feature``: the runs of a project read as a series.

The steps write run documents into a store, one indicator at a time, so that each scenario
states exactly what the runs recorded; the series is read through the function or through the
CLI. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from typer.testing import CliRunner

from harness495.core.models import (
    REPLACED_PREFIX,
    Finding,
    Intent,
    Iteration,
    Lesson,
    LessonKind,
    Lessons,
    LessonStatus,
    Requirement,
    RequirementStatus,
    ReviewVerdict,
    Run,
    RunStatus,
    Severity,
    Spec,
    Sufficiency,
    Verdict,
    Verification,
    VerificationKind,
    Version,
    new_id,
)
from harness495.core.reading import stats as indicators
from harness495.core.store import RunStore
from harness495.interfaces.cli import app

scenarios("features/stats.feature")

BASE = "b" * 40
HEAD = "c" * 40


@dataclass
class World:
    root: Path
    runs: dict[str, Run] = field(default_factory=dict)
    lessons: Lessons = field(default_factory=Lessons)
    series: indicators.Stats | None = None
    output: str = ""
    exit_code: int = 0

    @property
    def store(self) -> RunStore:
        return RunStore(self.root / ".495")

    def the_run(self, run_id: str) -> Run:
        return self.runs[run_id]

    def the_series(self) -> indicators.Stats:
        assert self.series is not None, "the harness has not read the runs yet"
        return self.series

    def perspective(self, name: str) -> indicators.PerspectiveStat:
        held = [p for p in self.the_series().perspectives if p.perspective == name]
        assert held, self.the_series().perspectives
        return held[0]

    def instrument(self, command: str) -> indicators.InstrumentStat:
        held = [i for i in self.the_series().instruments if i.command == command]
        assert held, self.the_series().instruments
        return held[0]

    def kind(self, name: str) -> indicators.KindStat:
        held = [k for k in self.the_series().kinds if k.kind is VerificationKind(name)]
        assert held, self.the_series().kinds
        return held[0]

    def save(self) -> None:
        for run in self.runs.values():
            self.store.save(run)
        self.store.save_lessons(self.lessons)

    def run_cli(self, *arguments: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLUMNS", "220")
        self.save()
        result = CliRunner().invoke(app, ["--project", str(self.root), *arguments])
        self.output = result.output
        self.exit_code = result.exit_code


@pytest.fixture
def world(tmp_path: Path) -> World:
    root = tmp_path / "target"
    (root / ".495").mkdir(parents=True)
    return World(root=root)


@given("a project with runs")
def a_project_with_runs(world: World) -> None:
    (world.root / ".495" / "project.toml").write_text("", encoding="utf-8")


@given(parsers.parse('a run "{run_id}" that ended "{outcome}" after {n:d} iteration'))
@given(parsers.parse('a run "{run_id}" that ended "{outcome}" after {n:d} iterations'))
def a_run_that_ended(world: World, run_id: str, outcome: str, n: int) -> None:
    run = Run(
        id=run_id,
        intent=Intent(text="add subtraction"),
        project_root=str(world.root),
        status=RunStatus.accepted if outcome == "accept" else RunStatus.rejected,
        spec=Spec(approved=True),
        iterations=[
            Iteration(n=i + 1, version=Version(base_commit=BASE, head_commit=HEAD))
            for i in range(n)
        ],
    )
    run.result.outcome = Verdict(outcome)
    world.runs[run_id] = run


@given(parsers.parse('"{run_id}" assessed {n:d} requirement(s) and cost {cost:f} USD'))
def a_run_assessed_requirements(world: World, run_id: str, n: int, cost: float) -> None:
    run = world.the_run(run_id)
    run.spec.requirements = [
        Requirement(id=f"R{i + 1}", statement=f"r{i + 1}", status=RequirementStatus.satisfied)
        for i in range(n)
    ]
    run.consumption.cost_usd = cost
    run.consumption.interventions = 5


@given(parsers.parse('"{run_id}" named the command "{command}" for "{vid}"'))
def a_run_named_the_command(world: World, run_id: str, command: str, vid: str) -> None:
    world.the_run(run_id).spec.verifications.append(
        Verification(id=vid, kind=VerificationKind.test, description="d", command=command)
    )


@given(
    parsers.parse(
        'the harness recorded "{vid}" of "{run_id}" unable to tell the change from its absence'
    )
)
def the_harness_recorded_a_fault(world: World, vid: str, run_id: str) -> None:
    run = world.the_run(run_id)
    run.iterations[0].instrument_faults.append(f"{vid}: fails identically on the base version")


@given(parsers.parse('the requester had replaced "{previous}" by it'))
def the_requester_had_replaced(world: World, previous: str) -> None:
    run = list(world.runs.values())[-1]
    run.spec.verifications[
        -1
    ].rationale = f"{REPLACED_PREFIX}{previous}` on the requester's instruction"


@given(
    parsers.parse(
        '"{run_id}" carries a "{kind}" verification that reported the same thing with and '
        "without the change"
    )
)
def a_vacuous_verification(world: World, run_id: str, kind: str) -> None:
    world.the_run(run_id).spec.verifications.append(
        Verification(
            id=new_id("V"),
            kind=VerificationKind(kind),
            description="d",
            command="true",
            sufficiency=Sufficiency.vacuous,
        )
    )


@given(parsers.parse('"{run_id}" carries a "{kind}" verification the gate called insufficient'))
def an_insufficient_verification(world: World, run_id: str, kind: str) -> None:
    world.the_run(run_id).spec.verifications.append(
        Verification(
            id=new_id("V"),
            kind=VerificationKind(kind),
            description="d",
            sufficiency=Sufficiency.insufficient,
        )
    )


@given(
    parsers.parse(
        'the "{perspective}" reviewer of "{run_id}" rejected the change and found "{title}" '
        "as a blocker"
    )
)
def a_reviewer_found(world: World, perspective: str, run_id: str, title: str) -> None:
    world.the_run(run_id).reviews.append(
        ReviewVerdict(
            intervention_id=new_id("int"),
            perspective=perspective,
            verdict=Verdict.reject,
            findings=[Finding(severity=Severity.blocker, title=title, evidence="x")],
        )
    )


@given(
    parsers.parse(
        'the review of "{perspective}" on "{run_id}" was discarded after finding "{title}"'
    )
)
def a_discarded_review(world: World, perspective: str, run_id: str, title: str) -> None:
    world.the_run(run_id).reviews.append(
        ReviewVerdict(
            intervention_id=new_id("int"),
            perspective=perspective,
            verdict=Verdict.reject,
            findings=[Finding(severity=Severity.blocker, title=title, evidence="x")],
            discarded=True,
            discard_reason="the tree was altered during the review",
        )
    )


@given(parsers.parse('a lesson of the project is "{first}" and another is "{second}"'))
def lessons_of_the_project(world: World, first: str, second: str) -> None:
    world.lessons = Lessons(
        lessons=[
            Lesson(
                id=new_id("les"),
                kind=LessonKind.note,
                statement=f"a {status} lesson",
                status=LessonStatus(status),
            )
            for status in (first, second)
        ]
    )


@when("the harness reads the runs as a series")
def the_harness_reads_the_series(world: World) -> None:
    world.series = indicators.summarise(world.root.name, list(world.runs.values()), world.lessons)


@when(parsers.parse('the requester runs "495 {arguments}"'))
def the_requester_runs(world: World, arguments: str, monkeypatch: pytest.MonkeyPatch) -> None:
    world.run_cli(*arguments.split(), monkeypatch=monkeypatch)


@then(parsers.parse("the series counts {n:d} run(s)"))
def the_series_counts_runs(world: World, n: int) -> None:
    assert world.the_series().runs == n


@then(parsers.parse('the series counts {n:d} run(s) that ended "{outcome}"'))
def the_series_counts_runs_by_outcome(world: World, n: int, outcome: str) -> None:
    assert world.the_series().by_outcome.get(outcome) == n


@then(parsers.parse("the series counts {total:d} iteration(s), {mean:f} per run produced"))
def the_series_counts_iterations(world: World, total: int, mean: float) -> None:
    assert world.the_series().iterations == total
    assert world.the_series().iterations_mean == mean


@then(parsers.parse("the series states {cost:f} USD per requirement assessed"))
def the_series_states_cost_per_requirement(world: World, cost: float) -> None:
    assert world.the_series().cost_per_requirement == cost


@then("the series states no cost per requirement")
def the_series_states_no_cost(world: World) -> None:
    assert world.the_series().cost_per_requirement is None


@then(parsers.parse('the command "{command}" is listed with {n:d} fault(s)'))
def the_command_is_listed_with_faults(world: World, command: str, n: int) -> None:
    assert world.instrument(command).faults == n


@then(parsers.parse('the command "{command}" is listed as replaced {n:d} time(s)'))
def the_command_is_listed_as_replaced(world: World, command: str, n: int) -> None:
    assert world.instrument(command).replaced == n


@then(parsers.parse('the kind "{kind}" counts {n:d} verification(s) that decided nothing'))
def the_kind_counts_non_discriminating(world: World, kind: str, n: int) -> None:
    assert world.kind(kind).non_discriminating == n


@then(parsers.parse('the kind "{kind}" counts {n:d} verification(s) stated insufficient'))
def the_kind_counts_insufficient(world: World, kind: str, n: int) -> None:
    assert world.kind(kind).insufficient == n


@then(
    parsers.parse(
        'the perspective "{name}" counts {reviews:d} review(s), {rejected:d} rejection(s) and '
        "{findings:d} finding(s)"
    )
)
def the_perspective_counts(
    world: World, name: str, reviews: int, rejected: int, findings: int
) -> None:
    stat = world.perspective(name)
    assert (stat.reviews, stat.rejected, stat.findings) == (reviews, rejected, findings)


@then(parsers.parse('the perspective "{name}" counts {n:d} blocker(s)'))
def the_perspective_counts_blockers(world: World, name: str, n: int) -> None:
    assert world.perspective(name).blockers == n


@then(parsers.parse('the perspective "{name}" counts {n:d} discarded review(s)'))
def the_perspective_counts_discarded(world: World, name: str, n: int) -> None:
    assert world.perspective(name).discarded == n


@then(parsers.parse('the perspective "{name}" states "{line}" as recurring'))
def the_perspective_states_recurring(world: World, name: str, line: str) -> None:
    assert line in world.perspective(name).recurring


@then(parsers.parse('the perspective "{name}" states nothing as recurring'))
def the_perspective_states_nothing_recurring(world: World, name: str) -> None:
    assert world.perspective(name).recurring == []


@then(parsers.parse('the series counts {first:d} lesson(s) "{status}" and {second:d} "{other}"'))
def the_series_counts_lessons(
    world: World, first: int, status: str, second: int, other: str
) -> None:
    by_status = world.the_series().lessons_by_status
    assert by_status.get(status) == first and by_status.get(other) == second, by_status


@then(parsers.parse('the output shows "{text}"'))
def the_output_shows(world: World, text: str) -> None:
    assert text in " ".join(world.output.split()), world.output


@then(parsers.parse("the JSON output states {n:d} run(s) and the kinds it read"))
def the_json_output_states(world: World, n: int) -> None:
    payload = json.loads(world.output)
    assert payload["runs"] == n
    assert "kinds" in payload and "perspectives" in payload and "instruments" in payload
