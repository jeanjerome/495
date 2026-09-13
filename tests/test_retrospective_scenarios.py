"""Scenarios of ``tests/features/retrospective.feature``: what a run showed about the tools
that measure a catalogue role, and the rows the catalogue takes from it.

The steps build a run document by hand, one verification and one measurement at a time, so
that each scenario states exactly what the harness recorded; the retrospective is read
through the function or through the CLI, and nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from typer.testing import CliRunner

from harness495.core.coverage import ROLES_BY_TECHNOLOGY
from harness495.core.models import (
    CatalogueRole,
    Evidence,
    EvidenceKind,
    Intent,
    Iteration,
    ProjectProfile,
    Retrospective,
    RoleCoverage,
    Run,
    Spec,
    ToolObservation,
    Verification,
    VerificationKind,
    Version,
    new_id,
)
from harness495.core.retro import retrospect
from harness495.core.store import RunStore
from harness495.interfaces.cli import app

scenarios("features/retrospective.feature")

BASE = "b" * 40
HEAD = "c" * 40
RUN_ID = "run-retro"


@dataclass
class World:
    root: Path
    run: Run | None = None
    retros: list[Retrospective] = field(default_factory=list)
    last: ToolObservation | None = None
    output: str = ""
    exit_code: int = 0

    def the_run(self) -> Run:
        assert self.run is not None, "no run was laid out"
        return self.run

    def the_retro(self) -> Retrospective:
        assert self.retros, "the harness has not written the retrospective yet"
        return self.retros[-1]

    def the_observation(self) -> ToolObservation:
        if self.last is None:
            observations = self.the_retro().tool_observations
            assert len(observations) == 1, f"expected one observation, found {observations}"
            self.last = observations[0]
        return self.last

    def verification(self, vid: str) -> Verification:
        v = self.the_run().spec.verification(vid)
        assert v is not None, f"no verification {vid}"
        return v

    def iteration(self, n: int) -> Iteration:
        run = self.the_run()
        for it in run.iterations:
            if it.n == n:
                return it
        it = Iteration(n=n, version=Version(base_commit=BASE, head_commit=HEAD))
        run.iterations.append(it)
        return it

    def measure(
        self,
        vid: str,
        n: int,
        passed: bool | None,
        control_exit: int | None,
        summary: str | None = None,
    ) -> Evidence:
        """Record a run of ``vid`` on the change in iteration ``n``, and its control run."""
        run = self.the_run()
        v = self.verification(vid)
        it = self.iteration(n)
        if passed is None:
            exit_code = None
        else:
            exit_code = 0 if passed else (2 if v.role is CatalogueRole.mutation else 1)
        subject = Evidence(
            id=new_id("ev"),
            kind=EvidenceKind.command_result,
            iteration=n,
            subject_version=HEAD,
            verification_id=vid,
            command=v.command,
            exit_code=exit_code,
            expected_exit_code=0,
            passed=passed,
            summary=summary or f"exit {exit_code} (expected 0)",
        )
        run.evidence.append(subject)
        it.evidence_ids.append(subject.id)
        if control_exit is not None:
            control = Evidence(
                id=new_id("ev"),
                kind=EvidenceKind.instrument_check,
                iteration=n,
                subject_version=BASE,
                verification_id=vid,
                command=v.command,
                exit_code=control_exit,
                expected_exit_code=0,
                passed=None,
                summary=f"control run on the base version: exit {control_exit}",
            )
            run.evidence.append(control)
            it.evidence_ids.append(control.id)
        return subject

    def run_cli(self, *arguments: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLUMNS", "200")
        result = CliRunner().invoke(app, ["--project", str(self.root), *arguments])
        self.output = result.output
        self.exit_code = result.exit_code


@pytest.fixture
def world(tmp_path: Path) -> World:
    root = tmp_path / "proj"
    root.mkdir()
    return World(root=root)


@given(parsers.parse('a run on a Python project measuring "{role}" with "{tool}"'))
def a_run_on_a_python_project(world: World, role: str, tool: str) -> None:
    coverage = [
        RoleCoverage(technology="python", role=r, tools=[], markers=[])
        for r in ROLES_BY_TECHNOLOGY["python"]
    ]
    for row in coverage:
        if row.role is CatalogueRole(role):
            row.tools = [tool]
            row.markers = [f"dependency {tool} in pyproject.toml"]
    world.run = Run(
        id=RUN_ID,
        intent=Intent(text="add subtraction"),
        project_root=str(world.root),
        profile=ProjectProfile(
            root=str(world.root), languages=["python"], role_coverage=coverage, base_commit=BASE
        ),
        spec=Spec(approved=True),
    )


@given(
    parsers.parse(
        'the verification "{vid}" of the run measures the role "{role}" with the command "{command}"'
    )
)
def a_verification_with_a_role(world: World, vid: str, role: str, command: str) -> None:
    world.the_run().spec.verifications.append(
        Verification(
            id=vid,
            kind=VerificationKind.test,
            description=f"{role} measured by {command}",
            command=command,
            role=CatalogueRole(role),
        )
    )


@given(parsers.parse('the verification "{vid}" of the run has no role and the command "{command}"'))
def a_verification_without_a_role(world: World, vid: str, command: str) -> None:
    world.the_run().spec.verifications.append(
        Verification(id=vid, kind=VerificationKind.test, description="the suite", command=command)
    )


@given(
    parsers.parse('in iteration {n:d} "{vid}" passed on the change and failed on the base version')
)
def passed_and_failed_without(world: World, n: int, vid: str) -> None:
    world.measure(vid, n, True, 1)


@given(
    parsers.parse('in iteration {n:d} "{vid}" failed on the change and passed on the base version')
)
def failed_and_passed_without(world: World, n: int, vid: str) -> None:
    world.measure(vid, n, False, 0)


@given(
    parsers.parse('in iteration {n:d} "{vid}" passed on the change and passed on the base version')
)
def passed_and_passed_without(world: World, n: int, vid: str) -> None:
    world.measure(vid, n, True, 0)


@given(
    parsers.parse(
        'in iteration {n:d} "{vid}" failed on the change and on the base version, and the harness recorded the fault'
    )
)
def failed_on_both(world: World, n: int, vid: str) -> None:
    subject = world.measure(vid, n, False, subject_exit_of(world, vid))
    world.iteration(n).instrument_faults.append(
        f"{vid}: fails identically on the base version {BASE[:12]} (exit {subject.exit_code}), "
        "so no edit inside the change can make it report success"
    )


def subject_exit_of(world: World, vid: str) -> int:
    return 2 if world.verification(vid).role is CatalogueRole.mutation else 1


@given(parsers.parse('in iteration {n:d} "{vid}" timed out on the change'))
def timed_out(world: World, n: int, vid: str) -> None:
    world.measure(vid, n, False, None, summary="timed out")


@given(
    parsers.parse(
        'in iteration {n:d} "{vid}" passed on the change and was not run on the base version'
    )
)
def passed_without_control(world: World, n: int, vid: str) -> None:
    world.measure(vid, n, True, None)


@given(
    parsers.parse(
        'in iteration {n:d} "{vid}" failed on the change and was not run on the base version'
    )
)
def failed_without_control(world: World, n: int, vid: str) -> None:
    world.measure(vid, n, False, None)


@given(parsers.parse('the command of "{vid}" passed on the base version before any change'))
def baseline_passed(world: World, vid: str) -> None:
    _baseline(world, vid, 0)


@given(parsers.parse('the command of "{vid}" failed on the base version before any change'))
def baseline_failed(world: World, vid: str) -> None:
    _baseline(world, vid, 1)


def _baseline(world: World, vid: str, exit_code: int) -> None:
    v = world.verification(vid)
    world.the_run().evidence.append(
        Evidence(
            id=new_id("ev"),
            kind=EvidenceKind.baseline,
            iteration=0,
            subject_version=BASE,
            verification_id=vid,
            command=v.command,
            exit_code=exit_code,
            expected_exit_code=0,
            passed=None,
            summary=f"never run before: exit {exit_code} on the base version",
        )
    )


@given(parsers.parse('the requester replaced the command of "{vid}" by "{command}"'))
def the_requester_replaced_the_command(world: World, vid: str, command: str) -> None:
    v = world.verification(vid)
    v.rationale = f"replaced `{v.command}` on the requester's instruction"
    v.command = command
    for it in world.the_run().iterations:
        it.instrument_faults = [f for f in it.instrument_faults if not f.startswith(f"{vid}:")]


@given("the run is saved in the project's store")
def the_run_is_saved(world: World) -> None:
    RunStore(world.root / ".495").save(world.the_run())


@when("the harness writes the retrospective")
@when("the harness writes the retrospective again")
def the_harness_writes_the_retrospective(world: World) -> None:
    world.retros.append(retrospect(world.the_run()))
    world.last = None


@when(parsers.parse('the requester runs "495 {arguments}"'))
def the_requester_runs(world: World, arguments: str, monkeypatch: pytest.MonkeyPatch) -> None:
    world.run_cli(*arguments.split(), monkeypatch=monkeypatch)
    assert world.exit_code == 0, world.output


@then(parsers.parse('the observation on "{role}" of "{technology}" names the tools "{tools}"'))
def the_observation_names_the_tools(world: World, role: str, technology: str, tools: str) -> None:
    observation = world.the_retro().observation(technology, CatalogueRole(role))
    assert observation is not None, world.the_retro().tool_observations
    world.last = observation
    assert observation.tools == [t.strip() for t in tools.split(",")]


@then(parsers.parse('that observation is "{verdict}"'))
def that_observation_is(world: World, verdict: str) -> None:
    assert world.the_observation().verdict.value == verdict, world.the_observation()


@then(
    parsers.re(
        r"that observation counts (?P<verdicts>\d+) verdicts?, (?P<contradictions>\d+) "
        r"contradictions? and (?P<faults>\d+) faults?"
    ),
    converters={"verdicts": int, "contradictions": int, "faults": int},
)
def that_observation_counts(world: World, verdicts: int, contradictions: int, faults: int) -> None:
    o = world.the_observation()
    assert (o.verdicts, o.contradictions, o.faults) == (verdicts, contradictions, faults), o


@then(parsers.parse('that observation reads "{line}"'))
def that_observation_reads(world: World, line: str) -> None:
    assert line in world.the_observation().detail, world.the_observation().detail


@then("that observation's row is a recommended entry citing the run")
def the_row_is_a_recommended_entry(world: World) -> None:
    o = world.the_observation()
    assert o.catalogue_row.startswith(f"| {o.role.value} | {', '.join(o.tools)} | recommended | ")
    assert world.the_retro().source in o.catalogue_row and RUN_ID in o.catalogue_row


@then("that observation's row is a rejected row citing the run")
def the_row_is_a_rejected_row(world: World) -> None:
    o = world.the_observation()
    assert o.catalogue_row.startswith(f"| Python | {o.role.value} | {', '.join(o.tools)} | ")
    assert o.catalogue_row.endswith(f"| {world.the_retro().source} |") and RUN_ID in o.catalogue_row


@then(parsers.parse('that observation\'s row says "{text}"'))
def the_row_says(world: World, text: str) -> None:
    assert text in world.the_observation().catalogue_row, world.the_observation().catalogue_row


@then("that observation brings no row")
def the_observation_brings_no_row(world: World) -> None:
    assert world.the_observation().catalogue_row == ""


@then("that observation is a further source for an entry the catalogue recommends")
def a_further_source(world: World) -> None:
    assert world.the_observation().in_catalogue


@then("that observation is an entry the catalogue does not have")
def an_entry_the_catalogue_does_not_have(world: World) -> None:
    assert not world.the_observation().in_catalogue


@then("the retrospective makes no observation")
def no_observation(world: World) -> None:
    assert world.the_retro().tool_observations == []


@then("both retrospectives make the same observations")
def both_make_the_same_observations(world: World) -> None:
    first, second = world.retros[-2], world.retros[-1]
    assert first.tool_observations == second.tool_observations
    assert first.source == second.source


@then("the retrospective of the run is saved under it")
def the_retrospective_is_saved(world: World) -> None:
    saved = RunStore(world.root / ".495").load_retrospective(RUN_ID)
    assert saved is not None and saved.run_id == RUN_ID


@then(parsers.parse('the output shows "{text}"'))
def the_output_shows(world: World, text: str) -> None:
    assert text in world.output, world.output


@then(
    parsers.parse(
        'the JSON output lists an observation on "{role}" of "{technology}" with the verdict "{verdict}"'
    )
)
def the_json_output_lists_an_observation(
    world: World, role: str, technology: str, verdict: str
) -> None:
    document = json.loads(world.output)
    matching = [
        o
        for o in document["tool_observations"]
        if o["technology"] == technology and o["role"] == role
    ]
    assert len(matching) == 1 and matching[0]["verdict"] == verdict, document
    assert matching[0]["catalogue_row"].startswith("| property | hypothesis | recommended |")
