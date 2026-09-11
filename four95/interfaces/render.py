"""Terminal rendering shared by the CLI and the interactive session."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from four95.core.models import (
    DecisionKind,
    Event,
    PendingDecision,
    RequirementStatus,
    Run,
    Spec,
)

if TYPE_CHECKING:
    from four95.core.store import RunStore

console = Console(highlight=False)

EVENT_STYLE = {
    "warning": "yellow",
    "run.failed": "red bold",
    "run.aborted": "red",
    "run.delivered": "green bold",
    "decision.requested": "magenta bold",
    "iteration.assessed": "cyan",
    "evidence": "blue",
    "review": "cyan",
    "intervention.started": "white",
    "intervention.ended": "white",
    "status": "dim",
}


def print_event(ev: Event) -> None:
    style = EVENT_STYLE.get(ev.type, "")
    ts = ev.ts.astimezone().strftime("%H:%M:%S")
    text = (
        f"[dim]{ts}[/] [{style}]{ev.type:<22}[/] {ev.message}"
        if style
        else f"[dim]{ts}[/] {ev.type:<22} {ev.message}"
    )
    console.print(text)


STATUS_COLOUR = {
    RequirementStatus.satisfied: "green",
    RequirementStatus.violated: "red",
    RequirementStatus.undetermined: "yellow",
    RequirementStatus.pending: "dim",
}


def _clip(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + " […]"


def print_spec(spec: Spec) -> None:
    """The specification as it stands, for someone about to approve or refuse it.

    Statements are shown whole: approving a requirement you have only seen half of is the thing
    this is meant to prevent. Descriptions of verifications are clipped instead, because they
    restate at length what the command already says, and the artifact holds the full text.
    """
    requirements = Table(title="requirements", show_lines=True, title_justify="left")
    requirements.add_column("req", style="bold", no_wrap=True)
    requirements.add_column("what must hold after the change", overflow="fold")
    requirements.add_column("checked by", no_wrap=True)
    for r in spec.requirements:
        requirements.add_row(r.id, r.statement, ", ".join(r.verification_ids) or "[red]nothing[/]")
    console.print(requirements)

    console.print("\n[bold]verifications[/]")
    for v in spec.verifications:
        colour = "green" if v.sufficiency.value == "sufficient" else "yellow"
        flag = ", to create" if v.to_create else ""
        console.print(
            f"  [bold]{v.id}[/] ({v.kind.value}{flag}) [{colour}]{v.sufficiency.value}[/]"
            + (f" — {v.rationale}" if v.rationale else "")
        )
        console.print(f"    [cyan]{v.command}[/]" if v.command else "    [red]no command[/]")
        if v.description:
            console.print(f"    [dim]{_clip(v.description)}[/]")

    for title, items in (
        ("allowed paths", spec.allowed_paths),
        ("out of scope", spec.out_of_scope),
        ("assumptions", spec.assumptions),
    ):
        if items:
            console.print(f"\n[bold]{title}[/]")
            for item in items:
                console.print(f"  - {_clip(item)}")
    if spec.gaps:
        console.print("\n[yellow]verification gaps[/]")
        for gap in spec.gaps:
            console.print(f"  [yellow]- {gap}[/]")


NEEDS_REQUIREMENTS = frozenset(
    {
        DecisionKind.undetermined,
        DecisionKind.iteration_limit,
        DecisionKind.instrument_fault,
        DecisionKind.no_progress,
    }
)


def print_requirement_status(run: Run) -> None:
    table = Table(title="where each requirement stands", show_lines=True, title_justify="left")
    table.add_column("req", style="bold", no_wrap=True)
    table.add_column("status", no_wrap=True)
    table.add_column("statement", overflow="fold")
    table.add_column("why", overflow="fold")
    for r in run.spec.requirements:
        table.add_row(
            r.id,
            f"[{STATUS_COLOUR[r.status]}]{r.status.value}[/]",
            _clip(r.statement, 160),
            _clip(r.status_reason, 220),
        )
    console.print(table)


def print_decision_detail(pending: PendingDecision, run: Run) -> None:
    """The facts behind the question, laid out, so the question itself can stay one sentence."""
    if pending.kind is DecisionKind.approve_spec:
        print_spec(run.spec)
        return
    if pending.kind not in NEEDS_REQUIREMENTS:
        return
    if run.spec.requirements:
        print_requirement_status(run)
    faults = pending.context.get("faults") or []
    if faults:
        console.print("\n[yellow]verifications that cannot see the change[/]")
        for f in faults:
            console.print(f"  [yellow]- {f}[/]")
    it = run.current_iteration
    if it and it.correction_requests:
        console.print("\n[bold]outstanding corrections[/]")
        for c in it.correction_requests:
            console.print(f"  - {_clip(c, 300)}")
    claims = (it.blocked_claims if it else []) or pending.context.get("blocked_claims") or []
    if claims:
        console.print(
            "\n[bold]reported by the producer as not done[/] [dim](its claim, unverified)[/]"
        )
        for c in claims:
            console.print(f"  - {_clip(c, 400)}")


def print_decision(pending: PendingDecision, run: Run | None = None) -> None:
    if run is not None:
        print_decision_detail(pending, run)
    lines = [pending.question, ""]
    for o in pending.options:
        note = " [dim](a note is required)[/]" if o.needs_note else ""
        lines.append(f"  [bold]{o.key}[/]: {o.label}{note}")
        if o.consequence:
            lines.append(f"      [dim]{o.consequence}[/]")
    console.print(
        Panel(
            "\n".join(lines), title=f"decision needed: {pending.kind.value}", border_style="magenta"
        )
    )


@contextmanager
def paused_display() -> Iterator[None]:
    """Suspend the run's status line, if one is up, for the duration of the block."""
    if _ACTIVE_MONITOR is None:
        yield
        return
    with _ACTIVE_MONITOR.paused():
        yield


def prompt_decision(run: Run, pending: PendingDecision) -> tuple[str, str] | None:
    with paused_display():
        print_decision(pending, run)
        keys = [o.key for o in pending.options]
        choice = Prompt.ask("choice", choices=keys, console=console)
        option = next(o for o in pending.options if o.key == choice)
        note = ""
        if option.needs_note:
            while not note.strip():
                note = Prompt.ask("note", console=console)
        return choice, note


def print_run_summary(
    run: Run, store: RunStore | None = None, with_requirements: bool = True
) -> None:
    outcome = run.result.outcome.value if run.result.outcome else "-"
    c = run.consumption
    cost = (
        "unknown"
        if c.cost_basis.value == "unknown" and not c.cost_usd
        else f"{c.cost_usd:.4f} USD ({c.cost_basis.value})"
    )
    header = (
        f"[bold]{run.id}[/]  status [bold]{run.status.value}[/]  outcome [bold]{outcome}[/]  "
        f"iteration {run.iteration_number}  interventions {c.interventions}  tokens {c.usage.total_tokens}  cost {cost}"
    )
    console.print(Panel(header, title="495 run", border_style="blue"))
    if run.spec.requirements and with_requirements:
        table = Table(show_lines=False)
        table.add_column("req", style="bold")
        table.add_column("status")
        table.add_column("statement")
        table.add_column("reason", overflow="fold")
        for r in run.spec.requirements:
            table.add_row(
                r.id,
                f"[{STATUS_COLOUR[r.status]}]{r.status.value}[/]",
                r.statement,
                r.status_reason,
            )
        console.print(table)
    if run.spec.gaps:
        console.print("[yellow]verification gaps:[/] " + "; ".join(run.spec.gaps))
    if run.result.summary:
        console.print(run.result.summary)
    it = run.current_iteration
    if it and it.version and it.version.head_commit:
        console.print(
            f"version: branch {it.version.branch} at {it.version.head_commit[:12]}, patch {it.version.patch_ref or 'none'}"
        )
    if run.result.report_ref and store is not None:
        console.print(f"report: {store.resolve(run.id, run.result.report_ref)}")
    if run.stop_reason:
        console.print(f"[red]stopped:[/] {run.stop_reason}")
    for w in run.warnings[-5:]:
        console.print(f"[yellow]warning:[/] {w}")


# --------------------------------------------------------------------------- live monitor

_ACTIVE_MONITOR: RunMonitor | None = None

PHASE_LABEL = {
    "created": "starting up",
    "profiled": "profiled",
    "specified": "specified",
    "ready": "ready to produce",
    "producing": "producing the change",
    "produced": "change produced",
    "verifying": "running the verifications",
    "verified": "verifications done",
    "reviewing": "reviewing",
    "reviewed": "weighing the evidence",
    "awaiting_decision": "waiting for you",
    "accepted": "accepted",
    "rejected": "rejected",
    "undetermined": "cannot conclude",
    "delivered": "delivered",
    "paused": "paused",
    "aborted": "aborted",
    "failed": "failed",
}

# The phase is on the status bar at all times, so the transitions themselves are noise.
HIDDEN_EVENTS = frozenset({"status"})


def _gauge(fraction: float, width: int = 12) -> str:
    filled = max(0, min(width, round(fraction * width)))
    colour = "red" if fraction >= 0.9 else "yellow" if fraction >= 0.7 else "green"
    return f"[{colour}]{'█' * filled}{'░' * (width - filled)}[/]"


class RunMonitor:
    """Streams events while keeping where-we-are and what-it-costs pinned to the bottom.

    Without it the phase is something you reconstruct by reading backwards through the log, and
    the cost is only known once the run is over.
    """

    def __init__(self, console_: Console | None = None) -> None:
        self.console = console_ or console
        self.phase = "created"
        self.iteration = 0
        self.max_iterations = 0
        self.activity = ""
        self.cost = 0.0
        self.max_cost: float | None = None
        self.tokens = 0
        self.interventions = 0
        self.started = time.monotonic()
        self._live: Live | None = None

    # ---- state

    def observe(self, ev: Event) -> None:
        data = ev.data or {}
        if ev.type == "status":
            self.phase = str(data.get("to") or self.phase)
        elif ev.type == "iteration.started":
            self.iteration = int(data.get("n") or self.iteration)
            self.max_iterations = int(data.get("max") or self.max_iterations)
        elif ev.type == "intervention.started":
            self.activity = ev.message
        elif ev.type == "intervention.ended":
            self.activity = ""
            c = data.get("consumption") or {}
            self.cost = float(c.get("cost_usd") or self.cost)
            self.tokens = int(c.get("tokens") or self.tokens)
            self.interventions = int(c.get("interventions") or self.interventions)
            if c.get("max_cost_usd") is not None:
                self.max_cost = float(c["max_cost_usd"])
        elif ev.type == "verification.started":
            self.activity = f"running {data.get('verification') or 'a verification'}"
        elif ev.type == "control.started":
            self.activity = (
                f"checking {data.get('verification') or 'a verification'} without the change"
            )

    def bar(self) -> Text | str:
        elapsed = int(time.monotonic() - self.started)
        parts = [f"[bold]{PHASE_LABEL.get(self.phase, self.phase)}[/]"]
        if self.iteration:
            of = f"/{self.max_iterations}" if self.max_iterations else ""
            parts.append(f"iteration {self.iteration}{of}")
        if self.activity:
            parts.append(f"[dim]{_clip(self.activity, 60)}[/]")
        spend = f"{self.cost:.2f}"
        if self.max_cost:
            spend = f"{_gauge(self.cost / self.max_cost)} {self.cost:.2f}/{self.max_cost:.2f} USD"
        else:
            spend += " USD"
        parts.append(spend)
        parts.append(
            f"{self.tokens / 1e6:.1f}M tok" if self.tokens >= 1e6 else f"{self.tokens} tok"
        )
        parts.append(f"{self.interventions} agent run(s)")
        parts.append(f"{elapsed // 60:d}m{elapsed % 60:02d}s")
        return Text.from_markup("  ·  ".join(parts), style="on grey15")

    # ---- lifecycle

    def __enter__(self) -> RunMonitor:
        global _ACTIVE_MONITOR
        if self.console.is_terminal:
            self._live = Live(
                self.bar(), console=self.console, refresh_per_second=4, transient=True
            )
            self._live.__enter__()
        _ACTIVE_MONITOR = self
        return self

    def __exit__(self, *exc: object) -> None:
        global _ACTIVE_MONITOR
        _ACTIVE_MONITOR = None
        if self._live is not None:
            self._live.__exit__(None, None, None)
            self._live = None
            self.console.print(self.bar())

    @contextmanager
    def paused(self) -> Iterator[None]:
        """Take the status line down while something else owns the terminal.

        A live region redraws over whatever is on the last line, the prompt included, so a
        question asked underneath one is invisible and every answer typed into it is lost.
        """
        live = self._live
        if live is None or not live.is_started:
            yield
            return
        live.stop()
        try:
            yield
        finally:
            live.start(refresh=True)

    def handle(self, ev: Event) -> None:
        self.observe(ev)
        if ev.type not in HIDDEN_EVENTS:
            print_event(ev)
        if self._live is not None:
            self._live.update(self.bar())


def decision_shows_requirements(pending: PendingDecision | None) -> bool:
    return pending is not None and pending.kind in NEEDS_REQUIREMENTS
