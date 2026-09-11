"""2 · spec — what must hold after the change, and what checks it."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from harness495.core.models import RequirementStatus, Sufficiency
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.theme import REQ_GLYPH, REQ_STYLE
from harness495.interfaces.tui.views.base import StageContent, ViewContext
from harness495.interfaces.tui.widgets import (
    bullets,
    cursor_cell,
    nothing_yet,
    panel,
    shell_block,
)


def build_spec(ctx: ViewContext) -> StageContent:
    run, cursor = ctx.run, ctx.cursor
    spec = run.spec
    if not spec.requirements:
        return StageContent(
            nothing_yet("the specifier has not produced a requirement yet"), label="requirements"
        )
    table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False)
    table.add_column(" ", width=1)
    table.add_column("req", width=4, style="bold", no_wrap=True)
    table.add_column("what must hold after the change", ratio=1, overflow="ellipsis", no_wrap=True)
    table.add_column("checked by", width=12, no_wrap=True)
    for index, r in enumerate(spec.requirements):
        # Each check is coloured by its own sufficiency: at the gate, "R3 is checked by
        # something that cannot see the change" is the fact the decision turns on, and a
        # uniformly cyan list of ids hides exactly that.
        checks = Text()
        for vid in r.verification_ids:
            v = spec.verification(vid)
            if checks.plain:
                checks.append(", ", style="h.meta")
            checks.append(
                vid,
                style="h.ref"
                if v is None or v.sufficiency is Sufficiency.sufficient
                else f"suf.{v.sufficiency.value}",
            )
        if not checks.plain:
            checks = Text("nothing", style="req.violated")
        table.add_row(
            cursor_cell(index == cursor),
            Text(r.id, style=REQ_STYLE[r.status]),
            Text(r.statement, style="h.value"),
            checks,
        )

    r = spec.requirements[min(cursor, len(spec.requirements) - 1)]
    rows: list[RenderableType] = [Text(r.statement, style="h.title")]
    if r.rationale:
        rows.append(Text(r.rationale, style="h.meta"))
    rows.append(Text())
    if not r.verification_ids:
        rows.append(
            Text(
                "Nothing checks this requirement, so no evidence can decide it. 495 reports it "
                "as a gap rather than assuming it holds.",
                style="req.violated",
            )
        )
    tree = Tree(Text("checked by", style="h.key"), guide_style="h.rule")
    for vid in r.verification_ids:
        v = spec.verification(vid)
        if v is None:
            continue
        flags = Text()
        if v.to_create:
            flags.append("  to create", style="gauge.warn")
        if v.sufficiency is not Sufficiency.sufficient:
            flags.append(f"  {v.sufficiency.value}", style=f"suf.{v.sufficiency.value}")
        node = tree.add(Text.assemble((v.id, "h.ref"), "  ", (v.kind.value, "h.meta")) + flags)
        if v.command:
            node.add(shell_block(v.command))
        if v.description:
            node.add(Text(v.description, style="h.value"))
        if v.rationale:
            node.add(Text(v.rationale, style=f"suf.{v.sufficiency.value}"))
    rows.append(tree)
    if r.status is not RequirementStatus.pending:
        rows += [
            Text(),
            Text.assemble(
                (f"{REQ_GLYPH[r.status]} {r.status.value}  ", REQ_STYLE[r.status]),
                (r.status_reason, "h.value"),
            ),
        ]
    detail = panel(Group(*rows), ICON["detail"], "requirement", r.id, tone="live")

    edges = Table.grid(padding=(0, 2), expand=True)
    edges.add_column(ratio=1)
    edges.add_column(ratio=1)
    edges.add_row(
        bullets("the producer may only touch", spec.allowed_paths, "h.ref"),
        bullets("deliberately out of scope", spec.out_of_scope, "h.meta"),
    )
    edges.add_row(
        bullets("assumed, not verified", spec.assumptions, "h.meta"),
        bullets("known gaps in the evidence", spec.gaps, "suf.insufficient"),
    )
    drawn = any((spec.allowed_paths, spec.out_of_scope, spec.assumptions, spec.gaps))
    return StageContent(
        table,
        rows=len(spec.requirements),
        detail=detail,
        below=panel(edges, ICON["scope"], "the edges of this run") if drawn else None,
        label="requirements",
    )
