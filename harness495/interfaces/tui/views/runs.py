"""Every run in the store, so the surface can be entered without knowing an id."""

from __future__ import annotations

from collections.abc import Sequence

from rich import box
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from harness495.core.models import Run
from harness495.interfaces.tui.stages import STATE_GLYPH, stage_of, stage_state, status_style
from harness495.interfaces.tui.views.base import StageContent
from harness495.interfaces.tui.widgets import Responsive, clip, cursor_cell, plural

WIDE = 104


def build_runs(runs: Sequence[Run], cursor: int) -> StageContent:
    def listing(width: int) -> Table:
        wide = width >= WIDE
        table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False)
        table.add_column(" ", width=1)
        table.add_column("run", width=16, style="h.ref", no_wrap=True)
        if wide:
            table.add_column("mode", width=8, style="h.meta", no_wrap=True)
        table.add_column("stands at", width=20, no_wrap=True)
        if wide:
            table.add_column("it.", width=3, justify="right", style="h.meta")
        table.add_column("spend", width=9, justify="right")
        table.add_column("intent", ratio=1, overflow="ellipsis", no_wrap=True)
        for index, r in enumerate(runs):
            ceiling = r.budget.max_cost_usd
            ratio = (r.consumption.cost_usd / ceiling) if ceiling else 0
            spend = "gauge.high" if ratio >= 0.9 else "gauge.warn" if ratio >= 0.7 else "h.value"
            state = stage_state(r, stage_of(r))
            cells: list[RenderableType] = [cursor_cell(index == cursor), Text(r.id, style="h.ref")]
            if wide:
                cells.append(Text(r.mode.value, style="h.meta"))
            cells.append(
                Text.assemble(
                    (f"{STATE_GLYPH[state]} ", f"tab.{state}"),
                    (stage_of(r), status_style(r.status)),
                )
            )
            if wide:
                cells.append(Text(str(r.iteration_number), style="h.meta", justify="right"))
            cells += [
                Text(f"{r.consumption.cost_usd:.2f}", style=spend, justify="right"),
                Text(clip(r.intent.text, 110), style="h.title" if index == cursor else "h.value"),
            ]
            table.add_row(*cells)
        return table

    waiting = [r for r in runs if r.pending_decision is not None]
    note = Text()
    if waiting:
        note.append(
            f"{len(waiting)} {plural(len(waiting), 'run')} waiting on you: ", style="attn.you"
        )
        note.append(", ".join(r.id for r in waiting), style="h.ref")
    else:
        note.append("no run is waiting on you", style="h.meta")
    note.append("   enter opens the selected run", style="attn.hint")
    return StageContent(
        Group(Responsive(listing), Text(), note), rows=len(runs), label="runs in the store"
    )
