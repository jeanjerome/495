"""Scenarios of ``tests/features/surface.feature`` and ``tests/features/stages.feature``: what
``interfaces/tui/`` draws of a run, and which of the eight stops that run stands at.

The steps carry one run to delivery over the sample project with the fake agents behind it,
open the surface over the store it left, flow each stop into a console writing in memory, and
read the text, the cursor and the run document back. The stage model is read on bare runs, since
what it answers is a function of the status and the question alone. Nothing is asserted outside
a ``Then``.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from rich.console import Console

from harness495.core.models import (
    DecisionKind,
    DecisionOption,
    Intent,
    PendingDecision,
    Run,
    RunMode,
    RunStatus,
)
from harness495.core.store import RunStore
from harness495.interfaces.tui import Shell, StoreSource
from harness495.interfaces.tui.logs import StoredLogs
from harness495.interfaces.tui.stages import STAGES, stage_of, stage_state
from harness495.interfaces.tui.theme import THEME

scenarios("features/surface.feature", "features/stages.feature")

VIEWS = [s.name for s in STAGES] + ["log", "runs"]
"""Every stop of a run, and the two pages that are not stops of one."""


def flow(shell: Shell, view: str, width: int = 150) -> str:
    shell.view = view
    out = io.StringIO()
    console = Console(theme=THEME, file=out, width=width, highlight=False, legacy_windows=False)
    console.print(shell.flow(width))
    return out.getvalue()


@dataclass
class Surface:
    """A surface over a store, and what the last rendering drew."""

    shell: Shell
    store: RunStore | None = None
    drawn: dict[str, str] = field(default_factory=dict)
    last: str = ""
    before: str = ""
    read_back: str | None = None
    refused: Exception | None = None

    @property
    def run(self) -> Run:
        return self.shell.run

    def render(self, view: str, width: int = 150) -> str:
        self.last = flow(self.shell, view, width)
        self.drawn[view] = self.last
        return self.last


@dataclass
class Standing:
    """A bare run, and the stop the stage model puts it at."""

    run: Run
    stop: str = ""


def bare(status: RunStatus, rid: str = "run-0") -> Run:
    return Run(
        id=rid, harness_version="0", intent=Intent(text="x"), project_root="/", status=status
    )


# ----------------------------------------------------------------- the surface over a store


@pytest.fixture
def delivered(sample_project: Path, config: Any, engine_factory: Callable[..., Any]) -> RunStore:
    engine = engine_factory()
    run = engine.create_run("add subtract to calc", sample_project, config, RunMode.change)
    engine.run(run.id)
    return RunStore(sample_project / ".495")


@given("a run carried to delivery, open on the surface", target_fixture="world")
def a_run_open_on_the_surface(delivered: RunStore) -> Surface:
    console = Console(theme=THEME, file=io.StringIO(), width=150, highlight=False)
    runs = delivered.list_runs()
    shell = Shell(StoreSource(delivered), console, animated=False, selected=runs[0].id)
    return Surface(shell, delivered, before=delivered.load(runs[0].id).model_dump_json())


@given("a surface over a snapshot of one run", target_fixture="world")
def a_surface_over_a_snapshot() -> Surface:
    shell = Shell.over([bare(RunStatus.created)], [], Console(file=io.StringIO()), animated=False)
    return Surface(shell)


@when("every stop is rendered")
def every_stop_is_rendered(world: Surface) -> None:
    for view in VIEWS:
        world.render(view)


@when(parsers.parse("every stop is rendered at {width:d} columns"))
def every_stop_is_rendered_at(world: Surface, width: int) -> None:
    for view in VIEWS:
        world.render(view, width)


@when(parsers.parse('the "{view}" stop is rendered'))
def the_stop_is_rendered(world: Surface, view: str) -> None:
    world.before = world.render(view)


@when("the cursor moves down one")
def the_cursor_moves_down_one(world: Surface) -> None:
    world.shell.act("cursor:+1")


@when("the output of the first command that recorded one is asked for")
def the_output_of_the_first_command(world: Surface) -> None:
    assert world.store is not None
    run = world.store.list_runs()[0]
    recorded = [e for e in run.evidence if e.output_ref]
    assert recorded, "the run recorded no command output"
    world.read_back = StoredLogs(world.store, run.id).get(recorded[0])


@when("the output of an evidence pointing at a file that is gone is asked for")
def the_output_of_a_missing_file(world: Surface) -> None:
    assert world.store is not None
    run = world.store.list_runs()[0]
    gone = run.evidence[0].model_copy(update={"output_ref": "evidence/gone.log"})
    world.read_back = StoredLogs(world.store, run.id).get(gone)


@then("every one of them names the run")
def every_stop_names_the_run(world: Surface) -> None:
    assert all(world.run.id in text for text in world.drawn.values())


@then("every stop of a run carries the pipeline strip, the home page excepted")
def every_stop_carries_the_strip(world: Surface) -> None:
    for view, text in world.drawn.items():
        if view == "runs":
            continue
        assert "profile" in text and "deliver" in text, view


@then(parsers.parse('it says "{text}"'))
def it_says(world: Surface, text: str) -> None:
    assert text in world.last


@then("it names the branch the change is on")
def it_names_the_branch(world: Surface) -> None:
    branch = world.run.result.branch
    assert branch is not None and branch in world.last


@then("it names the command that prints the report")
def it_names_the_report_command(world: Surface) -> None:
    assert f"495 report {world.run.id}" in world.last


@then("every verification of the specification is named")
def every_verification_is_named(world: Surface) -> None:
    assert all(v.id in world.last for v in world.run.spec.verifications)


@then("every requirement is named, with the status it stands at")
def every_requirement_is_named(world: Surface) -> None:
    for requirement in world.run.spec.requirements:
        assert requirement.id in world.last
        assert requirement.status.value in world.last


@then("the cursor stands on the second row")
def the_cursor_stands_on_the_second_row(world: Surface) -> None:
    assert world.shell.cursor == 1


@then("the stop renders differently from before")
def the_stop_renders_differently(world: Surface) -> None:
    assert flow(world.shell, world.shell.view) != world.before


@then(parsers.parse("no line is wider than {width:d} columns"))
def no_line_is_wider_than(world: Surface, width: int) -> None:
    for view, text in world.drawn.items():
        for line in text.splitlines():
            assert len(line.rstrip()) <= width, (view, line)


@then("the run document is what it was before")
def the_run_document_is_unchanged(world: Surface) -> None:
    assert world.store is not None
    assert world.store.load(world.run.id).model_dump_json() == world.before


@then("it comes back")
def it_comes_back(world: Surface) -> None:
    assert world.read_back


@then("nothing comes back")
def nothing_comes_back(world: Surface) -> None:
    assert world.read_back is None


@then("something was drawn")
def something_was_drawn(world: Surface) -> None:
    assert world.last


@then("the surface offers no control, and nothing to start")
def the_surface_offers_nothing(world: Surface) -> None:
    assert world.shell.controls() == [] and world.shell.startable() is None


@then("asking it to start a run is refused")
def asking_it_to_start_is_refused(world: Surface) -> None:
    with pytest.raises(RuntimeError):
        world.shell.driver.start("run-0")


# ----------------------------------------------------------------- where a run stands


@given(parsers.parse('a run whose status is "{status}"'), target_fixture="standing")
def a_run_whose_status_is(status: str) -> Standing:
    return Standing(bare(RunStatus(status)))


@given(parsers.parse('a run stopped on an "{kind}" question'), target_fixture="standing")
def a_run_stopped_on_a_question(kind: str) -> Standing:
    run = bare(RunStatus.awaiting_decision)
    run.pending_decision = PendingDecision(
        kind=DecisionKind(kind),
        question="approve?",
        options=[DecisionOption(key="approve", label="approve")],
    )
    return Standing(run)


@when("the stop it stands at is read")
def the_stop_it_stands_at(standing: Standing) -> None:
    standing.stop = stage_of(standing.run)


@then(parsers.parse('it is "{stop}"'))
def it_is_the_stop(standing: Standing, stop: str) -> None:
    assert standing.stop == stop


@then(parsers.parse('the stop "{name}" is blocked'))
def the_stop_is_blocked(standing: Standing, name: str) -> None:
    assert stage_state(standing.run, name) == "blocked"


@then(parsers.parse('the stop "{name}" is still to walk'))
def the_stop_is_still_to_walk(standing: Standing, name: str) -> None:
    assert stage_state(standing.run, name) == "todo"


@then(parsers.parse('the stop "{name}" is done'))
def the_stop_is_done(standing: Standing, name: str) -> None:
    assert stage_state(standing.run, name) == "done"


@then("every stop before the integration is done")
def every_stop_before_the_integration_is_done(standing: Standing) -> None:
    walked = [s.name for s in STAGES if s.name != "integration"]
    assert all(stage_state(standing.run, name) == "done" for name in walked)


@then(parsers.parse('the stop "{name}" is blocked, waiting on a merge rather than working'))
def the_stop_is_blocked_on_a_merge(standing: Standing, name: str) -> None:
    assert stage_state(standing.run, name) == "blocked"
