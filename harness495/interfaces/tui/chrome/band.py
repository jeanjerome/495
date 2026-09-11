"""The attention band: what the run needs from you, on every view."""

from __future__ import annotations

from rich import box
from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from harness495.core.models import Run
from harness495.interfaces.tui.attention import attention
from harness495.interfaces.tui.theme import ASK, BAD, PAD_TIGHT
from harness495.interfaces.tui.widgets.progress import WorkingBar

# How loud the band is, by what it is saying. A frame when the run is merely working; the
# whole block reversed into its colour when it has stopped and cannot go on without you. The
# escalation is the point: "it is alive" and "it is waiting on you" must not look alike.
BAND_TONE = {
    "attn.you": (f"bold black on {ASK}", "frame.ask"),
    "attn.dead": (f"bold black on {BAD}", "frame.bad"),
    "attn.done": ("", "frame.good"),
    "attn.work": ("", "frame.live"),
}


def attention_band(run: Run, paused: bool, working: WorkingBar | None) -> RenderableType:
    """The one line that says what the run needs from you — given a frame of its own.

    Between a bordered header and a bordered tab strip, an unframed line reads as a gap
    between two things rather than as a thing. So the band takes the box the header gave up:
    it is the only part of the chrome that changes colour, and the eye goes there first.
    """
    a = attention(run, paused)
    filled, border = BAND_TONE[a.tone]

    left = Text(no_wrap=True, overflow="ellipsis")
    left.append(f"{a.glyph}  ", style="" if filled else a.tone)
    left.append(a.headline.upper() if filled else a.headline, style="" if filled else a.tone)
    left.append("   ", style="")
    left.append(a.detail, style="" if filled else "h.value")

    right = Text(justify="right", no_wrap=True)
    if a.key:
        right.append(f" {a.key} ", style="key.onfill" if filled else "cursor")
        right.append(f"  {a.action}", style="" if filled else "attn.hint")

    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(ratio=1, overflow="ellipsis")
    grid.add_column(
        justify="right", width=len(right.plain) + 1 if right.plain else None, no_wrap=True
    )
    if a.working and working is not None and not filled:
        # The pulse is the only proof the run is alive; it earns a fixed slot of its own.
        grid.add_column(width=14)
        grid.add_row(left, right, working.renderable())
    else:
        grid.add_row(left, right)
    return Panel(
        grid,
        box=box.HEAVY,
        style=filled or "none",
        border_style=filled or border,
        padding=PAD_TIGHT,
    )
