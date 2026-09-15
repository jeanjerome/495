"""Scenarios of ``tests/features/home.feature``: what ``interfaces/tui/`` draws and offers when
no run is open, and which row a control acts on.

The steps build a surface over a static list of bare runs — what the page says is a function of
the store, not of anything a run had to be walked to produce — render it both the way ``--print``
flows it and the way the terminal draws it, and read the lines, the cursor, the band and the
controls back. Nothing is asserted outside a ``Then``.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when
from rich.console import Console

from harness495.core.models import (
    DecisionKind,
    DecisionOption,
    Intent,
    PendingDecision,
    Run,
    RunStatus,
)
from harness495.interfaces.tui import Shell
from harness495.interfaces.tui.driving import ReadOnly
from harness495.interfaces.tui.source import StaticSource
from harness495.interfaces.tui.stages import stage_of
from harness495.interfaces.tui.theme import THEME

scenarios("features/home.feature")

CHROME = 7
"""The header, the rule that closes it and the band: the rows that speak for whatever the
screen is about."""


class Driving(ReadOnly):
    """A surface that may act. Nothing here is pressed; what is measured is what is offered."""

    def drives(self) -> bool:
        return True

    def creates(self) -> bool:
        return True


def bare(status: RunStatus, rid: str = "run-0") -> Run:
    return Run(
        id=rid, harness_version="0", intent=Intent(text="x"), project_root="/", status=status
    )


def asking(rid: str = "run-0") -> Run:
    run = bare(RunStatus.awaiting_decision, rid)
    run.pending_decision = PendingDecision(
        kind=DecisionKind.approve_spec,
        question="approve?",
        options=[DecisionOption(key="approve", label="approve")],
    )
    return run


def actionable(rid: str = "run-1") -> Run:
    """A run with something to act on: a branch to merge and a report to check a ref against."""
    run = bare(RunStatus.delivered, rid)
    run.result.branch = f"495/{rid}"
    run.result.report_ref = "report.md"
    return run


def printed(shell: Shell, width: int = 150, height: int = 40) -> list[str]:
    """What ``--print`` and an export write: the content, flowed."""
    out = io.StringIO()
    console = Console(theme=THEME, file=out, width=width, highlight=False, legacy_windows=False)
    console.print(shell.flow(width))
    return out.getvalue().splitlines()


def drawn(shell: Shell, width: int = 150, height: int = 40) -> list[str]:
    """What the terminal draws: the same content in a ``Layout``."""
    out = io.StringIO()
    console = Console(
        theme=THEME, file=out, width=width, height=height, highlight=False, legacy_windows=False
    )
    console.print(shell.screen(width, height))
    return out.getvalue().splitlines()


RENDERINGS: dict[str, Callable[..., list[str]]] = {"printed": printed, "drawn": drawn}
"""Both ways the surface is rendered. A rule about what is on screen holds of both or it is not
a rule: one was once fixed while the other went on showing a run nobody had opened."""


@dataclass
class Home:
    """A surface standing on the store, and the lines the last rendering produced."""

    shell: Shell
    lines: list[str] = field(default_factory=list)
    band: Any = None

    @property
    def chrome(self) -> str:
        return "\n".join(self.lines[:CHROME])

    @property
    def body(self) -> str:
        return "\n".join(self.lines[CHROME:])


def over(*runs: Run, driver: Any = None) -> Home:
    """What ``495 watch`` builds when no run id was given: the home page, nothing open."""
    console = Console(theme=THEME, file=io.StringIO(), width=150, highlight=False)
    return Home(Shell(StaticSource(runs, []), console, animated=False, driver=driver))


# ----------------------------------------------------------------- the store the page shows


@given("a store holding a run that asks and a delivered run", target_fixture="world")
def a_store_with_a_question_and_a_delivered_run() -> Home:
    return over(asking(), bare(RunStatus.delivered, "run-1"))


@given("a store holding a run that asks and a run with something to act on", target_fixture="world")
def a_store_with_a_question_and_something_to_act_on() -> Home:
    return over(asking(), actionable())


@given(
    "a store holding a run that asks and a run with something to act on, on a surface that may act",
    target_fixture="world",
)
def a_store_on_a_surface_that_may_act() -> Home:
    return over(asking(), actionable(), driver=Driving())


@given("a store holding a delivered run and a run that asks", target_fixture="world")
def a_store_with_a_delivered_run_and_a_question() -> Home:
    return over(bare(RunStatus.delivered, "run-1"), asking())


@given("a store holding a delivered run alone", target_fixture="world")
def a_store_with_a_delivered_run_alone() -> Home:
    return over(bare(RunStatus.delivered, "run-1"))


@given("a store holding a producing run alone", target_fixture="world")
def a_store_with_a_producing_run_alone() -> Home:
    return over(bare(RunStatus.producing, "run-2"))


@given("a store holding a failed run and a run that asks", target_fixture="world")
def a_store_with_a_failed_run_and_a_question() -> Home:
    return over(bare(RunStatus.failed, "run-3"), asking())


@given("an empty store, on a surface that may act", target_fixture="world")
def an_empty_store() -> Home:
    return over(driver=Driving())


@given("a store holding 30 runs", target_fixture="world")
def a_store_holding_thirty_runs() -> Home:
    return over(*(bare(RunStatus.created, f"run-{n:02d}") for n in range(30)))


@given(parsers.parse("the home page reached {arrival}"))
def the_home_page_reached(world: Home, arrival: str) -> None:
    if arrival == "after a run was opened":
        world.shell.select("run-1")
        world.shell.act("view:runs")


@given(parsers.parse("{subject} as the subject of the page"))
def the_subject_of_the_page(world: Home, subject: str) -> None:
    if subject == "a run":
        world.shell.select("run-1")


# ----------------------------------------------------------------- what is drawn, and pressed


@when(parsers.re(r"the page is (?P<how>printed|drawn)"))
def the_page_is_rendered(world: Home, how: str) -> None:
    world.lines = RENDERINGS[how](world.shell)


@when(parsers.re(r"the cursor moves down one, and the page is (?P<how>printed|drawn)"))
def the_cursor_moves_and_the_page_is_rendered(world: Home, how: str) -> None:
    world.shell.act("cursor:+1")
    world.lines = RENDERINGS[how](world.shell)


@when("the cursor moves down one")
def the_cursor_moves_down_one(world: Home) -> None:
    world.shell.act("cursor:+1")


@when(parsers.parse("the cursor moves down {rows:d} rows"))
def the_cursor_moves_down_rows(world: Home, rows: int) -> None:
    for _ in range(rows):
        world.shell.act("cursor:+1")


@when(parsers.parse("the page is drawn {height:d} rows high"))
def the_page_is_drawn_rows_high(world: Home, height: int) -> None:
    world.lines = drawn(world.shell, height=height)


@when("the row under the cursor is opened")
def the_row_under_the_cursor_is_opened(world: Home) -> None:
    world.shell.act("open")


@when("the listing is opened again")
def the_listing_is_opened_again(world: Home) -> None:
    world.shell.act("view:runs")


@when("the run that asks is opened, and the listing is opened again")
def the_run_that_asks_is_opened(world: Home) -> None:
    world.shell.select("run-0")
    world.shell.act("view:runs")


@when("what the page offers is read")
def what_the_page_offers_is_read(world: Home) -> None:
    world.lines = printed(world.shell)


@when(parsers.parse('the stop "{name}" is asked for'))
def the_stop_is_asked_for(world: Home, name: str) -> None:
    world.shell.act(f"stage:{name}")


@when("the next stop, the previous stop and the filter are asked for in turn")
def the_relative_moves_are_asked_for(world: Home) -> None:
    for action in ("stage:+1", "stage:-1", "filter"):
        world.shell.act(action)


@when("opening, answering, starting, catching up and going to a stop are all asked for")
def every_action_is_asked_for(world: Home) -> None:
    for action in ("open", "decide", "control:start", "catchup", "stage:spec"):
        world.shell.act(action)


@when("the band of the store is read")
def the_band_of_the_store_is_read(world: Home) -> None:
    world.band = world.shell.store_state()


@when("the catch-up key is pressed")
def the_catchup_key_is_pressed(world: Home) -> None:
    world.shell.act("catchup")


# ----------------------------------------------------------------- what the page says


@then("the page stands at home, showing the listing")
def the_page_stands_at_home(world: Home) -> None:
    assert world.shell.at_home and world.shell.view == "runs"


@then(parsers.parse('the chrome says "{text}"'))
def the_chrome_says(world: Home, text: str) -> None:
    assert text in world.chrome


@then(parsers.parse('the chrome counts "{text}"'))
def the_chrome_counts(world: Home, text: str) -> None:
    assert text in world.chrome, "the identity and the band count the store"


@then("the chrome names no run of the store, and no stop of one")
def the_chrome_names_no_run(world: Home) -> None:
    assert "run-1" not in world.chrome and "delivered" not in world.chrome
    assert "profile" not in world.chrome, "eight stops are eight stops of a run"


@then("nothing on the page puts the question to the requester")
def nothing_puts_the_question(world: Home) -> None:
    assert not any("what this rests on" in line for line in world.lines)


@then(parsers.re(r'the body names "(?P<rid>[^"]+)"'))
def the_body_names(world: Home, rid: str) -> None:
    assert rid in world.body


@then(parsers.parse('the body names "{rid}", and says "{text}"'))
def the_body_names_and_says(world: Home, rid: str, text: str) -> None:
    assert rid in world.body and text in world.body


@then(parsers.parse('the body says "{text}"'))
def the_body_says(world: Home, text: str) -> None:
    assert text in world.body


@then(parsers.parse('the body names "{present}", and not "{absent}"'))
def the_body_names_and_not(world: Home, present: str, absent: str) -> None:
    assert present in world.body and absent not in world.body


@then("nothing was opened")
def nothing_was_opened(world: Home) -> None:
    assert not world.shell.opened, "the cursor moved; nothing was opened"


@then(parsers.parse('the run "{rid}" is open, at the stop it stands at'))
def the_run_is_open_at_its_stop(world: Home, rid: str) -> None:
    assert world.shell.opened and world.shell.run.id == rid
    assert world.shell.view == stage_of(world.shell.run)


@then(parsers.parse('the run "{rid}" is open, at the stop "{view}"'))
def the_run_is_open_at_the_stop(world: Home, rid: str, view: str) -> None:
    assert world.shell.opened and world.shell.run.id == rid and world.shell.view == view


@then(parsers.parse('the header names "{rid}", and the band under it says "{text}"'))
def the_header_names_the_run(world: Home, rid: str, text: str) -> None:
    assert rid in world.lines[0]
    assert text in world.lines[CHROME - 3]


@then("the cursor is still on the row that is open")
def the_cursor_is_still_on_the_open_row(world: Home) -> None:
    assert world.shell.cursor == 1


@then("the third line is a rule the full width of the screen")
def the_third_line_is_a_rule(world: Home) -> None:
    assert world.lines[2].rstrip() == "─" * 150


@then("the fourth line is air")
def the_fourth_line_is_air(world: Home) -> None:
    assert not world.lines[3].strip()


@then("the surface can answer, the cursor being on the run that asked")
def the_surface_can_answer(world: Home) -> None:
    assert world.shell.can("decide")


@then("the surface cannot answer")
def the_surface_cannot_answer(world: Home) -> None:
    assert not world.shell.can("decide"), "it answered a question three rows above the cursor"


@then(
    parsers.parse(
        'the cursor is on "{focused}", and the run open behind the page is still "{open_}"'
    )
)
def the_cursor_is_on(world: Home, focused: str, open_: str) -> None:
    assert world.shell.focus is not None and world.shell.focus.id == focused
    assert world.shell.run.id == open_


@then(parsers.parse('the footer offers "{first}" and "{second}", and not "{absent}"'))
def the_footer_offers(world: Home, first: str, second: str, absent: str) -> None:
    offered = [key for key, _, _ in world.shell.footer_keys()]
    assert first in offered and second in offered and absent not in offered


@then(parsers.parse("the footer offers only: {keys}"))
def the_footer_offers_only(world: Home, keys: str) -> None:
    assert [key for key, _, _ in world.shell.footer_keys()] == [k.strip() for k in keys.split(",")]


@then(parsers.parse("the controls offered are: {controls}"))
def the_controls_offered_are(world: Home, controls: str) -> None:
    assert world.shell.controls() == _controls(controls)


@then(parsers.parse("the only control offered is: {controls}"))
def the_only_control_offered_is(world: Home, controls: str) -> None:
    assert world.shell.controls() == _controls(controls), (
        "nothing acts on a run; one thing makes one"
    )


def _controls(text: str) -> list[tuple[str, str]]:
    """ "m merge the branch, i check a ref" -> [("m", "merge the branch"), ("i", "check a ref")]."""
    pairs = [item.strip().split(" ", 1) for item in text.split(",")]
    return [(key, label) for key, label in pairs]


@then("the surface offers no control")
def the_surface_offers_no_control(world: Home) -> None:
    assert world.shell.controls() == []


@then("the page stayed at home, with nothing opened")
def the_page_stayed_at_home(world: Home) -> None:
    assert world.shell.at_home and not world.shell.opened


@then(parsers.parse('it is toned "{tone}", saying "{text}"'))
def the_band_is_toned_saying(world: Home, tone: str, text: str) -> None:
    assert world.band.tone == tone and text in world.band.headline


@then(parsers.parse('it is toned "{tone}", offering no key'))
def the_band_is_toned_offering_nothing(world: Home, tone: str) -> None:
    assert world.band.tone == tone and world.band.key is None


@then(parsers.parse('it offers "{key}", and counts "{text}"'))
def the_band_offers_and_counts(world: Home, key: str, text: str) -> None:
    assert world.band.key == key and text in world.band.about


@then(parsers.parse('it says "{text}"'))
def the_band_says(world: Home, text: str) -> None:
    assert text in world.band.headline, "a question outranks a run that already ended"


@then("the cursor stands on a run that is asking something")
def the_cursor_stands_on_a_run_that_asks(world: Home) -> None:
    assert world.shell.focus is not None and world.shell.focus.pending_decision is not None


@then("nothing is in focus")
def nothing_is_in_focus(world: Home) -> None:
    assert world.shell.focus is None


@then(parsers.parse('the page says "{first}" and "{second}"'))
def the_page_says(world: Home, first: str, second: str) -> None:
    text = "\n".join(world.lines)
    assert first in text and second in text
