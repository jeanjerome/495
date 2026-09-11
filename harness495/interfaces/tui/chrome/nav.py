"""The pipeline strip, which is also the navigation."""

from __future__ import annotations

from rich import box
from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from harness495.core.models import Run
from harness495.interfaces.tui.stages import (
    STAGES,
    STATE_GLYPH,
    Stage,
    stage_badge,
    stage_state,
)

# Shrink in one direction only, and stop at the first arrangement that fits: counts first,
# then long names, then the padding. Measuring beats a table of width thresholds, because the
# widest tab is whichever stage name happens to be longest.
ARRANGEMENTS = ((True, "full", 1), (False, "full", 1), (False, "short", 1), (False, "short", 0))


def nav_bar(run: Run, viewed: str, width: int) -> RenderableType:
    """Seven stops, each in a box of its own.

    A single dense line of coloured words does not read as navigation — it reads as one more
    status line, and at seven stops the eye cannot tell where one stop ends and the next
    begins. So each stop is a ``Panel``: its own frame, its own key printed on that frame the
    way a tab carries a label, and room to breathe between it and its neighbours.

    Two things are marked, and they are deliberately on two different channels, because they
    are two different facts:

    * **colour** — the frame, the key and the glyph share one hue, which is the state of the
      **run** at that stop. Read left to right the strip is a progress gradient: green behind,
      cyan at the stop the run is working on, grey ahead, magenta where it has stopped to ask
      you something.
    * **weight** — a heavy frame is where **you** are looking. Nothing else on the strip is
      heavy, so "where am I" survives whatever colour the stop happens to be, and no reversed
      block is needed to say it.

    ``log`` and ``runs`` are not on the strip. They are not stages, and putting them here
    would make the pipeline look like it has nine steps; the footer carries them instead.
    """
    cells: list[Text] = []
    widths: list[int] = []
    for badges, names, pad in ARRANGEMENTS:
        cells = [_tab_body(run, stage, viewed, badges, names) for stage in STAGES]
        widths = [len(c.plain) + 2 + 2 * pad for c in cells]
        if sum(widths) + len(STAGES) - 1 <= width:
            break

    grid = Table.grid(expand=True, padding=(0, 1))
    for w in widths:
        # Ratios, not fixed widths: the slack a wide terminal leaves is shared out in
        # proportion to what each tab holds, rather than given to whichever comes last.
        grid.add_column(ratio=w)
    grid.add_row(
        *(
            _tab_panel(run, stage, viewed, body, pad)
            for stage, body in zip(STAGES, cells, strict=True)
        )
    )
    return grid


def _tab_body(run: Run, stage: Stage, viewed: str, badges: bool, names: str) -> Text:
    state = stage_state(run, stage.name)
    seen = stage.name == viewed
    body = Text(no_wrap=True, overflow="ellipsis", justify="center")
    body.append(STATE_GLYPH[state], style=f"tab.{state}")
    body.append(" ")
    body.append(
        stage.name if names == "full" else stage.short,
        style="tab.name.viewed" if seen else ("tab.name.todo" if state == "todo" else "tab.name"),
    )
    if badges:
        chip = stage_badge(run, stage.name)
        if chip is not None:
            body.append(" ")
            body.append_text(chip)
    return body


def _tab_panel(run: Run, stage: Stage, viewed: str, body: Text, pad: int) -> Panel:
    state = stage_state(run, stage.name)
    return Panel(
        body,
        title=Text(stage.key, style=f"tab.{state}"),
        title_align="left",
        box=box.HEAVY if stage.name == viewed else box.ROUNDED,
        border_style=f"tab.{state}",
        padding=(0, pad),
    )
