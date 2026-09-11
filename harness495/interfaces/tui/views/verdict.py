"""6 · verdict — where each requirement stands, why, and what happens next."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from harness495.core.models import Requirement, Run
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.reading import instrument_faults, verification_state
from harness495.interfaces.tui.theme import REQ_GLYPH, REQ_STYLE
from harness495.interfaces.tui.views.base import StageContent, ViewContext
from harness495.interfaces.tui.widgets import (
    Responsive,
    bullets,
    clip,
    cursor_cell,
    nothing_yet,
    panel,
)

WIDE = 104
"""Below this the reason column goes: the detail pane carries it whole anyway."""


def build_verdict(ctx: ViewContext) -> StageContent:
    """The ledger: one row per requirement, its status, and the reason for it.

    This is the answer the whole run exists to produce. A status word in the spec table, the
    evidence behind it on another tab and the correction it caused in an iteration row are
    three places to look for one fact; here they are one line and one detail.
    """
    run, cursor = ctx.run, ctx.cursor
    reqs = run.spec.requirements
    if not reqs:
        return StageContent(nothing_yet("there is nothing to decide yet"), label="the ledger")

    def ledger(width: int) -> Table:
        wide = width >= WIDE
        table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False)
        table.add_column(" ", width=1)
        table.add_column("req", width=4, style="bold", no_wrap=True)
        table.add_column("what must hold", ratio=2, overflow="ellipsis", no_wrap=True)
        table.add_column("stands as", width=13, no_wrap=True)
        if wide:
            table.add_column("because", ratio=2, overflow="ellipsis", no_wrap=True)
        for index, r in enumerate(reqs):
            cells: list[RenderableType] = [
                cursor_cell(index == cursor),
                Text(r.id, style=REQ_STYLE[r.status]),
                Text(r.statement, style="h.value"),
                Text.assemble(
                    (f"{REQ_GLYPH[r.status]} ", REQ_STYLE[r.status]),
                    (r.status.value, REQ_STYLE[r.status]),
                ),
            ]
            if wide:
                cells.append(Text(r.status_reason or "not assessed yet", style="h.meta"))
            table.add_row(*cells)
        return table

    detail = _requirement_detail(run, reqs[min(cursor, len(reqs) - 1)])

    below: list[RenderableType] = []
    it = run.current_iteration
    if it and it.correction_requests:
        below.append(
            panel(
                Group(
                    bullets("sent back to the producer", it.correction_requests, "h.value"),
                    Text(),
                    Text(
                        "A correction request says which requirement is not demonstrated and what "
                        "was observed, never what to change: the target is the behaviour, and a "
                        "check is only how the harness looks at it.",
                        style="h.meta",
                    ),
                ),
                ICON["corrections"],
                "corrections",
                tone="warn",
            )
        )
    if run.decisions:
        taken = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False)
        taken.add_column("when", width=5, style="h.meta", no_wrap=True)
        taken.add_column("question", width=18, no_wrap=True, style="h.value")
        taken.add_column("taken", width=20, no_wrap=True)
        taken.add_column("by", width=8, style="h.meta", no_wrap=True)
        taken.add_column("why", ratio=1, overflow="ellipsis", no_wrap=True, style="h.meta")
        for d in run.decisions:
            taken.add_row(
                f"it {d.iteration}",
                d.kind.value.replace("_", " "),
                Text(d.outcome, style="h.ref"),
                d.made_by.value,
                d.rationale or "—",
            )
        below.append(panel(taken, ICON["decided"], "decisions already taken"))
    return StageContent(
        Responsive(ledger),
        rows=len(reqs),
        detail=detail,
        below=Group(*below) if below else None,
        label="the ledger",
    )


def _requirement_detail(run: Run, r: Requirement) -> RenderableType:
    rows: list[RenderableType] = [Text(r.statement, style="h.title")]
    if r.rationale:
        rows.append(Text(r.rationale, style="h.meta"))
    rows += [
        Text(),
        Text.assemble(
            (f"{REQ_GLYPH[r.status]} {r.status.value}", REQ_STYLE[r.status]),
            ("   ", ""),
            (r.status_reason or "not assessed yet", "h.value"),
        ),
        Text(),
        Text("the evidence behind that", style="h.key"),
    ]
    faults = instrument_faults(run)
    if not r.verification_ids:
        rows.append(Text("  nothing checks it, so nothing can decide it", style="req.violated"))
    for vid in r.verification_ids:
        v = run.spec.verification(vid)
        if v is None:
            continue
        glyph, style, note = verification_state(run, v)
        rows.append(
            Text.assemble(
                (f"  {glyph} ", style),
                (vid, "h.ref"),
                ("  ", ""),
                (clip(v.command or v.description, 76), "h.meta"),
            )
        )
        rows.append(Padding(Text(note, style=style), (0, 0, 0, 6)))
        if vid in faults:
            rows.append(
                Padding(
                    Text(
                        "it fails the same way without the change, so it proves nothing here",
                        style="suf.faulty",
                    ),
                    (0, 0, 0, 6),
                )
            )
    against = [
        (rv, f)
        for rv in run.reviews
        if not rv.discarded
        for f in rv.findings
        if f.requirement_id == r.id
    ]
    if against:
        rows += [Text(), Text("what the reviewers raised against it", style="h.key")]
        for rv, f in against:
            rows.append(
                Text.assemble(
                    (f"  {f.severity.value}  ", f"sev.{f.severity.value}"),
                    (f.title, "h.title"),
                    (f"  ·  {rv.perspective}", "h.meta"),
                )
            )
            if f.file:
                rows.append(
                    Padding(
                        Text(f.file + (f":{f.line}" if f.line else ""), style="h.ref"),
                        (0, 0, 0, 4),
                    )
                )
    return panel(Group(*rows), ICON["detail"], "requirement", r.id, tone="live")
