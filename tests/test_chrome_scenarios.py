"""Scenarios of ``tests/features/chrome.feature``: what ``interfaces/tui/chrome/``,
``icons.py``, ``headlines.py``, ``attention.py`` and ``widgets.py`` paint around whatever a stop
is showing.

The steps call each of those directly — the icon table, the footer row, the headline of a stop,
the band of a run, the strip, the turning mark and the sweep over the logo — render what comes
back into a console writing in memory, and read the text and the styles back. Nothing is
asserted outside a ``Then``.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from rich.cells import cell_len
from rich.console import Console
from rich.style import Style

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
from harness495.interfaces.tui.attention import attention
from harness495.interfaces.tui.chrome import footer_bar, logo, nav_bar
from harness495.interfaces.tui.chrome.band import TONE_STYLE
from harness495.interfaces.tui.headlines import headline
from harness495.interfaces.tui.icons import ICON, ICON_SET, use_icons
from harness495.interfaces.tui.stages import STAGES, STATE_GLYPH
from harness495.interfaces.tui.theme import THEME
from harness495.interfaces.tui.widgets import WorkingMark

scenarios("features/chrome.feature")


def bare(status: RunStatus, rid: str = "run-0") -> Run:
    return Run(
        id=rid, harness_version="0", intent=Intent(text="x"), project_root="/", status=status
    )


def asking(kind: DecisionKind) -> Run:
    run = bare(RunStatus.awaiting_decision)
    run.pending_decision = PendingDecision(
        kind=kind, question="approve?", options=[DecisionOption(key="approve", label="approve")]
    )
    return run


def lit_column(columns: tuple[Style | None, ...]) -> int | None:
    """Which column the highlight is brightest on, or ``None`` where nothing is painted.

    A column the light has not reached carries no overlay at all: it keeps whatever style the
    theme gave the mark, which is the only way the unlit part of a sweep cannot differ from
    the mark at rest.
    """
    light = {
        index: sum(c.color.get_truecolor())
        for index, c in enumerate(columns)
        if c is not None and c.color is not None
    }
    return max(light, key=lambda index: light[index]) if light else None


@dataclass
class Chrome:
    """What the last call painted, and what was read out of it."""

    run: Run | None = None
    shell: Shell | None = None
    text: str = ""
    marks: list[str] = field(default_factory=list)
    bands: list[Any] = field(default_factory=list)
    sweep: list[Any] = field(default_factory=list)
    frames: list[Any] = field(default_factory=list)
    columns: tuple[Style | None, ...] | None = None
    rendered: Any = None

    @property
    def open_run(self) -> Run:
        assert self.shell is not None
        return self.shell.run


@pytest.fixture
def world() -> Chrome:
    return Chrome()


def draw(renderable: Any, width: int = 110) -> str:
    out = io.StringIO()
    console = Console(theme=THEME, file=out, width=width, highlight=False, legacy_windows=False)
    console.print(renderable)
    return out.getvalue()


# ----------------------------------------------------------------- the icons


@when("the emoji of the eight stops are read")
def the_emoji_of_the_stops(world: Chrome) -> None:
    world.marks = [ICON[stage.name] for stage in STAGES]


@when("the icon set is switched to ascii")
def the_icon_set_is_switched(world: Chrome) -> None:
    use_icons("ascii")
    world.marks = [ICON[name] for name in ICON_SET]
    use_icons()


@then("no two stops share one")
def no_two_stops_share_one(world: Chrome) -> None:
    assert len(set(world.marks)) == len(STAGES)


@then("each of them is two cells wide")
def each_mark_is_two_cells(world: Chrome) -> None:
    assert all(cell_len(mark) == 2 for mark in world.marks)


@then("every mark is one cell wide")
def every_mark_is_one_cell(world: Chrome) -> None:
    assert all(cell_len(mark) == 1 for mark in world.marks)


# ----------------------------------------------------------------- the footer


@pytest.fixture
def delivered(sample_project: Path, config: Any, engine_factory: Callable[..., Any]) -> RunStore:
    engine = engine_factory()
    run = engine.create_run("add subtract to calc", sample_project, config, RunMode.change)
    engine.run(run.id)
    return RunStore(sample_project / ".495")


@given("a run carried to delivery, open on the surface")
def a_run_open_on_the_surface(world: Chrome, delivered: RunStore) -> None:
    console = Console(theme=THEME, file=io.StringIO(), width=150, highlight=False)
    runs = delivered.list_runs()
    world.shell = Shell(StoreSource(delivered), console, animated=False, selected=runs[0].id)


@when(parsers.parse("the footer row is drawn at {width:d} columns"))
def the_footer_row_is_drawn(world: Chrome, width: int) -> None:
    shell = world.shell
    assert shell is not None
    row = footer_bar(shell.footer_keys(), shell.run, shell.elapsed, True, width)
    world.text = draw(row, width)


@then(parsers.parse('"{text}" is on the row once'))
def the_text_is_on_the_row_once(world: Chrome, text: str) -> None:
    assert world.text.count(f" {text} ") == 1


# ----------------------------------------------------------------- the band


@given(parsers.parse('a run stopped on an "{kind}" question'))
def a_run_stopped_on_a_question(world: Chrome, kind: str) -> None:
    world.run = asking(DecisionKind(kind))


@given(parsers.parse('a snapshot surface over a run stopped on an "{kind}" question'))
def a_snapshot_surface_over_a_run_that_asks(world: Chrome, kind: str) -> None:
    world.shell = Shell.over(
        [asking(DecisionKind(kind))], [], Console(file=io.StringIO()), animated=False
    )


@when(parsers.parse('the headline of the "{view}" stop is read'))
def the_headline_of_the_stop(world: Chrome, view: str) -> None:
    assert world.run is not None
    world.text = headline(world.run, view).plain


@when("the band is read for every status a run can be in")
def the_band_for_every_status(world: Chrome) -> None:
    world.bands = [attention(bare(status), can_drive=True) for status in RunStatus]


@when(parsers.parse('the display is frozen, and the "{view}" stop is rendered'))
def the_display_is_frozen(world: Chrome, view: str) -> None:
    shell = world.shell
    assert shell is not None
    shell.act("freeze")
    shell.view = view
    world.text = draw(shell.flow(150), 150)


@when("the band of the open run is read")
def the_band_of_the_open_run(world: Chrome) -> None:
    assert world.shell is not None
    world.bands = [world.shell.attention()]


@when("the band of a producing run is read, on a surface that may drive and on one that may not")
def the_band_of_a_producing_run(world: Chrome) -> None:
    world.bands = [
        attention(bare(RunStatus.producing), can_drive=can_drive) for can_drive in (True, False)
    ]


@then(parsers.parse('it says "{text}"'))
def the_headline_says(world: Chrome, text: str) -> None:
    assert text in world.text


@then(parsers.parse('it does not say "{text}"'))
def the_headline_does_not_say(world: Chrome, text: str) -> None:
    assert text.lower() not in world.text.lower()


@then("each tone is one the panels take, and the theme has a frame for it")
def each_tone_takes_a_frame(world: Chrome) -> None:
    for state in world.bands:
        assert state.tone in TONE_STYLE
        assert f"frame.{state.tone}" in THEME.styles


@then(parsers.parse('the stop says "{text}"'))
def the_stop_says(world: Chrome, text: str) -> None:
    assert text in world.text


@then("the surface cannot answer")
def the_surface_cannot_answer(world: Chrome) -> None:
    assert world.shell is not None and not world.shell.can("decide")


@then("the band names the stop that holds the question, rather than the key that answers it")
def the_band_names_the_stop(world: Chrome) -> None:
    key = world.bands[0].key
    assert key == STAGES[1].key and key != "d"


@then('neither says anything is working, and both say "idle"')
def neither_says_working(world: Chrome) -> None:
    assert all(not state.working and state.headline == "idle" for state in world.bands)


@then(parsers.parse('the band of a run nobody started says "{text}"'))
def the_band_of_an_unstarted_run(world: Chrome, text: str) -> None:
    assert attention(bare(RunStatus.created)).headline == text


# ----------------------------------------------------------------- the strip


@when("the strip of a producing run is drawn with something working")
def the_strip_with_something_working(world: Chrome) -> None:
    world.text = draw(nav_bar(bare(RunStatus.producing), "change", 110, working=True))


@when("the strip of a producing run is drawn with nothing working")
def the_strip_with_nothing_working(world: Chrome) -> None:
    world.text = draw(nav_bar(bare(RunStatus.producing), "change", 110, working=False))


@when("eight frames of the turning mark are read, one per redraw")
def eight_frames_of_the_turning_mark(world: Chrome) -> None:
    mark = WorkingMark()
    world.marks = [mark.glyph(at=n * mark.spinner.interval / 1000) for n in range(8)]


@then("the turning mark is on it")
def the_turning_mark_is_on_it(world: Chrome) -> None:
    assert WorkingMark().glyph(at=0.0) in world.text


@then("the turning mark is not")
def the_turning_mark_is_not(world: Chrome) -> None:
    assert WorkingMark().glyph(at=0.0) not in world.text


@then("the still glyph for the stop being walked is not")
def the_still_glyph_is_not(world: Chrome) -> None:
    assert STATE_GLYPH["here"] not in world.text


@then("the still glyph for the stop being walked is on it")
def the_still_glyph_is_on_it(world: Chrome) -> None:
    assert STATE_GLYPH["here"] in world.text


@then("the stops ahead are untouched")
def the_stops_ahead_are_untouched(world: Chrome) -> None:
    assert STATE_GLYPH["todo"] in world.text


@then("they are eight different frames")
def eight_different_frames(world: Chrome) -> None:
    assert len(set(world.marks)) == 8, "eight redraws, eight different frames"


@then("each of them is one cell wide")
def each_frame_is_one_cell(world: Chrome) -> None:
    assert all(len(frame) == 1 for frame in world.marks), (
        "the tab was measured with one cell for the glyph"
    )


# ----------------------------------------------------------------- the mark


@when("the sweep of one cycle is read")
def the_sweep_of_one_cycle(world: Chrome) -> None:
    world.sweep = [
        logo.frame(logo.INITIAL_PAUSE + n / 100) for n in range(int(logo.SWEEP_DURATION * 100))
    ]


@when("a moment of the sweep and a moment at rest are each compared with a cycle later")
def a_moment_of_the_sweep_and_one_at_rest(world: Chrome) -> None:
    world.frames = [
        (logo.frame(2.5), logo.frame(2.5 + logo.CYCLE)),
        (logo.frame(0.5), logo.frame(0.5 + logo.CYCLE)),
    ]


@when("the mark is rendered at a moment of the sweep")
def the_mark_is_rendered_at_a_moment(world: Chrome) -> None:
    world.columns = logo.frame(logo.INITIAL_PAUSE + 0.9)
    assert world.columns is not None
    world.rendered = logo.render(logo.DIGITS, column_styles=world.columns)


@when("the mark is captured still")
def the_mark_is_captured_still(world: Chrome) -> None:
    world.text = logo.still().plain


@then("the cycle opens at rest, and closes at rest")
def the_cycle_opens_and_closes_at_rest(world: Chrome) -> None:
    assert logo.frame(0.0) is None and logo.frame(logo.CYCLE - 0.01) is None


@then("the sweep is one continuous pass")
def the_sweep_is_continuous(world: Chrome) -> None:
    assert all(columns is not None for columns in world.sweep)


@then("the lit column only ever moves to the right")
def the_lit_column_moves_right(world: Chrome) -> None:
    assert _lit(world) == sorted(_lit(world))


@then("it starts at the first column and ends at the last")
def the_sweep_spans_the_mark(world: Chrome) -> None:
    lit = _lit(world)
    assert lit[0] == 0 and lit[-1] == logo.WIDTH - 1


def _lit(world: Chrome) -> list[int]:
    return [c for c in (lit_column(f) for f in world.sweep if f is not None) if c is not None]


@then("the moment of the sweep draws the same frame")
def the_moment_draws_the_same_frame(world: Chrome) -> None:
    now, later = world.frames[0]
    assert now == later


@then("the moment at rest is at rest there too")
def the_moment_at_rest_is_at_rest(world: Chrome) -> None:
    now, later = world.frames[1]
    assert now is later is None


@then("no glyph is replaced; only the colour moves")
def no_glyph_is_replaced(world: Chrome) -> None:
    assert world.rendered.plain == logo.still().plain


@then("the brightest column differs from the resting style")
def the_brightest_column_differs(world: Chrome) -> None:
    console = Console(theme=THEME, file=io.StringIO())
    assert world.columns is not None
    peak = lit_column(world.columns)
    assert peak is not None
    resting = console.get_style("h.logo")
    assert world.rendered.get_style_at_offset(console, peak) != resting, "the light is on the ink"


@then("a hole between the glyphs keeps the resting style")
def a_hole_keeps_the_resting_style(world: Chrome) -> None:
    console = Console(theme=THEME, file=io.StringIO())
    resting = console.get_style("h.logo")
    hole = world.rendered.plain.index(" ")
    assert world.rendered.get_style_at_offset(console, hole) == resting


@then("a column the light has not reached carries no overlay at all")
def an_unlit_column_carries_no_overlay(world: Chrome) -> None:
    console = Console(theme=THEME, file=io.StringIO())
    assert world.columns is not None and world.columns[0] is None
    resting = console.get_style("h.logo")
    assert world.rendered.get_style_at_offset(console, 0) == resting


@then(parsers.parse('it reads "{first}" over "{second}"'))
def the_still_capture_reads(world: Chrome, first: str, second: str) -> None:
    assert world.text.splitlines() == [first, second]
