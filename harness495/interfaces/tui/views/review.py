"""5 · review — what independent reviewers said, and what was discarded."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from harness495.core.models import ReviewVerdict, Role, Run
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.reading import kept_findings, running_intervention
from harness495.interfaces.tui.theme import REQ_GLYPH, REQ_STYLE, SEVERITIES, VERDICT_STYLE
from harness495.interfaces.tui.views.base import StageContent, ViewContext
from harness495.interfaces.tui.widgets import (
    agent_card,
    cursor_cell,
    field_pairs,
    nothing_yet,
    panel,
    pulse,
    severity_counts,
)


def build_review(ctx: ViewContext) -> StageContent:
    run, cursor = ctx.run, ctx.cursor
    if not run.reviews:
        return StageContent(nothing_yet("no reviewer has reported yet"), label="verdicts")
    table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False)
    table.add_column(" ", width=1)
    table.add_column("perspective", width=16, style="bold", no_wrap=True)
    table.add_column("verdict", width=12, no_wrap=True)
    table.add_column("findings", width=9, no_wrap=True)
    table.add_column("in one sentence", ratio=1, overflow="ellipsis", no_wrap=True)
    for index, rv in enumerate(run.reviews):
        if rv.discarded:
            cells: list[RenderableType] = [
                Text(rv.perspective, style="h.meta"),
                Text("discarded", style="attn.dead"),
                Text("—", style="h.meta"),
                Text(rv.discard_reason, style="suf.faulty"),
            ]
        else:
            cells = [
                Text(rv.perspective, style="h.title"),
                Text(rv.verdict.value, style=VERDICT_STYLE[rv.verdict]),
                severity_counts(rv.findings),
                Text(rv.summary, style="h.value"),
            ]
        table.add_row(cursor_cell(index == cursor), *cells)

    detail = _review_detail(run, run.reviews[min(cursor, len(run.reviews) - 1)])

    below: list[RenderableType] = []
    findings = _all_findings(run)
    if findings is not None:
        below.append(findings)
    live = running_intervention(run)
    if live is not None and live.role is Role.reviewer:
        # A reviewer still reading is the reason the board is incomplete; saying so here beats
        # leaving the user to wonder why one perspective is missing.
        below.append(agent_card(run, live, pulse("agent", note=True)))
    return StageContent(
        table,
        rows=len(run.reviews),
        detail=detail,
        below=Group(*below) if below else None,
        label="verdicts",
    )


def _review_detail(run: Run, rv: ReviewVerdict) -> RenderableType:
    i = run.intervention(rv.intervention_id)
    rows: list[RenderableType] = [
        field_pairs(
            [
                ("perspective", Text(rv.perspective, style="h.ref.strong")),
                (
                    "verdict",
                    Text(
                        "discarded" if rv.discarded else rv.verdict.value,
                        style="attn.dead" if rv.discarded else VERDICT_STYLE[rv.verdict],
                    ),
                ),
                (
                    "agent",
                    Text(
                        f"{i.agent.kind.value}:{i.agent.model or 'default'}"
                        if i
                        else rv.intervention_id,
                        style="h.ref",
                    ),
                ),
                (
                    "confidence",
                    Text(
                        f"{rv.confidence:.0%}" if rv.confidence is not None else "—",
                        style="h.value",
                    ),
                ),
            ]
        )
    ]
    if rv.discarded:
        rows += [
            Text(),
            Text(rv.discard_reason, style="attn.dead"),
            Text(),
            Text(
                "A reviewer is given the tree read-only. One that writes to it has broken the "
                "condition its verdict rests on, so the verdict is dropped rather than weighed.",
                style="h.meta",
            ),
        ]
        return panel(Group(*rows), ICON["detail"], "review", rv.perspective, tone="bad")
    if rv.summary:
        rows += [Text(), Text(rv.summary, style="h.value")]
    if rv.requirement_assessment:
        rows += [Text(), Text("how it read each requirement", style="h.key")]
        for rid, status in rv.requirement_assessment.items():
            rows.append(
                Text.assemble(
                    (f"  {REQ_GLYPH[status]} ", REQ_STYLE[status]),
                    (rid, "h.title"),
                    ("  ", ""),
                    (status.value, REQ_STYLE[status]),
                )
            )
    for f in rv.findings:
        rows += [
            Text(),
            Text.assemble(
                (f"{f.severity.value}  ", f"sev.{f.severity.value}"),
                (f.title, "h.title"),
                (f"  {f.requirement_id}" if f.requirement_id else "", "h.meta"),
            ),
        ]
        if f.detail:
            rows.append(Padding(Text(f.detail, style="h.value"), (0, 0, 0, 2)))
        if f.file:
            rows.append(
                Padding(
                    Text(f.file + (f":{f.line}" if f.line else ""), style="h.ref"), (0, 0, 0, 2)
                )
            )
        if f.evidence:
            rows.append(Padding(Text(f"rests on {f.evidence}", style="h.meta"), (0, 0, 0, 2)))
    rows += [
        Text(),
        Text(
            "A reviewer never sees the producer's transcript, and its own explanation never "
            "reaches the producer: only a correction request derived from evidence does.",
            style="h.meta",
        ),
    ]
    return panel(Group(*rows), ICON["detail"], "review", rv.perspective, tone="live")


def _all_findings(run: Run) -> RenderableType | None:
    found = kept_findings(run)
    if not found:
        return None
    order = {s: i for i, s in enumerate(SEVERITIES)}
    found.sort(key=lambda pair: order[pair[1].severity])
    table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False)
    table.add_column("severity", width=9, no_wrap=True)
    table.add_column("req", width=4, style="h.meta", no_wrap=True)
    table.add_column("finding", ratio=2, overflow="ellipsis", no_wrap=True)
    table.add_column("where", ratio=1, overflow="ellipsis", no_wrap=True)
    for rv, f in found:
        where = f"{f.file}:{f.line}" if f.file and f.line else (f.file or rv.perspective)
        table.add_row(
            Text(f.severity.value, style=f"sev.{f.severity.value}"),
            f.requirement_id or "—",
            Text(f.title, style="h.value"),
            Text(where, style="h.meta"),
        )
    return panel(table, ICON["findings"], "every finding, worst first", f"{len(found)} raised")
