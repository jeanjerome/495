"""Scenarios of ``tests/features/lessons.feature``: what a run showed about the project itself,
put to the requester and carried to the next run.

The steps build a run document by hand, one thing the run settled at a time, so that each
scenario states exactly what the harness recorded; the lessons are read through the function,
answered through the function or the CLI, and the last scenario walks a real run to see what
the specifier is given. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from typer.testing import CliRunner

from harness495.core import lessons as memory
from harness495.core.config import load_config
from harness495.core.models import (
    REPLACED_PREFIX,
    CatalogueRole,
    ClarifyAnswer,
    ClarifyRound,
    Decision,
    DecisionKind,
    DecisionMaker,
    Evidence,
    EvidenceKind,
    Finding,
    Intent,
    Iteration,
    Lesson,
    LessonKind,
    Lessons,
    LessonStatus,
    ProjectProfile,
    Retrospective,
    ReviewVerdict,
    Role,
    Run,
    RunMode,
    RunStatus,
    Severity,
    Spec,
    ToolObservation,
    ToolVerdict,
    Verdict,
    Verification,
    VerificationKind,
    Version,
    new_id,
)
from harness495.core.store import RunStore
from harness495.interfaces.cli import app
from tests.conftest import Scenario

scenarios("features/lessons.feature")

BASE = "b" * 40
HEAD = "c" * 40


@dataclass
class World:
    root: Path
    runs: dict[str, Run] = field(default_factory=dict)
    retros: dict[str, Retrospective] = field(default_factory=dict)
    touched: list[Lesson] = field(default_factory=list)
    last: Lesson | None = None
    error: str = ""
    output: str = ""
    exit_code: int = 0
    engine: Any = None
    run: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def store(self) -> RunStore:
        return RunStore(self.root / ".495")

    def the_run(self, run_id: str = "") -> Run:
        assert self.runs, "no run was laid out"
        return self.runs[run_id] if run_id else list(self.runs.values())[-1]

    def iteration(self, run: Run, n: int = 1) -> Iteration:
        for it in run.iterations:
            if it.n == n:
                return it
        it = Iteration(n=n, version=Version(base_commit=BASE, head_commit=HEAD))
        run.iterations.append(it)
        return it

    def read(self, run: Run) -> list[Lesson]:
        """What the run showed, against the criteria as they stand, kept in the document."""
        lessons = self.store.load_lessons()
        touched = memory.reconcile(
            lessons,
            memory.learn(run, load_config(self.root).project, self.retros.get(run.id)),
        )
        self.store.save_lessons(lessons)
        return touched

    def the_lesson(self) -> Lesson:
        if self.last is None:
            assert len(self.touched) == 1, f"expected one lesson, found {self.touched}"
            self.last = self.touched[0]
        return self.last

    def reload(self) -> Lesson:
        """The lesson as the document holds it, after an answer was recorded."""
        held = self.store.load_lessons().get(self.the_lesson().id)
        assert held is not None
        return held

    def of_kind(self, kind: str) -> list[Lesson]:
        return [x for x in self.store.load_lessons().lessons if x.kind is LessonKind(kind)]

    def run_cli(self, *arguments: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLUMNS", "220")
        result = CliRunner().invoke(app, ["--project", str(self.root), *arguments])
        self.output = result.output
        self.exit_code = result.exit_code


@pytest.fixture
def world(tmp_path: Path) -> World:
    root = tmp_path / "target"
    (root / ".495").mkdir(parents=True)
    return World(root=root)


# --------------------------------------------------------------------------- the project


def _criteria(world: World, text: str) -> None:
    (world.root / ".495" / "project.toml").write_text(text, encoding="utf-8")


@given("a project whose criteria declare nothing")
def a_project_declaring_nothing(world: World) -> None:
    _criteria(world, "")


@given(parsers.parse('a project whose criteria declare the command "{command}"'))
def a_project_declaring_a_command(world: World, command: str) -> None:
    _criteria(world, f'[[commands]]\nname = "mutation"\ncommand = "{command}"\nkind = "test"\n')


@given(parsers.parse('a project whose criteria declare the convention "{text}"'))
def a_project_declaring_a_convention(world: World, text: str) -> None:
    _criteria(world, f'conventions = ["{text}"]\n')


# --------------------------------------------------------------------------- what a run showed


@given(parsers.parse('a project whose criteria declare the scope "{globs}"'))
def a_project_declaring_a_scope(world: World, globs: str) -> None:
    paths = ", ".join(f'"{g.strip()}"' for g in globs.split(","))
    _criteria(world, f"[scope]\nallowed_paths = [{paths}]\n")


@given(parsers.parse('a run "{run_id}" on it'))
def a_run_on_it(world: World, run_id: str) -> None:
    world.runs[run_id] = Run(
        id=run_id,
        intent=Intent(text="add subtraction"),
        project_root=str(world.root),
        status=RunStatus.accepted,
        profile=ProjectProfile(root=str(world.root), languages=["python"], base_commit=BASE),
        spec=Spec(approved=True),
    )


@given(parsers.parse('the requester replaced the command of "{vid}" by "{command}"'))
def the_requester_replaced_the_command(world: World, vid: str, command: str) -> None:
    run = world.the_run()
    previous = "mutmut run"
    run.spec.verifications.append(
        Verification(
            id=vid,
            kind=VerificationKind.test,
            description="the mutation run",
            command=command,
            role=CatalogueRole.mutation,
            rationale=f"{REPLACED_PREFIX}{previous}` on the requester's instruction",
        )
    )
    world.iteration(run).instrument_faults.append(
        f"{vid}: fails identically on the base version (exit 2)"
    )
    run.decisions.append(
        Decision(
            id=new_id("dec"),
            kind=DecisionKind.instrument_fault,
            made_by=DecisionMaker.human,
            outcome="recalibrate",
            rationale=f"{vid}: {command}",
            iteration=1,
        )
    )


@given(parsers.parse('the requester corrected the change by hand with "{text}"'))
def the_requester_corrected_by_hand(world: World, text: str) -> None:
    run = world.the_run()
    world.iteration(run).correction_requests.append(f"[human] {text}")
    run.decisions.append(
        Decision(
            id=new_id("dec"),
            kind=DecisionKind.undetermined,
            made_by=DecisionMaker.human,
            outcome="correct",
            rationale=text,
            iteration=1,
        )
    )


@given(
    parsers.parse(
        'the "{perspective}" reviewer of "{run_id}" blocked the change for "{title}" '
        'observed at "{evidence}"'
    )
)
def a_reviewer_blocked_the_change(
    world: World, perspective: str, run_id: str, title: str, evidence: str
) -> None:
    world.the_run(run_id).reviews.append(
        ReviewVerdict(
            intervention_id=new_id("int"),
            perspective=perspective,
            verdict=Verdict.reject,
            findings=[Finding(severity=Severity.blocker, title=title, evidence=evidence)],
        )
    )


@given(parsers.parse('"{run_id}" was allowed "{globs}" for that run alone'))
def a_run_allowed_for_itself(world: World, run_id: str, globs: str) -> None:
    """What ``495 new --allowed-path`` leaves on the run: a scope the file does not declare."""
    scope = world.the_run(run_id).config.project.scope
    scope.allowed_paths = [g.strip() for g in globs.split(",")]


@given(parsers.parse('the change of "{run_id}" was produced within "{globs}" and stayed there'))
def the_change_stayed_within(world: World, run_id: str, globs: str) -> None:
    run = world.the_run(run_id)
    run.spec.allowed_paths = [g.strip() for g in globs.split(",")]
    run.evidence.append(
        Evidence(
            id=new_id("ev"),
            kind=EvidenceKind.scope_check,
            iteration=1,
            subject_version=HEAD,
            passed=True,
            summary=f"2 file(s) changed, all within scope ({globs})",
        )
    )


@given(
    parsers.parse(
        'the specification of "{run_id}" allowed "{globs}" and no version stayed inside it'
    )
)
def no_version_stayed_inside(world: World, run_id: str, globs: str) -> None:
    run = world.the_run(run_id)
    run.spec.allowed_paths = [g.strip() for g in globs.split(",")]
    run.evidence.append(
        Evidence(
            id=new_id("ev"),
            kind=EvidenceKind.scope_check,
            iteration=1,
            subject_version=HEAD,
            passed=False,
            summary="outside allowed paths: README.md",
        )
    )


def _answer(world: World, question: str, option: str, by: DecisionMaker) -> None:
    run = world.the_run()
    run.clarification.rounds.append(
        ClarifyRound(
            n=1,
            intervention_id=new_id("int"),
            answers=[
                ClarifyAnswer(
                    question_id="Q1",
                    question=question,
                    option=option,
                    label=option,
                    taken_by=by,
                )
            ],
        )
    )


@given(parsers.parse('the requester decided "{question}" with "{option}"'))
def the_requester_decided(world: World, question: str, option: str) -> None:
    _answer(world, question, option, DecisionMaker.human)


@given(parsers.parse('the harness decided "{question}" with "{option}" on the requester\'s behalf'))
def the_harness_decided(world: World, question: str, option: str) -> None:
    _answer(world, question, option, DecisionMaker.harness)


@given(parsers.parse('the requester sent the specification back with "{text}"'))
def the_requester_sent_the_specification_back(world: World, text: str) -> None:
    world.the_run().decisions.append(
        Decision(
            id=new_id("dec"),
            kind=DecisionKind.approve_spec,
            made_by=DecisionMaker.human,
            outcome="revise",
            rationale=text,
        )
    )


@given(parsers.parse('the retrospective of "{run_id}" found "{tool}" faulty for the "{role}" role'))
def the_retrospective_found_a_tool_faulty(world: World, run_id: str, tool: str, role: str) -> None:
    world.retros[run_id] = Retrospective(
        run_id=run_id,
        project=world.root.name,
        run_status=RunStatus.accepted,
        source=f"retrospective 2026-09-14 ({world.root.name}, run {run_id})",
        tool_observations=[
            ToolObservation(
                technology="python",
                role=CatalogueRole(role),
                tools=[tool],
                verdict=ToolVerdict.faulty,
                faults=1,
                detail=["V1, iteration 1: fails identically with and without the change (exit 2)"],
            )
        ],
    )


@given("the run is saved in the project's store")
def the_run_is_saved(world: World) -> None:
    world.store.save(world.the_run())


# --------------------------------------------------------------------------- reading them


@when("the harness reads what the run showed")
@given("the harness has read what the run showed")
def the_harness_reads_what_the_run_showed(world: World) -> None:
    world.last = None
    world.touched = world.read(world.the_run())


@when("the harness reads what each run showed")
def the_harness_reads_each_run(world: World) -> None:
    world.last = None
    touched: list[Lesson] = []
    for run in world.runs.values():
        touched = world.read(run)
    world.touched = touched


@when("the requester accepts that lesson")
def the_requester_accepts(world: World) -> None:
    lessons = world.store.load_lessons()
    held = lessons.get(world.the_lesson().id)
    assert held is not None
    memory.accept(held)
    world.store.save_lessons(lessons)


@when(parsers.parse('the requester accepts that lesson as "{text}"'))
def the_requester_accepts_as(world: World, text: str) -> None:
    lessons = world.store.load_lessons()
    held = lessons.get(world.the_lesson().id)
    assert held is not None
    memory.accept(held, text)
    world.store.save_lessons(lessons)


@when(parsers.parse('the requester declines that lesson with the reason "{reason}"'))
def the_requester_declines(world: World, reason: str) -> None:
    lessons = world.store.load_lessons()
    held = lessons.get(world.the_lesson().id)
    assert held is not None
    memory.decline(held, reason)
    world.store.save_lessons(lessons)


@when("the requester declines that lesson with no reason")
def the_requester_declines_with_no_reason(world: World) -> None:
    lessons = world.store.load_lessons()
    held = lessons.get(world.the_lesson().id)
    assert held is not None
    try:
        memory.decline(held, "")
    except memory.LessonError as exc:
        world.error = str(exc)
    world.store.save_lessons(lessons)


@when(parsers.parse('the requester runs "495 {arguments}"'))
def the_requester_runs(world: World, arguments: str, monkeypatch: pytest.MonkeyPatch) -> None:
    world.run_cli(*arguments.split(), monkeypatch=monkeypatch)


# --------------------------------------------------------------------------- what is proposed


@then(parsers.parse('a lesson of kind "{kind}" says "{text}"'))
def a_lesson_says(world: World, kind: str, text: str) -> None:
    held = [x for x in world.of_kind(kind) if text in x.statement]
    assert held, [x.statement for x in world.of_kind(kind)]
    world.last = held[0]


@then(parsers.parse('no lesson of kind "{kind}" is proposed'))
def no_lesson_of_kind(world: World, kind: str) -> None:
    assert world.of_kind(kind) == []


@then(parsers.parse('there is one lesson of kind "{kind}"'))
def one_lesson_of_kind(world: World, kind: str) -> None:
    held = world.of_kind(kind)
    assert len(held) == 1, held
    world.last = held[0]


@then(parsers.parse('that lesson would declare "{value}"'))
def that_lesson_would_declare(world: World, value: str) -> None:
    assert world.the_lesson().value == value


@then(parsers.parse('that lesson\'s lines for project.toml hold "{text}"'))
def that_lessons_lines_hold(world: World, text: str) -> None:
    assert text in memory.toml_lines(world.reload())


@then("that lesson holds what the run observed about it")
def that_lesson_holds_what_was_observed(world: World) -> None:
    observed = world.reload().observed
    assert any(REPLACED_PREFIX in line for line in observed), observed
    assert any("fails identically" in line for line in observed), observed


@then("that lesson holds what both runs observed")
def that_lesson_holds_both(world: World) -> None:
    observed = world.reload().observed
    assert any(".env:1" in line for line in observed), observed
    assert any(".env:4" in line for line in observed), observed


@then("that lesson declares nothing")
def that_lesson_declares_nothing(world: World) -> None:
    assert not world.the_lesson().declares
    assert memory.toml_lines(world.the_lesson()) == ""


@then(parsers.parse('that lesson names the runs "{run_ids}"'))
def that_lesson_names_the_runs(world: World, run_ids: str) -> None:
    assert world.reload().run_ids == [r.strip() for r in run_ids.split(",")]


@then(parsers.parse('that lesson is "{status}"'))
def that_lesson_is(world: World, status: str) -> None:
    assert world.reload().status is LessonStatus(status)


@then(parsers.parse('that lesson carries the reason "{reason}"'))
def that_lesson_carries_the_reason(world: World, reason: str) -> None:
    assert world.reload().reason == reason


@then("that lesson still says what the run observed")
def that_lesson_still_says(world: World) -> None:
    held = world.reload()
    assert "a credential is committed" in held.statement
    assert held.value == "a credential is committed"


@then(parsers.parse('the answer is refused with "{text}"'))
def the_answer_is_refused(world: World, text: str) -> None:
    assert text in world.error


# --------------------------------------------------------------------------- what they change


@then(parsers.parse('the project\'s criteria declare the command "{command}"'))
def the_criteria_declare_the_command(world: World, command: str) -> None:
    project = load_config(world.root).project
    assert any(c.command == command for c in project.commands), project.commands


@then("the criteria name the lesson as the source of that command")
def the_criteria_name_the_lesson(world: World) -> None:
    project = load_config(world.root).project
    sources = [c.source for c in project.commands]
    assert f"lesson {world.the_lesson().id}" in sources, sources


@then(parsers.parse('the project\'s criteria declare the convention "{text}"'))
def the_criteria_declare_the_convention(world: World, text: str) -> None:
    project = load_config(world.root).project
    assert text in project.conventions, project.conventions


@then("the project's criteria declare no convention")
def the_criteria_declare_no_convention(world: World) -> None:
    assert load_config(world.root).project.conventions == []


@then(parsers.parse('the project\'s criteria allow "{glob}"'))
def the_criteria_allow(world: World, glob: str) -> None:
    allowed = load_config(world.root).project.scope.allowed_paths
    assert glob in allowed, allowed


@then(parsers.parse('"{name}" holds "{text}"'))
def the_file_holds(world: World, name: str, text: str) -> None:
    assert text in (world.root / ".495" / name).read_text(encoding="utf-8")


@then(parsers.parse('the output shows "{text}"'))
def the_output_shows(world: World, text: str) -> None:
    assert text in " ".join(world.output.split()), world.output


@then(parsers.parse('the JSON output lists a lesson of kind "{kind}" whose lines hold "{text}"'))
def the_json_lists_a_lesson(world: World, kind: str, text: str) -> None:
    payload = json.loads(world.output)
    held = [x for x in payload if x["kind"] == kind]
    assert held, payload
    assert text in held[0]["toml"]


# --------------------------------------------------------------------------- through a run


@given("the sample project")
def the_sample_project(
    world: World, sample_project: Path, config: Any, engine_factory: Any, scenario: Scenario
) -> None:
    world.root = sample_project
    world.extra["config"] = config
    world.extra["scenario"] = scenario
    world.engine = engine_factory()


@given(parsers.parse('a lesson in force saying "{statement}"'))
def a_lesson_in_force(world: World, statement: str) -> None:
    lessons = Lessons(
        lessons=[
            Lesson(
                id=new_id("les"),
                kind=LessonKind.note,
                statement=statement,
                run_ids=["run-earlier"],
                status=LessonStatus.accepted,
            )
        ]
    )
    world.store.save_lessons(lessons)
    world.extra["statement"] = statement


@when("a change run walks the workflow")
def a_change_run_walks_the_workflow(world: World) -> None:
    run = world.engine.create_run(
        "add subtract to calc", world.root, world.extra["config"], RunMode.change
    )
    world.run = world.engine.run(run.id)


def _prompt_of(world: World, role: Role) -> str:
    calls = [t for t in world.extra["scenario"].calls if t.role is role]
    assert calls, f"no intervention of role {role.value} was made"
    return calls[0].prompt


@then("the facts given to the specifier hold that lesson")
def the_facts_hold_the_lesson(world: World) -> None:
    prompt = _prompt_of(world, Role.specifier)
    facts = prompt.partition("# Established facts (produced by the 495 harness)")[2].partition(
        "# Untrusted content"
    )[0]
    assert "What earlier runs showed about this project" in facts, facts
    assert world.extra["statement"] in facts, facts


@then("the untrusted content given to the specifier does not hold it")
def the_untrusted_does_not_hold_it(world: World) -> None:
    prompt = _prompt_of(world, Role.specifier)
    untrusted = prompt.partition("# Untrusted content")[2].partition("# Instructions")[0]
    assert world.extra["statement"] not in untrusted
