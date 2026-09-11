"""3 · change — what the producer did, in which sandbox, at what cost."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from harness495.core.models import Role, Run
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.reading import (
    allowing_glob,
    findings_on,
    running_intervention,
)
from harness495.interfaces.tui.theme import VERDICT_STYLE
from harness495.interfaces.tui.views.base import StageContent, ViewContext
from harness495.interfaces.tui.widgets import (
    Responsive,
    agent_card,
    budget_panel,
    bullets,
    clip,
    cursor_cell,
    field_pairs,
    nothing_yet,
    panel,
    pulse,
    severity_counts,
    short,
    two_columns,
)


def build_change(ctx: ViewContext) -> StageContent:
    run, cursor = ctx.run, ctx.cursor
    it = run.current_iteration
    v = it.version if it else None
    producer = next(
        (i for i in reversed(run.interventions) if i.role is Role.producer),
        running_intervention(run),
    )
    files = list(v.files_changed) if v else []

    table: RenderableType = nothing_yet(
        "the producer is still working; nothing is committed yet"
        if running_intervention(run) is not None
        else "no file has been changed"
    )
    listed = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False)
    listed.add_column(" ", width=1)
    listed.add_column("file the producer changed", ratio=1, overflow="ellipsis", no_wrap=True)
    listed.add_column("allowed by", width=26, no_wrap=True, overflow="ellipsis")
    listed.add_column("findings", width=9, no_wrap=True)
    for index, path in enumerate(files):
        glob = allowing_glob(run.spec.allowed_paths, path)
        against = findings_on(run, path)
        listed.add_row(
            cursor_cell(index == cursor),
            Text(path, style="h.value"),
            Text(glob or "outside the allowed paths", style="h.ref" if glob else "req.violated"),
            severity_counts(f for _, f in against),
        )
    if files:
        table = listed

    detail = None
    if files:
        path = files[min(cursor, len(files) - 1)]
        glob = allowing_glob(run.spec.allowed_paths, path)
        rows: list[RenderableType] = [
            field_pairs(
                [
                    ("file", Text(path, style="h.ref.strong")),
                    (
                        "allowed by",
                        Text(
                            glob or "no glob — this is a scope violation",
                            style="h.ref" if glob else "req.violated",
                        ),
                    ),
                ]
            )
        ]
        against = findings_on(run, path)
        if against:
            rows += [Text(), Text("what the reviewers said about it", style="h.key")]
            for rv, f in against:
                rows.append(
                    Text.assemble(
                        (f"{f.severity.value}  ", f"sev.{f.severity.value}"),
                        (f.title, "h.title"),
                        (f"  ·  {rv.perspective}", "h.meta"),
                        (f"  line {f.line}" if f.line else "", "h.meta"),
                    )
                )
                if f.detail:
                    rows.append(Padding(Text(f.detail, style="h.meta"), (0, 0, 0, 2)))
        else:
            rows += [Text(), Text("no reviewer raised anything against this file", style="h.meta")]
        detail = panel(Group(*rows), ICON["detail"], "file", tone="live")

    claims = (
        panel(
            Group(
                bullets("the producer reports it could not", it.blocked_claims, "suf.insufficient"),
                Text(),
                Text(
                    "A claim, not a fact: it is what the agent said about its own turn, "
                    "surfaced so you can judge it, never used as evidence.",
                    style="h.meta",
                ),
            ),
            ICON["claims"],
            "blocked claims",
            tone="warn",
        )
        if it and it.blocked_claims
        else None
    )
    history = _iteration_history(run) if len(run.iterations) > 1 else None
    below: list[RenderableType] = [
        two_columns(
            agent_card(run, producer, pulse("agent", note=True)), budget_panel(run), ratio=(3, 2)
        )
    ]
    # Paired rather than stacked: both are short, both are about the attempt rather than the
    # files, and four full-width panels under one list is how a stage runs off the screen.
    if claims is not None and history is not None:
        below.append(two_columns(claims, history))
    elif claims is not None:
        below.append(claims)
    elif history is not None:
        below.append(history)
    return StageContent(
        table, rows=len(files), detail=detail, below=Group(*below), label="files changed"
    )


def _iteration_history(run: Run) -> RenderableType:
    """What each earlier attempt left behind, so a third one is not a mystery."""

    def table(width: int) -> Table:
        # Paired with another panel this lands in half a screen, where a ratio column is a
        # column of nothing. Below that it drops out rather than pretending to be there.
        wide = width >= 64
        t = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False)
        t.add_column("it.", width=4, style="bold")
        t.add_column("version", width=10, style="h.ref", no_wrap=True)
        t.add_column("outcome", width=13, no_wrap=True)
        if wide:
            t.add_column("what it left behind", ratio=1, overflow="ellipsis", no_wrap=True)
        for it in run.iterations:
            left = it.correction_requests or it.blocked_claims or ["—"]
            cells: list[RenderableType] = [
                Text(str(it.n), style="bold"),
                Text(short(it.version.head_commit) if it.version else "—", style="h.ref"),
                Text(
                    it.outcome.value if it.outcome else "in progress",
                    style=VERDICT_STYLE.get(it.outcome, "attn.work") if it.outcome else "attn.work",
                ),
            ]
            if wide:
                cells.append(Text(clip(left[0], 110), style="h.meta"))
            t.add_row(*cells)
        return t

    return panel(Responsive(table), ICON["attempts"], "attempts", f"{len(run.iterations)} so far")
