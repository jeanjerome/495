"""1 · profile — what 495 understood about this project, and what it can actually run."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.views.base import StageContent, ViewContext
from harness495.interfaces.tui.widgets import (
    bullets,
    clip,
    cursor_cell,
    field_pairs,
    nothing_yet,
    panel,
    shell_block,
    short,
    two_columns,
)


def build_profile(ctx: ViewContext) -> StageContent:
    run, cursor = ctx.run, ctx.cursor
    p = run.profile
    if p is None or not p.commands:
        return StageContent(
            nothing_yet("495 has not read this project yet"), label="verification commands"
        )

    table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False)
    table.add_column(" ", width=1)
    table.add_column("command", width=10, style="bold", no_wrap=True)
    table.add_column("runs as", ratio=2, overflow="ellipsis", no_wrap=True, style="h.ref")
    table.add_column("on the base version", ratio=2, overflow="ellipsis", no_wrap=True)
    table.add_column("took", width=7, justify="right", style="h.meta")

    ready = {r.command_name: r for r in p.readiness}
    for index, c in enumerate(p.commands):
        r = ready.get(c.name)
        if r is None:
            state = Text("◐ not tried", style="req.pending")
        elif r.executable:
            state = Text.assemble(("✓ ", "req.satisfied"), (clip(r.detail, 60), "h.value"))
        else:
            state = Text.assemble(
                ("✕ cannot run here — ", "req.violated"), (clip(r.detail, 50), "h.value")
            )
        table.add_row(
            cursor_cell(index == cursor),
            c.name,
            c.command,
            state,
            f"{r.duration_s:.1f}s" if r and r.duration_s else "",
        )

    c = p.commands[min(cursor, len(p.commands) - 1)]
    r = ready.get(c.name)
    rows: list[RenderableType] = [
        field_pairs(
            [
                ("command", Text(c.name, style="h.ref.strong")),
                ("kind", Text(c.kind.value, style="h.value")),
                ("declared by", Text(c.source, style="h.value")),
                (
                    "timeout",
                    Text(f"{c.timeout_s or run.budget.command_timeout_s}s", style="h.value"),
                ),
            ]
        ),
        Text(),
        Text("runs as", style="h.key"),
        shell_block(c.command),
    ]
    if r is not None:
        rows += [
            Text(),
            Text("proved on the base version", style="h.key"),
            Text(
                f"exit {r.exit_code} in {r.duration_s:.1f}s",
                style="req.satisfied" if r.executable else "req.violated",
            ),
            Text(r.detail, style="h.value"),
        ]
        if not r.executable:
            rows += [
                Text(),
                Text(
                    "A command that cannot run here proves nothing about the change. 495 asks "
                    "you whether to drop it, retry it, or stop — it never quietly passes it.",
                    style="suf.insufficient",
                ),
            ]
    detail = panel(Group(*rows), ICON["detail"], "command", c.name, tone="live")

    facts = panel(
        field_pairs(
            [
                ("project", Text(p.root, style="h.value")),
                ("languages", Text(", ".join(p.languages) or "—", style="h.value")),
                ("tooling", Text(", ".join(p.tooling) or "—", style="h.value")),
                ("read from", Text(", ".join(p.detected_from) or "—", style="h.meta")),
                (
                    "base",
                    Text(f"{short(p.base_commit, 12)} on {p.default_branch or '—'}", style="h.ref"),
                ),
            ]
        ),
        ICON["project"],
        "project",
    )
    given = panel(
        Group(
            bullets("conventions the agents are held to", p.conventions, "h.value"),
            Text(),
            bullets("documents put in their context", p.doc_files, "h.ref"),
        ),
        ICON["briefing"],
        "what the agents are told",
    )
    return StageContent(
        table,
        rows=len(p.commands),
        detail=detail,
        below=two_columns(facts, given),
        label="verification commands",
    )
