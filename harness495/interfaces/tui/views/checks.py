"""4 · checks — what the verification commands observed on the candidate."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from harness495.core.models import Run, Verification
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.logs import Logs
from harness495.interfaces.tui.reading import (
    evidence_for,
    instrument_faults,
    latest_results,
    scope_checks,
    verification_state,
)
from harness495.interfaces.tui.views.base import StageContent, ViewContext
from harness495.interfaces.tui.widgets import (
    Responsive,
    clip,
    cursor_cell,
    field_pairs,
    log_block,
    nothing_yet,
    panel,
    plural,
    shell_block,
    short,
)

WIDE = 88
"""Below this the kind and the requirements a check carries go; the observation never does."""


def build_checks(ctx: ViewContext) -> StageContent:
    run, cursor = ctx.run, ctx.cursor
    faults = instrument_faults(run)
    latest = latest_results(run)
    vs = run.spec.verifications

    if not vs:
        return StageContent(
            nothing_yet(
                "nothing is specified yet, so there is nothing to check"
                if not run.spec.requirements
                else "the approved specification carries no check"
            ),
            label="checks",
        )

    def board(width: int) -> Table:
        wide = width >= WIDE
        table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False)
        table.add_column(" ", width=1)
        table.add_column("check", width=5, style="h.ref", no_wrap=True)
        if wide:
            table.add_column("kind", width=10, style="h.meta", no_wrap=True)
            table.add_column("carries", width=9, style="h.meta", no_wrap=True)
        table.add_column(
            "what it observed on the candidate", ratio=1, overflow="ellipsis", no_wrap=True
        )
        table.add_column("took", width=7, justify="right", style="h.meta")
        for index, v in enumerate(vs):
            glyph, style, note = verification_state(run, v)
            carried = [r.id for r in run.spec.requirements if v.id in r.verification_ids]
            e = latest.get(v.id)
            cells: list[RenderableType] = [cursor_cell(index == cursor), Text(v.id, style="h.ref")]
            if wide:
                cells += [
                    Text(v.kind.value, style="h.meta"),
                    Text(",".join(carried) or "—", style="h.meta"),
                ]
            cells += [
                Text.assemble((f"{glyph} ", style), (clip(note, 120), "h.value")),
                Text(f"{e.duration_s:.2f}s" if e and e.duration_s else "", style="h.meta"),
            ]
            table.add_row(*cells)
        return table

    v = vs[min(cursor, len(vs) - 1)]
    detail = check_detail(run, v, v.id in faults, ctx.logs)

    notes: list[tuple[str, RenderableType]] = []
    scope = scope_checks(run)
    if scope:
        notes.append(
            (
                "scope check",
                Text(
                    scope[-1].summary,
                    style="req.satisfied" if scope[-1].passed else "req.violated",
                ),
            )
        )
    if faults:
        named = ", ".join(sorted(faults))
        one = len(faults) == 1
        notes.append(
            (
                plural(len(faults), "blind check"),
                Text(
                    f"{named} failed identically on the base version. 495 takes "
                    f"{'it' if one else 'them'} out of the evidence rather than turning "
                    f"{'it' if one else 'them'} into work for the producer.",
                    style="suf.faulty",
                ),
            )
        )
    notes += [("gap", Text(gap, style="suf.insufficient")) for gap in run.spec.gaps]
    below = (
        panel(
            field_pairs(notes, width=13),
            ICON["limits"],
            "what this evidence cannot show",
            tone="warn",
        )
        if notes
        else None
    )
    return StageContent(Responsive(board), rows=len(vs), detail=detail, below=below, label="checks")


def check_detail(run: Run, v: Verification, faulty: bool, logs: Logs) -> RenderableType:
    glyph, style, note = verification_state(run, v)
    records = evidence_for(run, v.id)
    carried = [r for r in run.spec.requirements if v.id in r.verification_ids]
    rows: list[RenderableType] = [
        field_pairs(
            [
                ("check", Text(f"{v.id} · {v.kind.value}", style="h.ref.strong")),
                ("state", Text(f"{glyph} {note}", style=style)),
                ("carries", Text(", ".join(r.id for r in carried) or "nothing", style="h.value")),
                (
                    "sufficiency",
                    Text(
                        "cannot see the change" if faulty else v.sufficiency.value,
                        style="suf.faulty" if faulty else f"suf.{v.sufficiency.value}",
                    ),
                ),
                ("expects", Text(f"exit {v.expected_exit_code}", style="h.value")),
            ]
        )
    ]
    if v.description:
        rows += [Text(), Text(v.description, style="h.value")]
    if v.command:
        rows += [Text(), Text("command", style="h.key"), shell_block(v.command)]
    for e in records:
        mark, est = (
            ("◐", "req.undetermined")
            if e.passed is None
            else (("✓", "req.satisfied") if e.passed else ("✕", "req.violated"))
        )
        rows += [
            Text(),
            Text.assemble(
                (f"{mark} ", est),
                (e.kind.value.replace("_", " "), "h.title"),
                ("  on ", "h.meta"),
                (short(e.subject_version) if e.subject_version else "—", "h.ref"),
                (f"  exit {e.exit_code}", "h.meta"),
                (f"  {e.duration_s:.2f}s" if e.duration_s else "", "h.meta"),
            ),
            Text(f"  {e.summary}", style="h.value"),
        ]
        log = logs.get(e)
        if log:
            rows.append(log_block(log))
        elif e.output_ref:
            rows.append(Text(f"  output kept at {e.output_ref}", style="h.meta"))
    if faulty:
        rows += [
            Text(),
            Text(
                "This command fails the same way with and without the change, so it measures "
                "something else. Anything it carries stays undetermined until the check is "
                "replaced — 495 will not ask the producer to chase it.",
                style="suf.faulty",
            ),
        ]
    return panel(
        Group(*rows), ICON["detail"], "check", v.id, tone="live", subtitle="enter · full log"
    )
