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
from harness495.interfaces.tui.logs import StoredLogs
from harness495.interfaces.tui.source import StaticSource
from harness495.interfaces.tui.stages import STAGES, STATE_GLYPH, stage_of, stage_state
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


def test_every_stage_renders_a_delivered_run(delivered: RunStore) -> None:
    shell = surface(delivered)
    for view in VIEWS:
        text = render(shell, view)
        assert shell.run.id in text
        if view != "runs":
            # The pipeline strip is on every view of a run, whichever one is open. The home
            # page is the exception, and it is the point of it: a strip is eight stops *of a
            # run*, and that page is about the store.
            assert "profile" in text and "deliver" in text


def test_the_delivered_stage_names_the_artefacts_and_what_to_do(delivered: RunStore) -> None:
    shell = surface(delivered)
    run = shell.run
    assert run.status is RunStatus.delivered
    text = render(shell, "deliver")
    assert "nothing has been merged" in text
    assert run.result.branch is not None and run.result.branch in text
    assert f"495 report {run.id}" in text


def test_the_checks_stage_shows_what_each_command_observed(delivered: RunStore) -> None:
    shell = surface(delivered)
    text = render(shell, "checks")
    for v in shell.run.spec.verifications:
        assert v.id in text


def test_the_ledger_carries_every_requirement_and_its_reason(delivered: RunStore) -> None:
    shell = surface(delivered)
    text = render(shell, "verdict")
    for r in shell.run.spec.requirements:
        assert r.id in text
        assert r.status.value in text


def test_the_cursor_moves_the_detail_beside_the_list(delivered: RunStore) -> None:
    shell = surface(delivered)
    shell.view = "spec"
    first = render(shell, "spec")
    shell.act("cursor:+1")
    assert shell.cursor == 1
    assert render(shell, "spec") != first


def test_a_narrow_terminal_never_scrolls_sideways(delivered: RunStore) -> None:
    """Below 136 the detail goes under the list; below 92 the mark goes. Nothing overflows."""
    shell = surface(delivered, width=80)
    for view in VIEWS:
        for line in render(shell, view, width=80).splitlines():
            assert len(line.rstrip()) <= 80, (view, line)


def test_the_surface_never_advances_the_run(delivered: RunStore) -> None:
    before = delivered.load(delivered.list_runs()[0].id).model_dump_json()
    shell = surface(delivered)
    for view in VIEWS:
        render(shell, view)
    assert delivered.load(shell.run.id).model_dump_json() == before


# --------------------------------------------------------------------- the stage model


def _bare(status: RunStatus, rid: str = "run-0") -> Run:
    return Run(
        id=rid, harness_version="0", intent=Intent(text="x"), project_root="/", status=status
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (RunStatus.created, "profile"),
        (RunStatus.specified, "spec"),
        (RunStatus.producing, "change"),
        (RunStatus.verifying, "checks"),
        (RunStatus.reviewing, "review"),
        (RunStatus.reviewed, "verdict"),
        (RunStatus.accepted, "deliver"),
        (RunStatus.delivered, "integration"),
    ],
)
def test_a_status_maps_to_one_stop(status: RunStatus, expected: str) -> None:
    assert stage_of(_bare(status)) == expected


def test_a_question_is_shown_at_the_stage_that_raised_it() -> None:
    """``awaiting_decision`` says the run stopped, not where; the question says where."""
    run = _bare(RunStatus.awaiting_decision)
    run.pending_decision = PendingDecision(
        kind=DecisionKind.approve_spec,
        question="approve?",
        options=[DecisionOption(key="approve", label="approve")],
    )
    assert stage_of(run) == "spec"
    assert stage_state(run, "spec") == "blocked"
    assert stage_state(run, "checks") == "todo"
    assert stage_state(run, "profile") == "done"


def test_a_delivered_run_leaves_every_stop_walked_and_stands_at_the_integration() -> None:
    """Delivery ends what the harness can do alone: the merge, and its check, are yours."""
    run = _bare(RunStatus.delivered)
    walked = [s.name for s in STAGES if s.name != "integration"]
    assert all(stage_state(run, name) == "done" for name in walked)
    assert stage_of(run) == "integration"
    assert stage_state(run, "integration") == "blocked", "it is waiting on a merge, not working"


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


@BOTH
@pytest.mark.parametrize("opened_first", [False, True], ids=["fresh", "after a run was opened"])
def test_the_home_page_speaks_for_no_run_however_you_got_there(
    draw: Any, opened_first: bool
) -> None:
    """The header, the band and the strip each name a run; this page is about the store.

    Getting here by opening a run and pressing ``l`` used to be a different screen from
    getting here without: ``opened`` is a latch nothing lowers, so the chrome went on naming
    the run opened last — its status, its question, its pipeline — above a cursor standing
    somewhere else entirely.
    """
    shell = _store_of(_asking(), _bare(RunStatus.delivered, "run-1"))
    if opened_first:
        shell.select("run-1")
        shell.act("view:runs")
    assert shell.at_home and shell.view == "runs"

    lines = draw(shell)
    chrome = "\n".join(lines[:CHROME])
    assert "no run is open" in chrome
    assert "2 runs" in chrome, "the identity and the band count the store"
    assert "run-1" not in chrome and "delivered" not in chrome, "it spoke for a run again"
    assert "profile" not in chrome, "eight stops are eight stops of a run"
    # The card states the question the cursor is on — that is what it is for. What is not
    # here is the panel that *puts* it to you: a question is answered at the stop that raised
    # it, and this page stands at none.
    assert not any("what this rests on" in ln for ln in lines)


@BOTH
def test_the_card_names_the_run_the_cursor_is_on(draw: Any) -> None:
    """Reading a run is not opening it: the detail beside the listing follows the cursor."""
    shell = _store_of(_asking(), _bare(RunStatus.delivered, "run-1"))
    assert "run-0" in "\n".join(draw(shell)[CHROME:])
    shell.act("cursor:+1")
    body = "\n".join(draw(shell)[CHROME:])
    assert "run-1" in body and "delivered" in body
    assert not shell.opened, "the cursor moved; nothing was opened"


@BOTH
def test_opening_a_row_gives_the_chrome_back_for_that_row(draw: Any) -> None:
    """The listing used to point at one run while the header named another."""
    shell = _store_of(_asking(), _bare(RunStatus.delivered, "run-1"))
    shell.act("cursor:+1")
    shell.act("open")
    assert shell.opened and shell.run.id == "run-1"
    assert shell.view == stage_of(shell.run)
    lines = draw(shell)
    # The header names the run you opened, and the band under it speaks for the same one.
    assert "run-1" in lines[0] and "delivered" in lines[CHROME - 3]
    # Back to the listing: the cursor is still on the run that is open, not reset to the top.
    shell.act("view:runs")
    assert shell.cursor == 1


def _delivered(rid: str = "run-1") -> Run:
    """A run with something to act on: a branch to merge and a report to check a ref against."""
    run = _bare(RunStatus.delivered, rid)
    run.result.branch = f"495/{rid}"
    run.result.report_ref = "report.md"
    return run


@BOTH
@pytest.mark.parametrize("opened", [False, True], ids=["the store", "a run"])
def test_the_header_is_closed_by_a_rule(draw: Any, opened: bool) -> None:
    """Three things are stacked at the top of every screen, and the first one ends.

    Identity, then what it needs, then what it holds. Without a line under the identity the
    band's own frame opened one row under the last row of the header, and five lines read as
    one block instead of two things in a hierarchy.
    """
    shell = _store_of(_asking(), _delivered())
    if opened:
        shell.select("run-1")
    lines = draw(shell)
    assert lines[2].rstrip() == "─" * 150, "a rule, the full width of the screen"
    assert not lines[3].strip(), "and air between it and what it separates"


def test_a_control_on_the_home_acts_on_the_row_under_the_cursor() -> None:
    """The whole point of the page: one subject per screen, and it is the one it points at.

    The run that was opened last used to keep the controls, so ``d`` answered a question three
    rows above the cursor — and the footer offered it while the card described another run.
    """
    shell = _store_of(_asking(), _delivered(), driver=_Driving())
    shell.select("run-0")
    shell.act("view:runs")
    assert shell.can("decide"), "the cursor is on the run that asked"

    shell.act("cursor:+1")
    assert shell.focus is not None and shell.focus.id == "run-1"
    assert shell.run.id == "run-0", "the run opened behind the page is still the opened one"
    assert not shell.can("decide"), "it answered a question three rows above the cursor"
    offered = [key for key, _, _ in shell.footer_keys()]
    assert "d" not in offered and "m" in offered and "i" in offered
    assert shell.controls() == [
        ("m", "merge the branch"),
        ("i", "check a ref"),
        ("c", "new run"),
    ]


def test_a_surface_that_only_reads_offers_nothing_on_the_home_either() -> None:
    shell = _store_of(_asking(), _bare(RunStatus.delivered, "run-1"))
    assert shell.controls() == []
    assert [key for key, _, _ in shell.footer_keys()] == ["↑↓", "enter", "n", "?", "q"]


def test_a_key_that_names_a_stop_opens_the_row_it_is_a_stop_of() -> None:
    """A digit is "go to stop N" — of the run under the cursor, since that is the subject."""
    shell = _store_of(_asking(), _bare(RunStatus.delivered, "run-1"))
    shell.act("cursor:+1")
    shell.act("stage:spec")
    assert shell.opened and shell.run.id == "run-1" and shell.view == "spec"


def test_a_relative_move_needs_a_stop_to_move_from() -> None:
    """← and → walk to the *next* stop. The home page stands at none, so they do nothing."""
    shell = _store_of(_asking(), _bare(RunStatus.delivered, "run-1"))
    for action in ("stage:+1", "stage:-1", "filter"):
        shell.act(action)
        assert shell.at_home and not shell.opened


def test_what_the_band_names_is_where_n_puts_the_cursor() -> None:
    """One reading of the store's attention, for the two surfaces that act on it."""
    shell = _store_of(_bare(RunStatus.delivered, "run-1"), _asking())
    state = shell.store_state()
    assert state.tone == "ask" and "waiting on you" in state.headline
    assert state.key == "n" and "2 runs" in state.about
    shell.act("catchup")
    assert shell.focus is not None and shell.focus.pending_decision is not None


def test_the_band_says_what_no_single_run_can() -> None:
    """A store where nothing asks anything still has something to say about itself."""
    quiet = _store_of(_bare(RunStatus.delivered, "run-1")).store_state()
    assert quiet.tone == "good" and quiet.key is None
    idle = _store_of(_bare(RunStatus.producing, "run-2")).store_state()
    assert idle.tone == "ask" and "idle" in idle.headline
    stopped = _store_of(_bare(RunStatus.failed, "run-3"), _asking()).store_state()
    assert "waiting on you" in stopped.headline, "a question outranks a run that already ended"


def test_a_store_emptied_under_the_surface_still_has_a_page() -> None:
    """Another terminal can take the last run away; what is left is still a store."""
    shell = _store_of(driver=_Driving())
    assert shell.focus is None
    assert shell.controls() == [("c", "new run")], "nothing acts on a run; one thing makes one"
    text = "\n".join(_drawn(shell))
    assert "no run yet" in text and "no project" in text
    for action in ("open", "decide", "control:start", "catchup", "stage:spec"):
        shell.act(action)
        assert shell.at_home and not shell.opened


def test_a_store_too_long_for_the_screen_is_windowed_around_the_cursor() -> None:
    """The layout crops what does not fit without saying so, and the cursor crops first."""
    shell = _store_of(*(_bare(RunStatus.created, f"run-{n:02d}") for n in range(30)))
    for _ in range(20):
        shell.act("cursor:+1")
    text = "\n".join(_drawn(shell, height=30)[CHROME:])
    assert "21 of 30, showing" in text
    assert "run-20" in text and "run-00" not in text


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


def test_a_recorded_output_is_read_from_the_store(delivered: RunStore) -> None:
    run = delivered.list_runs()[0]
    logs = StoredLogs(delivered, run.id)
    with_output = [e for e in run.evidence if e.output_ref]
    assert with_output, "the run recorded no command output"
    assert logs.get(with_output[0])


def test_a_missing_output_reads_as_nothing_rather_than_raising(delivered: RunStore) -> None:
    run = delivered.list_runs()[0]
    evidence = run.evidence[0].model_copy(update={"output_ref": "evidence/gone.log"})
    assert StoredLogs(delivered, run.id).get(evidence) is None


# --------------------------------------------------------------------- a snapshot surface


def test_a_snapshot_surface_renders_but_offers_no_control() -> None:
    shell = Shell.over([_bare(RunStatus.created)], [], Console(file=io.StringIO()), animated=False)
    assert render(shell, "profile")
    assert shell.controls() == []
    assert shell.startable() is None
    with pytest.raises(RuntimeError):
        shell.driver.start("run-0")
