"""The decision: visible while it waits, answerable where it is asked.

A decision kept behind a footer key makes the one thing the run is stopped for the least
visible thing on the screen. Here the question is rendered in the body of the stage that
raised it, above everything else, and the keyboard only ever opens the input for it.
"""

from __future__ import annotations

import datetime as dt

from rich import box
from rich.cells import cell_len
from rich.console import Console, Group, RenderableType
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from harness495.core.models import (
    DecisionKind,
    PendingDecision,
    RequirementStatus,
    Run,
)
from harness495.interfaces.tui.asking import Answers, Question, Step, ask_in_prompt
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.reading import requirement_counts
from harness495.interfaces.tui.theme import PAD, REQ_STYLE
from harness495.interfaces.tui.widgets import (
    TITLE_LEAD,
    Choice,
    Responsive,
    choices,
    field_pairs,
    hms,
    plural,
)


def decision_panel(run: Run, pending: PendingDecision, focused: bool = True) -> Panel:
    waited = (dt.datetime.now(dt.UTC) - pending.raised_at).total_seconds()
    body: list[RenderableType] = [Text(pending.question, style="h.title"), Text()]
    facts = decision_facts(run, pending)
    if facts:
        body += [
            Text("what this rests on", style="h.key"),
            Padding(field_pairs(facts, width=14), (0, 0, 0, 2)),
            Text(),
        ]
    body.append(Responsive(lambda w: _options_grid(pending, w)))
    if any(o.needs_note for o in pending.options):
        body += [
            Text(),
            Text("* asks you for a note; it becomes the record of why", style="attn.hint"),
        ]
    body += [
        Text(),
        Text.assemble((" d ", "cursor"), ("  answer it here", "attn.hint")),
        Text(f"      or, from any shell:  495 decide {run.id} <choice>", style="h.meta"),
    ]
    return Panel(
        Group(*body),
        title=Text.assemble(
            (ICON["question"] + " " * max(1, TITLE_LEAD - cell_len(ICON["question"])), "attn.you"),
            ("495 is waiting on you", "h.title"),
            (f"  {pending.kind.value.replace('_', ' ')}", "h.meta"),
        ),
        title_align="left",
        subtitle=Text(f"asked {hms(waited)} ago", style="h.meta"),
        subtitle_align="right",
        box=box.HEAVY,
        border_style="frame.ask" if focused else "frame.quiet",
        padding=PAD,
    )


def _options_grid(pending: PendingDecision, width: int) -> Table:
    """The decision's own options, in the shape every question 495 asks takes."""
    return choices(
        [Choice(o.key, o.label, o.consequence, o.needs_note) for o in pending.options], width
    )


NEEDS_LEDGER = frozenset(
    {DecisionKind.undetermined, DecisionKind.acceptance, DecisionKind.iteration_limit}
)


def decision_facts(run: Run, pending: PendingDecision) -> list[tuple[str, RenderableType]]:
    """The facts the question rests on, laid out rather than packed into the question."""
    out: list[tuple[str, RenderableType]] = []
    counts = requirement_counts(run)
    if pending.kind in NEEDS_LEDGER:
        line = Text()
        for status in (
            RequirementStatus.satisfied,
            RequirementStatus.violated,
            RequirementStatus.undetermined,
            RequirementStatus.pending,
        ):
            if counts[status]:
                line.append(f"{counts[status]} {status.value}   ", style=REQ_STYLE[status])
        out.append(("requirements", line))
    it = run.current_iteration
    if it and it.instrument_faults:
        n = len(it.instrument_faults)
        out.append(
            (
                plural(n, "blind check"),
                Text(
                    f"{', '.join(it.instrument_faults)} {plural(n, 'fails', 'fail')} identically "
                    "without the change",
                    style="suf.faulty",
                ),
            )
        )
    for claim in it.blocked_claims if it else []:
        out.append(("producer says", Text(f"it could not {claim}", style="suf.insufficient")))
    if pending.kind is DecisionKind.approve_spec:
        out.append(
            (
                "specification",
                Text(
                    f"{len(run.spec.requirements)} requirements, "
                    f"{len(run.spec.verifications)} checks, "
                    f"{len(run.spec.gaps)} {plural(len(run.spec.gaps), 'gap')}",
                    style="h.value",
                ),
            )
        )
        for gap in run.spec.gaps:
            out.append(("gap", Text(gap, style="suf.insufficient")))
    if pending.kind is DecisionKind.budget and run.budget.max_cost_usd:
        out.append(
            (
                "spend",
                Text(
                    f"{run.consumption.cost_usd:.2f} of {run.budget.max_cost_usd:.2f} USD, basis "
                    f"{run.consumption.cost_basis.value}",
                    style="gauge.high",
                ),
            )
        )
    return out


def decision_question(run: Run, pending: PendingDecision) -> Question:
    """The question the run stopped on: one answer, and why when the answer needs a why."""
    options = tuple(Choice(o.key, o.label, o.consequence, o.needs_note) for o in pending.options)
    facts = decision_facts(run, pending)
    lead: RenderableType | None = None
    if facts:
        lead = Group(
            Text("what this rests on", style="h.key"),
            Padding(field_pairs(facts, width=14), (0, 0, 0, 2)),
        )

    def step(answers: Answers) -> Step | None:
        if "choice" not in answers:
            return Step("choice", pending.question, options=options)
        taken = next((o for o in pending.options if o.key == answers["choice"]), None)
        if taken is not None and taken.needs_note and "note" not in answers:
            return Step(
                "note",
                "why — this is what the decision will read as, later",
                hint="a sentence; it is kept with the run",
                required=True,
            )
        return None

    return Question(
        title="495 is waiting on you",
        glyph=ICON["question"],
        next=step,
        lead=lead,
    )


def ask_decision(console: Console, run: Run, pending: PendingDecision) -> tuple[str, str] | None:
    """The same question where there is no surface to draw it on. Deliberately blocking.

    The run is stopped until it is answered, and a dialog you could tab away from would be
    lying about that.
    """
    console.print(decision_panel(run, pending))
    answers = ask_in_prompt(console, decision_question(run, pending))
    if answers is None:
        return None
    choice = answers["choice"]
    option = next(o for o in pending.options if o.key == choice)
    console.print(
        Text.assemble(
            ("recorded ", "h.meta"),
            (choice, "h.ref.strong"),
            (f" — {option.consequence}" if option.consequence else "", "h.meta"),
        )
    )
    return choice, answers.get("note", "")
