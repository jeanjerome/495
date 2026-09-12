"""The run surface: every stop renders what the run actually holds, at any width."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from rich.cells import cell_len
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
from harness495.interfaces.tui.attention import attention
from harness495.interfaces.tui.chrome import footer_bar, logo, nav_bar
from harness495.interfaces.tui.chrome.band import TONE_STYLE
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
        # The pipeline strip is on every view, whichever one is open.
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


# --------------------------------------------------------------------- the listing


def _store_of(*runs: Run) -> Shell:
    """What ``495 watch`` builds when no run id was given: a listing, and nothing open."""
    console = Console(theme=THEME, file=io.StringIO(), width=150, highlight=False)
    return Shell(StaticSource(runs, []), console, animated=False)


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


@BOTH
def test_nothing_speaks_for_a_run_until_one_is_opened(draw: Any) -> None:
    """The header, the band and the strip each name a run; on the listing none is picked."""
    shell = _store_of(_asking(), _bare(RunStatus.delivered, "run-1"))
    assert not shell.opened and shell.view == "runs"
    lines = draw(shell)
    # Two rows of store identity, then the listing: nothing in between speaks for a run.
    assert "no run is open" in lines[0]
    assert "runs in the store" in lines[2]
    assert not any("approve?" in ln for ln in lines), "it asked a question nobody opened"
    assert [k for k, _, _ in shell.footer_keys()] == ["↑↓", "enter", "?", "q"]


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
    assert "run-1" in lines[0] and "delivered" in lines[2]
    # Back to the listing: the cursor is still on the run that is open, not reset to the top.
    shell.act("view:runs")
    assert shell.cursor == 1


def test_a_key_that_acts_on_a_run_does_nothing_while_none_is_open() -> None:
    shell = _store_of(_asking(), _bare(RunStatus.delivered, "run-1"))
    for action in ("stage:spec", "view:log", "catchup", "decide", "control:start"):
        shell.act(action)
        assert shell.view == "runs" and not shell.opened
    assert not shell.can("decide") and not shell.can("control:start")


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


def test_the_mark_dissolves_each_digit_once_per_cycle() -> None:
    seen = {logo.frame(t / 100)[1] for t in range(int(logo.CYCLE * 100))}
    assert seen == {None, 0, 1, 2}


def test_the_mark_is_a_pure_function_of_the_clock() -> None:
    """Two surfaces refreshing at different rates must draw the same frame at the same instant."""
    assert logo.frame(2.5) == logo.frame(2.5 + logo.CYCLE)
    assert logo.frame(0.0) == (logo.DIGITS, None, "h.logo")


def test_the_mark_keeps_its_holes_when_it_dissolves() -> None:
    """A morph that filled the gaps would print three rectangles instead of 4 9 5."""
    assert logo.morph(logo.DIGITS[0], "░") == ("░ ░", "░░░")


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
