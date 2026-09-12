"""The attention band: what the run needs from you, on every view."""

from __future__ import annotations

from rich import box
from rich.cells import cell_len
from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from harness495.interfaces.tui.attention import Attention
from harness495.interfaces.tui.theme import PAD_TIGHT
from harness495.interfaces.tui.widgets.panels import TITLE_LEAD
from harness495.interfaces.tui.widgets.progress import spin

#: The four states of a run, in the styles the rest of the surface already speaks.
TONE_STYLE = {"live": "attn.work", "ask": "attn.you", "bad": "attn.dead", "good": "attn.done"}


def attention_band(a: Attention, moving: bool = False, frozen: bool = False) -> RenderableType:
    """The one line that says what the run needs from you — shaped like every other block.

    It was a heavy frame whose interior reversed into magenta or red the moment the run
    wanted something, with the headline shouted in capitals. It read as a slab dropped on a
    surface where every other block is a rounded frame with a title on it, and the escalation
    it bought was not needed: one screen holds at most one band, so there is nothing for it to
    shout over. What it cost was legibility — a reversed line takes the hue of its state and
    leaves the words to fight it, and two of the four states never filled at all, so the same
    fact came out in capitals or in lower case depending on which one was true.

    So: a rounded frame like the rest, the state on it as a title, the sentence under it, and
    the key on the right. The colour of the frame and of the title is the state — red where
    it stopped, magenta where only a human moves it on, cyan while something advances it,
    green where it is done — which is the same six meanings every other frame is coloured by.
    The key chip stays cyan wherever it appears, because a chip is a handle rather than a
    state, and the decision panel draws it that way too.

    ``frozen`` is the *surface* stopping, not the run: it goes on the frame, where it cannot
    take the place of what the run is saying.
    """
    style = TONE_STYLE[a.tone]
    # The one thing on the band that moves, and only where movement is drawn rather than
    # recorded. It turns for the same fact the pipeline strip turns on, one stop away.
    glyph = spin("band").glyph() if moving and a.working else a.glyph

    title = Text(no_wrap=True)
    title.append(glyph + " " * max(1, TITLE_LEAD - cell_len(glyph)), style=style)
    title.append(a.headline, style=style)
    if a.about:
        title.append(f"  {a.about}", style="h.meta")

    left = Text(a.detail, style="h.value", no_wrap=True, overflow="ellipsis")
    right = Text(justify="right", no_wrap=True)
    if a.key:
        right.append(f" {a.key} ", style="cursor")
        right.append(f"  {a.action}", style="attn.hint")

    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(ratio=1, overflow="ellipsis")
    grid.add_column(
        justify="right", width=len(right.plain) + 1 if right.plain else None, no_wrap=True
    )
    grid.add_row(left, right)
    return Panel(
        grid,
        title=title,
        title_align="left",
        subtitle=Text("‖ frozen · space thaws it", style="gauge.warn") if frozen else None,
        subtitle_align="right",
        box=box.ROUNDED,
        border_style=f"frame.{a.tone}",
        padding=PAD_TIGHT,
    )
