"""The page the surface opens on: the store, the run under the cursor, and 495 itself.

This is the one screen that is not about a run. The eight stops each answer a question about
one of them; this answers the three that none of them can — what is in this store, what is in
the row you are pointing at, and how 495 walks a run *here*.

It is built as a listing with a detail beside it, which is the shape six stage views already
take, so the eye reads it before it is explained: the rows are the store, the card is whichever
row the cursor is on, and nothing on the screen speaks for a run that is not one of those two
things. Reading a run is not opening it — opening changes what every key does, and a page you
cannot look around without committing to a row is a page that makes you commit to a row.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from rich import box
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from harness495.core.models import HarnessConfig, RequirementStatus, Run
from harness495.interfaces.tui.attention import attention
from harness495.interfaces.tui.chrome.band import TONE_STYLE
from harness495.interfaces.tui.headlines import headline
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.reading import kept_findings, requirement_counts
from harness495.interfaces.tui.stages import (
    STAGES,
    STATE_GLYPH,
    stage_count,
    stage_of,
    stage_state,
    status_style,
)
from harness495.interfaces.tui.views.base import StageContent
from harness495.interfaces.tui.widgets import (
    Responsive,
    clip,
    cursor_cell,
    field_pairs,
    gauge,
    hms,
    panel,
    plural,
    severity_counts,
)

WIDE = 92
"""Above this the listing carries the iteration count as well as the age."""

AGED = 72
"""Above this it carries how long ago the run was last touched.

The listing no longer has a screen to itself — the card takes two fifths of it — so the columns
are given up one at a time rather than all at once at one threshold. The intent is what survives
every trim: it is the only cell that says what the run is *for*, and the run id above it says
nothing to anyone who did not choose it."""

CHROME = 16
"""Rows the listing does not get: the header and the rule that closes it, the band, the footer,
its own frame, its heading and the line under it saying where the cursor is."""

CARD = 16
"""Rows the card costs when it is under the listing rather than beside it."""

BELOW = 13
"""Rows the panel about 495 takes, and the reason it is the first thing given up.

The store is what this page is for. How the harness works is what it says while there is room
to say it — and ``?`` says it on demand, at any height."""


@dataclass(frozen=True)
class HomeContext:
    """Everything the home page is allowed to read.

    Not a :class:`~harness495.interfaces.tui.views.base.ViewContext`: that one carries *the*
    run, and this page has no such thing. It has a store, a cursor into it, and the height it
    was given, which is what decides how much of the store fits.
    """

    runs: Sequence[Run]
    cursor: int = 0
    height: int = 40
    stacked: bool = False
    """Whether the card is under the listing rather than beside it, which the shell decides by
    width. It changes what the listing can afford: beside the rows it costs nothing, under them
    it costs sixteen."""
    held: str | None = None
    """Who else is advancing the run under the cursor, if anyone."""


def build_home(ctx: HomeContext) -> StageContent:
    runs = ctx.runs
    if not runs:
        return StageContent(_empty(), label="")
    cursor = min(ctx.cursor, len(runs) - 1)
    spare = ctx.height - CHROME - (CARD if ctx.stacked else 0)
    below = spare >= BELOW + 3
    start, end = _window(len(runs), cursor, max(3, spare - (BELOW if below else 0)))
    return StageContent(
        Group(
            Responsive(lambda w: _listing(runs, cursor, start, end, w)),
            Text(),
            _note(len(runs), cursor, start, end, ctx.stacked),
        ),
        rows=len(runs),
        detail=_card(runs[cursor], ctx.held),
        below=_harness(runs) if below else None,
        label="runs in the store",
    )


def _window(count: int, cursor: int, rows: int) -> tuple[int, int]:
    """Which slice of the store is on screen, kept around the cursor.

    A listing that draws every run it has is a listing that is silently cropped by the layout
    the moment the store outgrows the terminal — and the row that disappears first is the one
    the cursor is on, since new runs are appended and the cursor tends to be at the end.
    """
    if count <= rows:
        return 0, count
    start = min(max(0, cursor - rows // 2), count - rows)
    return start, start + rows


def _listing(runs: Sequence[Run], cursor: int, start: int, end: int, width: int) -> Table:
    wide = width >= WIDE
    aged = width >= AGED
    table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1), show_edge=False)
    table.add_column(" ", width=1)
    table.add_column("run", width=15, style="h.ref", no_wrap=True)
    table.add_column("stands at", width=13, no_wrap=True)
    if wide:
        table.add_column("it.", width=3, justify="right", style="h.meta")
    if aged:
        table.add_column("age", width=6, justify="right", style="h.meta", no_wrap=True)
    table.add_column("spend", width=8, justify="right")
    table.add_column("intent", ratio=1, overflow="ellipsis", no_wrap=True)
    for index in range(start, end):
        r = runs[index]
        ceiling = r.budget.max_cost_usd
        ratio = (r.consumption.cost_usd / ceiling) if ceiling else 0
        spend = "gauge.high" if ratio >= 0.9 else "gauge.warn" if ratio >= 0.7 else "h.value"
        state = stage_state(r, stage_of(r))
        cells: list[RenderableType] = [cursor_cell(index == cursor), Text(r.id, style="h.ref")]
        cells.append(
            Text.assemble(
                (f"{STATE_GLYPH[state]} ", f"tab.{state}"),
                (stage_of(r), status_style(r.status)),
            )
        )
        if wide:
            cells.append(Text(str(r.iteration_number), style="h.meta", justify="right"))
        if aged:
            cells.append(Text(_age(r), style="h.meta", justify="right"))
        cells += [
            Text(f"{r.consumption.cost_usd:.2f}", style=spend, justify="right"),
            Text(clip(r.intent.text, 110), style="h.title" if index == cursor else "h.value"),
        ]
        table.add_row(*cells)
    return table


def _note(count: int, cursor: int, start: int, end: int, stacked: bool) -> Text:
    """Where the cursor is in the store, and what the two halves of the screen are for.

    What the store *needs* is not said here any more: the band says it, once, at the top. Two
    statements of the same fact on one screen is how they end up disagreeing.
    """
    note = Text()
    note.append(f"{cursor + 1} of {count}", style="h.value")
    if end - start < count:
        note.append(f", showing {start + 1}–{end}", style="h.meta")
    where = "below" if stacked else "beside"
    note.append(f"   enter opens it; the card {where} is what it holds", style="attn.hint")
    return note


def _age(run: Run) -> str:
    return hms((dt.datetime.now(dt.UTC) - run.updated_at).total_seconds())


def _empty() -> RenderableType:
    """A store with nothing in it still has something to say: what would be in it."""
    return Group(
        Text("No run in this store yet.", style="h.value"),
        Text(),
        Text(
            "495 takes an intent in prose, has it specified, produced in a worktree of its own, "
            "verified by this project's own commands and reviewed from independent "
            "perspectives — then hands you a patch, a branch and a report.",
            style="h.meta",
        ),
    )


# --------------------------------------------------------------------- the run under the cursor


def _card(run: Run, held: str | None) -> RenderableType:
    """What the highlighted row holds, without opening it.

    The same three things the chrome of an open run says — where it stands, what it needs, what
    it has spent — read off the row the cursor is on rather than off a run the screen is not
    about. That is the whole difference this page turns on: the header, the band and the strip
    each speak for one run, so on a page about the store they speak from inside the card, where
    the cursor says which run they mean.
    """
    a = attention(run, held=held)
    state = Text()
    for stage in STAGES:
        st = stage_state(run, stage.name)
        state.append(f"{STATE_GLYPH[st]} ", style=f"tab.{st}")
    state.append(f" {stage_of(run)}", style=status_style(run.status))

    wants = Text.assemble((f"{a.glyph}  ", TONE_STYLE[a.tone]), (a.headline, TONE_STYLE[a.tone]))
    if a.about:
        wants.append(f"  {a.about}", style="h.meta")

    body: list[RenderableType] = [
        state,
        Text(),
        wants,
        Text(a.detail, style="h.value"),
        Text(),
        headline(run, stage_of(run)),
        Text(),
        field_pairs(_facts(run), width=8),
    ]
    return panel(Group(*body), ICON["detail"], run.id, run.mode.value, tone=a.tone)


def _facts(run: Run) -> list[tuple[str, RenderableType]]:
    it = run.current_iteration
    counts = requirement_counts(run)
    ceiling = run.budget.max_cost_usd
    spend = gauge(run.consumption.cost_usd / ceiling if ceiling else None, 8)
    spend.append(f"  {run.consumption.cost_usd:.2f}", style="h.value")
    spend.append(f" / {ceiling:.0f} USD" if ceiling else "  no ceiling", style="h.meta")

    pairs: list[tuple[str, RenderableType]] = [
        ("intent", Text(clip(run.intent.text, 220), style="h.value")),
        ("since", Text(f"{_age(run)} ago · iteration {run.iteration_number}", style="h.meta")),
        ("spend", spend),
    ]
    if run.spec.requirements:
        ledger = Text()
        for status, glyph in (
            (RequirementStatus.satisfied, "●"),
            (RequirementStatus.violated, "✕"),
            (RequirementStatus.undetermined, "◐"),
            (RequirementStatus.pending, "○"),
        ):
            if counts[status]:
                ledger.append(f"{counts[status]}{glyph} ", style=f"req.{status.value}")
        checks, bad = stage_count(run, "checks")
        if checks:
            ledger.append(f" {checks} checks", style="tab.count.bad" if bad else "h.meta")
        pairs.append(("ledger", ledger))
    findings = kept_findings(run)
    if findings:
        pairs.append(("findings", severity_counts(f for _, f in findings)))
    if it and it.version and it.version.head_commit:
        files = len(it.version.files_changed)
        pairs.append(("change", Text(f"{files} {plural(files, 'file')} touched", style="h.value")))
    if run.result.branch:
        landed = {
            "landed": ("it carries the verified change", "req.satisfied"),
            "differs": ("it carries something else", "req.violated"),
            "unmerged": ("nothing has been merged into it", "h.meta"),
            "unchecked": ("nothing has been merged; that is your call", "h.meta"),
        }[run.integration_state()]
        branch = Text(run.result.branch, style="h.ref")
        branch.append(f"  {landed[0]}", style=landed[1])
        pairs.append(("branch", branch))
    if run.warnings:
        pairs.append(("warning", Text(clip(run.warnings[-1], 160), style="gauge.warn")))
    return pairs


# --------------------------------------------------------------------- 495 itself


def _harness(runs: Sequence[Run]) -> RenderableType:
    """How a run is walked *here*, and the four rules that hold whatever is configured.

    The configuration is read off the most recent run rather than off a file: a run carries the
    configuration it was created with, which is what actually walked it, and a file says what
    the next one would get. Which run it came from is on the frame, because two runs in one
    store can have been walked by different agents under different ceilings.

    What is *not* here is the list of the eight stops. ``?`` has it, with every key, and a page
    that repeats the help is a page whose bottom half is never read twice.
    """
    newest = runs[-1]
    cfg = newest.config
    perspectives = ", ".join(r.perspective for r in cfg.roles.reviewers) or "none"
    sandbox = cfg.sandbox.backend
    network = "network allowed" if cfg.sandbox.allow_network else "network denied"
    b = cfg.budget
    ceiling = f"{b.max_cost_usd:.0f} USD" if b.max_cost_usd else "no spend ceiling"
    commands = newest.profile.commands if newest.profile else []
    what = field_pairs(
        [
            (
                "agents",
                Text.assemble(
                    (_agent(cfg, cfg.roles.producer), "h.value"),
                    (" produces  ·  ", "h.meta"),
                    (_agent(cfg, cfg.roles.specifier), "h.value"),
                    (" specifies", "h.meta"),
                    *(
                        (
                            ("  ·  ", "h.meta"),
                            (_agent(cfg, cfg.roles.test_designer), "h.value"),
                            (" writes the tests", "h.meta"),
                        )
                        if cfg.roles.test_designer
                        else ()
                    ),
                ),
            ),
            ("reviewed by", Text(perspectives, style="h.value")),
            (
                "isolation",
                Text(f"one git worktree per run · {sandbox}, {network}", style="h.value"),
            ),
            (
                "ceilings",
                Text(
                    f"{ceiling} · {b.max_iterations} iterations · {b.max_interventions} agent runs",
                    style="h.value",
                ),
            ),
            (
                "verified by",
                Text(
                    ", ".join(c.name for c in commands)
                    if commands
                    else "whatever the project declares",
                    style="h.value",
                ),
            ),
        ],
        width=12,
    )
    rules = Text(
        "a requirement is decided by evidence, never by an agent's word · every check is run "
        "with and without the change, and one that reports the same thing both times is taken "
        "out of the evidence · nothing reaches your tree until you ask · ? lists the eight "
        "stops and every key",
        style="h.meta",
    )
    return panel(
        Group(what, Text(), rules),
        ICON["pipeline"],
        "how 495 walks a run here",
        subtitle=f"as configured for {newest.id}",
    )


def _agent(cfg: HarnessConfig, name: str) -> str:
    try:
        spec = cfg.agent(name)
    except KeyError:
        return name
    return f"{spec.kind.value}:{spec.model}" if spec.model else spec.kind.value
