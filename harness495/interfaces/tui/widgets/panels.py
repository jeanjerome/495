"""The frame around a block of content, and the title on it."""

from __future__ import annotations

from rich import box
from rich.cells import cell_len
from rich.console import RenderableType
from rich.panel import Panel
from rich.text import Text

from harness495.interfaces.tui.theme import PAD

TITLE_LEAD = 4
"""Cells a panel title reserves for its icon: the glyph, plus the gap after it.

A constant rather than one space, because the two kinds of glyph are not the same object. An
emoji is a full-bleed two-cell bitmap; a geometric mark is one cell with side bearings on both
sides. The same single space therefore reads as air after ● and as nothing at all after 📋.
Padding every lead to the same width settles that, and has the side effect that the words of
every title on screen start in the same column, however the panels are stacked.
"""


def title_text(glyph: str, name: str, suffix: str = "") -> Text:
    lead = glyph + " " * max(1, TITLE_LEAD - cell_len(glyph))
    head = Text.assemble((lead, "h.ref"), (name, "h.title"))
    if suffix:
        head.append(f"  {suffix}", style="h.meta")
    return head


def panel(
    body: RenderableType,
    glyph: str,
    name: str,
    suffix: str = "",
    *,
    tone: str = "quiet",
    subtitle: str = "",
) -> Panel:
    """A framed block of content.

    ``tone`` is a *reason*, not a colour — ``quiet``, ``live``, ``warn``, ``bad``, ``good``,
    ``ask`` — and it is the only way to colour a frame. Taking a colour here is how an
    interface ends up with a blue budget panel next to a yellow agent panel next to a cyan
    detail panel, none of which agree on what a blue border is supposed to mean.

    Every panel is ``ROUNDED``, the band included. Weight is reserved: ``HEAVY`` appears on
    exactly two things, and both are where you are — the tab you are standing on, and the
    question you cannot walk past.
    """
    return Panel(
        body,
        title=title_text(glyph, name, suffix),
        title_align="left",
        subtitle=Text(subtitle, style="h.meta") if subtitle else None,
        subtitle_align="right",
        box=box.ROUNDED,
        border_style=f"frame.{tone}",
        padding=PAD,
    )
