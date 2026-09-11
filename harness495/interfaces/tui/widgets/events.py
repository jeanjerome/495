"""The event stream, filtered down to what the header does not already say."""

from __future__ import annotations

from collections.abc import Sequence

from rich.table import Table
from rich.text import Text

from harness495.core.models import Event
from harness495.interfaces.tui.theme import EVENT_STYLE, LOUD_EVENTS, NOISE_EVENTS
from harness495.interfaces.tui.widgets.text import clip

FILTERS = ("useful", "all", "loud")


def visible_events(events: Sequence[Event], mode: str) -> list[Event]:
    """``useful`` drops what the header already says, ``loud`` keeps only what asks something."""
    if mode == "all":
        return list(events)
    if mode == "loud":
        return [e for e in events if e.type in LOUD_EVENTS]
    return [e for e in events if e.type not in NOISE_EVENTS]


def events_table(events: Sequence[Event], rows: int, mode: str, unseen: int = 0) -> Table:
    kept = visible_events(events, mode)
    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(width=8, style="h.meta", no_wrap=True)
    table.add_column(width=20, no_wrap=True, overflow="ellipsis")
    table.add_column(ratio=1, overflow="ellipsis", no_wrap=True)
    shown = kept[-rows:]
    first_new = len(shown) - unseen if unseen else -1
    for index, ev in enumerate(shown):
        if index == first_new and 0 < unseen <= len(shown):
            table.add_row("", Text("── new ──", style="attn.you"), "")
        table.add_row(
            ev.ts.astimezone().strftime("%H:%M:%S"),
            Text(ev.type, style=EVENT_STYLE.get(ev.type, "h.meta")),
            Text(clip(ev.message, 160), style="h.value"),
        )
    if not kept:
        table.add_row("", Text("nothing yet", style="h.meta"), "")
    return table
