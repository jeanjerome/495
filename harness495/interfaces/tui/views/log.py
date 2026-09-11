"""The event stream. Not a stage: it is the record of what happened, not where the run is."""

from __future__ import annotations

from collections.abc import Sequence

from rich.console import Group
from rich.text import Text

from harness495.core.models import Event
from harness495.interfaces.tui.views.base import StageContent
from harness495.interfaces.tui.widgets import events_table, visible_events


def build_log(events: Sequence[Event], mode: str, rows: int, unseen: int) -> StageContent:
    kept = visible_events(events, mode)
    hidden = len(events) - len(kept)
    note = Text()
    note.append(f"showing {mode}", style="h.value")
    if hidden:
        note.append(f", {hidden} of {len(events)} hidden", style="h.meta")
    note.append("   f cycles useful → all → loud", style="attn.hint")
    return StageContent(
        Group(events_table(events, rows, mode, unseen), Text(), note), label="events"
    )
