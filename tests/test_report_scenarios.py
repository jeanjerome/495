"""Scenarios of ``tests/features/report.feature``: the Markdown report puts, under each
requirement, the scenario of every verification that carries one and what that verification
reported on the evaluated commit.

The rendering scenarios build a run document by hand and read the report back; the engine
scenario walks a change run with the scripted agents of ``conftest`` and reads the report the
same way. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from harness495.core.models import (
    BehaviourScenario,
    Evidence,
    EvidenceKind,
    Intent,
    Iteration,
    Requirement,
    RequirementStatus,
    Run,
    RunMode,
    Spec,
    Sufficiency,
    Verification,
    VerificationKind,
    Version,
)
from harness495.core.report import render_markdown

scenarios("features/report.feature")

BASE = "b" * 40
HEAD = "h" * 40


@dataclass
class World:
    run: Run | None = None
    report: str = ""
    section: str = ""
    engine: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def the_run(self) -> Run:
        assert self.run is not None, "no run was given"
        return self.run

    def verification(self, vid: str) -> Verification:
        v = self.the_run().spec.verification(vid)
        assert v is not None, f"no verification {vid}"
        return v

    def the_section(self) -> str:
        assert self.section, "no section was read"
        return self.section


@pytest.fixture
def world() -> World:
    return World()


def _steps(text: str) -> list[str]:
    return [s.strip() for s in text.split("|") if s.strip()]


def _section(report: str, heading: str) -> str:
    """The text under a ``###`` heading, up to the next heading of any level."""
    after = report.split(heading + "\n", 1)
    if len(after) < 2:
        return ""
    body = after[1]
    for line in body.splitlines():
        if line.startswith("#"):
            return body.split(line, 1)[0]
    return body


# --------------------------------------------------------------------------- the run document


@given(parsers.parse('a run with the requirement "{rid}" "{statement}" verified by "{vid}"'))
def a_run_with_a_requirement(world: World, rid: str, statement: str, vid: str) -> None:
    world.run = Run(
        id="run-report",
        intent=Intent(text="add subtract to calc"),
        project_root="/tmp/project",
        spec=Spec(requirements=[Requirement(id=rid, statement=statement, verification_ids=[vid])]),
        iterations=[Iteration(n=1, version=Version(base_commit=BASE, head_commit=HEAD))],
    )


@given(parsers.parse('the run also has the requirement "{rid}" "{statement}" verified by "{vid}"'))
def the_run_also_has_a_requirement(world: World, rid: str, statement: str, vid: str) -> None:
    world.the_run().spec.requirements.append(
        Requirement(id=rid, statement=statement, verification_ids=[vid])
    )


@given(
    parsers.parse(
        '"{vid}" is a test to create with the scenario given "{given}" when "{when}" then "{then}"'
    )
)
def a_test_to_create_with_a_scenario(
    world: World, vid: str, given: str, when: str, then: str
) -> None:
    world.the_run().spec.verifications.append(
        Verification(
            id=vid,
            kind=VerificationKind.test,
            description="a test",
            command="pytest -q tests/test_calc.py",
            to_create=True,
            scenario=BehaviourScenario(given=_steps(given), when=_steps(when), then=_steps(then)),
        )
    )


@given(parsers.parse('"{vid}" is an existing test with no scenario'))
def an_existing_test_without_a_scenario(world: World, vid: str) -> None:
    world.the_run().spec.verifications.append(
        Verification(
            id=vid, kind=VerificationKind.test, description="the suite", command="pytest -q"
        )
    )


@given(parsers.parse('the requirement "{rid}" stands "{status}"'))
def the_requirement_stands(world: World, rid: str, status: str) -> None:
    r = next(x for x in world.the_run().spec.requirements if x.id == rid)
    r.status = RequirementStatus(status)


@given(parsers.parse('"{vid}" is vacuous because "{rationale}"'))
def the_verification_is_vacuous(world: World, vid: str, rationale: str) -> None:
    v = world.verification(vid)
    v.sufficiency = Sufficiency.vacuous
    v.rationale = rationale


def _command_result(
    world: World, vid: str, eid: str, passed: bool, summary: str, version: str, current: bool
) -> None:
    run = world.the_run()
    run.evidence.append(
        Evidence(
            id=eid,
            kind=EvidenceKind.command_result,
            iteration=1,
            subject_version=version,
            verification_id=vid,
            passed=passed,
            summary=summary,
        )
    )
    if current:
        it = run.current_iteration
        assert it is not None
        it.evidence_ids.append(eid)


@given(parsers.parse('in the current iteration "{vid}" passed on the evaluated commit as "{eid}"'))
def passed_on_the_evaluated_commit(world: World, vid: str, eid: str) -> None:
    _command_result(world, vid, eid, True, "exit 0", HEAD, True)


@given(
    parsers.parse(
        'in the current iteration "{vid}" failed on the evaluated commit as "{eid}" reporting "{summary}"'
    )
)
def failed_on_the_evaluated_commit(world: World, vid: str, eid: str, summary: str) -> None:
    _command_result(world, vid, eid, False, summary, HEAD, True)


@given(parsers.parse('"{vid}" was run on the base version only, as "{eid}"'))
def run_on_the_base_version_only(world: World, vid: str, eid: str) -> None:
    _command_result(world, vid, eid, True, "exit 0", BASE, False)


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


# --------------------------------------------------------------------------- the report


@when("the report is rendered")
def the_report_is_rendered(world: World) -> None:
    world.report = render_markdown(world.the_run())


@then(parsers.parse('the report has the section "{heading}"'))
def the_report_has_the_section(world: World, heading: str) -> None:
    world.section = _section(world.report, heading)
    assert world.section, world.report


@then(parsers.parse('under it the line "{line}"'))
def under_it_the_line(world: World, line: str) -> None:
    assert line in world.the_section().splitlines(), world.section


@then(parsers.parse('under it a line saying "{text}"'))
def under_it_a_line_saying(world: World, text: str) -> None:
    assert any(text in line for line in world.the_section().splitlines()), world.section


@then(parsers.parse('under it the Gherkin block "{block}"'))
def under_it_the_gherkin_block(world: World, block: str) -> None:
    section = world.the_section()
    fenced = section.split("```gherkin\n", 1)
    assert len(fenced) == 2, section
    body = fenced[1].split("```", 1)[0]
    assert [line.strip() for line in body.strip().splitlines()] == _steps(block), body


@then(parsers.parse('the report has the row "{row}"'))
def the_report_has_the_row(world: World, row: str) -> None:
    assert any(line.startswith(row) for line in world.report.splitlines()), world.report


@then(parsers.parse('the report has no section for "{rid}"'))
def the_report_has_no_section_for(world: World, rid: str) -> None:
    assert f"### {rid} " not in world.report, world.report
