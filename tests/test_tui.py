"""The run surface: every stop renders what the run actually holds, at any width."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
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
from harness495.interfaces.tui.driving import ReadOnly
from harness495.interfaces.tui.headlines import headline
from harness495.interfaces.tui.icons import ICON, ICON_SET, use_icons
from harness495.interfaces.tui.source import StaticSource
from harness495.interfaces.tui.stages import STAGES, STATE_GLYPH
from harness495.interfaces.tui.theme import THEME
from harness495.interfaces.tui.widgets import WorkingMark

VIEWS = [s.name for s in STAGES] + ["log", "runs"]


def render(shell: Shell, view: str, width: int = 150) -> str:
    shell.view = view
    out = io.StringIO()
    console = Console(theme=THEME, file=out, width=width, highlight=False, legacy_windows=False)
    console.print(shell.flow(width))
    return out.getvalue()


def surface(store: RunStore, width: int = 150) -> Shell:
    """A surface with the first run open, which is what a test about a stage needs."""
    console = Console(theme=THEME, file=io.StringIO(), width=width, highlight=False)
    runs = store.list_runs()
    return Shell(StoreSource(store), console, animated=False, selected=runs[0].id if runs else None)


@pytest.fixture
def delivered(sample_project: Path, config: Any, engine_factory: Any) -> RunStore:
    engine = engine_factory()
    run = engine.create_run("add subtract to calc", sample_project, config, RunMode.change)
    engine.run(run.id)
    return RunStore(sample_project / ".495")


# --------------------------------------------------------------------- the stage model


def _bare(status: RunStatus, rid: str = "run-0") -> Run:
    return Run(
        id=rid, harness_version="0", intent=Intent(text="x"), project_root="/", status=status
    )


# --------------------------------------------------------------------- the home page


class _Driving(ReadOnly):
    """A surface that may act. Nothing here is pressed; what is tested is what is offered."""

    def drives(self) -> bool:
        return True

    def creates(self) -> bool:
        return True


def _store_of(*runs: Run, driver: Any = None) -> Shell:
    """What ``495 watch`` builds when no run id was given: the home page, nothing open."""
    console = Console(theme=THEME, file=io.StringIO(), width=150, highlight=False)
    return Shell(StaticSource(runs, []), console, animated=False, driver=driver)


def _printed(shell: Shell, width: int = 150) -> list[str]:
    """What ``--print`` and an export write: the content, flowed."""
    out = io.StringIO()
    console = Console(theme=THEME, file=out, width=width, highlight=False, legacy_windows=False)
    console.print(shell.flow(width))
    return out.getvalue().splitlines()


def _drawn(shell: Shell, width: int = 150, height: int = 40) -> list[str]:
    """What the terminal draws: the same content in a ``Layout``."""
    out = io.StringIO()
    console = Console(
        theme=THEME, file=out, width=width, height=height, highlight=False, legacy_windows=False
    )
    console.print(shell.screen(width, height))
    return out.getvalue().splitlines()


#: Both ways the surface is rendered. A rule about what is on screen holds for both or it is
#: not a rule: one was once fixed while the other went on showing a run nobody had opened.
BOTH = pytest.mark.parametrize("draw", [_printed, _drawn], ids=["printed", "drawn"])

#: The header, the rule that closes it and the band: the rows that speak for whatever the
#: screen is about.
CHROME = 7


def _delivered(rid: str = "run-1") -> Run:
    """A run with something to act on: a branch to merge and a report to check a ref against."""
    run = _bare(RunStatus.delivered, rid)
    run.result.branch = f"495/{rid}"
    run.result.report_ref = "report.md"
    return run


# --------------------------------------------------------------------- the icons


def test_every_stop_is_named_by_an_emoji_of_its_own() -> None:
    """An emoji standing for two stops stands for neither; the width rule is enforced on import."""
    marks = [ICON[s.name] for s in STAGES]
    assert len(set(marks)) == len(STAGES)
    assert all(cell_len(m) == 2 for m in marks)


def test_a_terminal_without_emoji_gets_one_cell_marks_instead() -> None:
    try:
        use_icons("ascii")
        assert all(cell_len(ICON[name]) == 1 for name in ICON_SET)
    finally:
        use_icons()


# --------------------------------------------------------------------- the footer


@pytest.mark.parametrize("width", [80, 88, 104, 120, 150])
def test_no_key_is_offered_twice_on_the_row(delivered: RunStore, width: int) -> None:
    """Quit is put back after the trim, so a row that still held it printed it twice."""
    shell = surface(delivered, width)
    row = footer_bar(shell.footer_keys(), shell.run, shell.elapsed, True, width)
    console = Console(theme=THEME, file=io.StringIO(), width=width, highlight=False)
    with console.capture() as cap:
        console.print(row)
    assert cap.get().count(" quit ") == 1


# --------------------------------------------------------------------- the band


def _asking(kind: DecisionKind = DecisionKind.approve_spec) -> Run:
    run = _bare(RunStatus.awaiting_decision)
    run.pending_decision = PendingDecision(
        kind=kind, question="approve?", options=[DecisionOption(key="approve", label="approve")]
    )
    return run


def test_the_ledger_headline_never_denies_the_question_under_it() -> None:
    """A run can be stopped on a decision before one requirement has been weighed."""
    line = headline(_asking(DecisionKind.acceptance), "verdict").plain
    assert "waiting on your answer" in line and "nothing to decide" not in line.lower()
    # A question raised elsewhere is answered elsewhere: the panel is not under this sentence.
    assert "waiting on your answer" not in headline(_asking(), "verdict").plain


def test_every_state_of_the_band_takes_a_frame_the_rest_of_the_surface_draws() -> None:
    """Four tones, and each one is a border style panels already take — no hue of its own."""
    for status in RunStatus:
        state = attention(_bare(status), can_drive=True)
        assert state.tone in TONE_STYLE
        assert f"frame.{state.tone}" in THEME.styles


def test_a_frozen_display_never_hides_what_the_run_is_stopped_on() -> None:
    """Freezing is the surface stopping, not the run: it goes on the frame, not in its place."""
    shell = Shell.over([_asking()], [], Console(file=io.StringIO()), animated=False)
    shell.act("freeze")
    text = render(shell, "spec")
    assert "waiting on you" in text and "frozen" in text


def test_the_band_offers_no_key_the_surface_would_refuse() -> None:
    """A snapshot cannot answer a question, so it names the stage that holds it instead of d."""
    shell = Shell.over([_asking()], [], Console(file=io.StringIO()), animated=False)
    state = shell.attention()
    assert not shell.can("decide")
    assert state.key == STAGES[1].key and state.key != "d"


def test_a_run_nothing_holds_is_idle_on_a_surface_that_cannot_drive_it_either() -> None:
    """The claim and the running intervention are both in the store; idle is read, not assumed."""
    for can_drive in (True, False):
        state = attention(_bare(RunStatus.producing), can_drive=can_drive)
        assert not state.working
        assert state.headline == "idle"
    assert attention(_bare(RunStatus.created)).headline == "not started"


# --------------------------------------------------------------------- the strip


def _strip(run: Run, working: bool, width: int = 110) -> str:
    out = io.StringIO()
    console = Console(theme=THEME, file=out, width=width, highlight=False, legacy_windows=False)
    console.print(nav_bar(run, "change", width, working=working))
    return out.getvalue()


def test_the_stop_a_run_is_moving_through_turns() -> None:
    """A producer three minutes in and a run nobody started are both cyan at the same stop."""
    mark = WorkingMark()
    turning = _strip(_bare(RunStatus.producing), working=True)
    assert mark.glyph(at=0.0) in turning
    assert STATE_GLYPH["here"] not in turning
    assert STATE_GLYPH["todo"] in turning, "the stops ahead are untouched"


def test_a_still_strip_keeps_the_glyph_the_legend_names() -> None:
    """A --print and an export capture one frame; a spinner caught alone reads as a typo."""
    still = _strip(_bare(RunStatus.producing), working=False)
    assert STATE_GLYPH["here"] in still
    assert WorkingMark().glyph(at=0.0) not in still


def test_the_turning_mark_advances_with_the_clock_and_never_changes_width() -> None:
    mark = WorkingMark()
    frames = [mark.glyph(at=t * mark.spinner.interval / 1000) for t in range(8)]
    assert len(set(frames)) == 8, "eight redraws, eight different frames"
    assert all(len(f) == 1 for f in frames), "the tab was measured with one cell for the glyph"


# --------------------------------------------------------------------- the mark


def _lit_column(columns: tuple[Style | None, ...]) -> int | None:
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


def test_the_highlight_crosses_the_mark_once_per_cycle() -> None:
    """Left to right, then away: a highlight that walked back would read as a flicker."""
    assert logo.frame(0.0) is None, "the cycle opens at rest"
    assert logo.frame(logo.CYCLE - 0.01) is None, "and closes at rest"
    sweep = [
        logo.frame(logo.INITIAL_PAUSE + t / 100) for t in range(int(logo.SWEEP_DURATION * 100))
    ]
    assert all(columns is not None for columns in sweep), "it is one continuous pass"
    lit = [c for c in (_lit_column(f) for f in sweep if f is not None) if c is not None]
    assert lit == sorted(lit)
    assert lit[0] == 0 and lit[-1] == logo.WIDTH - 1


def test_the_mark_is_a_pure_function_of_the_clock() -> None:
    """Two surfaces refreshing at different rates must draw the same frame at the same instant."""
    assert logo.frame(2.5) == logo.frame(2.5 + logo.CYCLE)
    assert logo.frame(0.5) is logo.frame(0.5 + logo.CYCLE) is None


def test_the_highlight_paints_the_ink_and_leaves_everything_else_at_rest() -> None:
    """Painting the gaps would light three rectangles instead of 4 9 5."""
    console = Console(theme=THEME, file=io.StringIO())
    columns = logo.frame(logo.INITIAL_PAUSE + 0.9)
    assert columns is not None
    peak = _lit_column(columns)
    assert peak is not None
    lit = logo.render(logo.DIGITS, column_styles=columns)
    assert lit.plain == logo.still().plain, "no glyph is replaced; only the colour moves"
    resting = console.get_style("h.logo")
    assert lit.get_style_at_offset(console, peak) != resting, "the light is on the ink"
    assert lit.get_style_at_offset(console, lit.plain.index(" ")) == resting, "never in the holes"
    # An overlay is an explicit colour and the resting style is whatever the theme says, so a
    # column painted for nothing is a column that can disagree with the mark around it.
    assert columns[0] is None and lit.get_style_at_offset(console, 0) == resting


def test_a_still_capture_gets_the_whole_mark() -> None:
    assert logo.still().plain.splitlines() == ["█ █ █▀█ █▀▀", "▀▀█ ▀▀█ ▀▀█"]


# --------------------------------------------------------------------- evidence logs


# --------------------------------------------------------------------- a snapshot surface
