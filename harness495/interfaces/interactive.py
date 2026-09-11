"""Interactive session: a small menu over the same engine, for use without memorising commands."""

from __future__ import annotations

import contextlib
import signal
from typing import TYPE_CHECKING, Any

from rich.prompt import Confirm, Prompt

from harness495 import __version__
from harness495.core.engine import Engine, EngineError
from harness495.core.models import RunMode
from harness495.core.report import render_markdown
from harness495.core.store import RunNotFound
from harness495.interfaces.render import (
    RunMonitor,
    console,
    decision_shows_requirements,
    print_decision,
    print_run_summary,
    prompt_decision,
)

if TYPE_CHECKING:
    from harness495.interfaces.cli import Ctx


def _engine(c: Ctx, monitor: RunMonitor | None = None) -> Engine:
    on_event = monitor.handle if monitor is not None else None
    return Engine(c.store, on_event=on_event, decision_handler=prompt_decision)


def _drive(c: Ctx, engine: Engine, run_id: str, monitor: RunMonitor) -> None:
    def handler(signum: int, frame: Any) -> None:
        engine.request_stop(run_id, "interrupted by user")
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGINT, handler)
    try:
        with monitor:
            run = engine.run(run_id)
    finally:
        signal.signal(signal.SIGINT, previous)
    pending = run.pending_decision
    # The decision lays the requirements out itself; printing them twice reads as two states.
    print_run_summary(run, c.store, with_requirements=not decision_shows_requirements(pending))
    if pending is not None:
        print_decision(pending, run)


def interactive_session(c: Ctx) -> None:
    console.print(f"[bold]495[/] {__version__}  project {c.project}  state {c.state_dir}")
    if not c.project.joinpath(".git").exists():
        console.print("[yellow]this directory is not a git repository; runs need one[/]")
    while True:
        console.print()
        console.print(
            "[bold]1[/] new change   [bold]2[/] evaluate existing change   [bold]3[/] list runs   [bold]4[/] resume / continue   [bold]5[/] status   [bold]6[/] report   [bold]7[/] doctor   [bold]q[/] quit"
        )
        choice = Prompt.ask(
            "action", choices=["1", "2", "3", "4", "5", "6", "7", "q"], default="3", console=console
        )
        try:
            if choice == "q":
                return
            if choice == "1":
                _new(c)
            elif choice == "2":
                _evaluate(c)
            elif choice == "3":
                _list(c)
            elif choice == "4":
                _resume(c)
            elif choice == "5":
                run = c.store.load(Prompt.ask("run id", console=console))
                print_run_summary(run, c.store)
                if run.pending_decision:
                    print_decision(run.pending_decision, run)
            elif choice == "6":
                run = c.store.load(Prompt.ask("run id", console=console))
                console.print(render_markdown(run, c.store))
            elif choice == "7":
                from harness495.interfaces.cli import app

                app(
                    ["--project", str(c.project), "--state-dir", str(c.state_dir), "doctor"],
                    standalone_mode=False,
                )
        except (EngineError, RunNotFound) as exc:
            console.print(f"[red]error:[/] {exc}")
        except KeyboardInterrupt:
            console.print("\n[yellow]interrupted[/]")


def _new(c: Ctx) -> None:
    intent = Prompt.ask("intent (what must the change accomplish?)", console=console)
    if not intent.strip():
        return
    config = c.config()
    agent = Prompt.ask(
        "agent for every role (name, or kind[:model])",
        default=config.roles.producer,
        console=console,
    )
    from harness495.interfaces.cli import _apply_overrides

    config = _apply_overrides(config, agent, None, None, None, None, None, None, False, None, None)
    max_cost = Prompt.ask(
        "cost limit in USD", default=str(config.budget.max_cost_usd), console=console
    )
    with contextlib.suppress(ValueError):
        config.budget.max_cost_usd = float(max_cost)
    monitor = RunMonitor()
    engine = _engine(c, monitor)
    run = engine.create_run(intent, c.project, config, RunMode.change, source="interactive")
    console.print(f"created run [bold]{run.id}[/]")
    if Confirm.ask("start now?", default=True, console=console):
        _drive(c, engine, run.id, monitor)


def _evaluate(c: Ctx) -> None:
    intent = Prompt.ask("what is the change supposed to accomplish?", console=console)
    ref = Prompt.ask(
        "commit to evaluate ('<ref>' or '<base>..<ref>'; empty = uncommitted working tree)",
        default="",
        console=console,
    )
    config = c.config()
    monitor = RunMonitor()
    engine = _engine(c, monitor)
    run = engine.create_run(
        intent,
        c.project,
        config,
        RunMode.evaluate,
        evaluate_ref=ref or "WORKTREE",
        source="interactive",
    )
    console.print(f"created run [bold]{run.id}[/]")
    _drive(c, engine, run.id, monitor)


def _list(c: Ctx) -> None:
    runs = c.store.list_runs()
    if not runs:
        console.print("no run yet")
        return
    for r in runs:
        outcome = r.result.outcome.value if r.result.outcome else "-"
        console.print(
            f"[bold]{r.id}[/]  {r.status.value:<18} {outcome:<12} it.{r.iteration_number}  {r.intent.text[:70]}"
        )


def _resume(c: Ctx) -> None:
    run_id = Prompt.ask("run id", console=console)
    run = c.store.load(run_id)
    monitor = RunMonitor()
    engine = _engine(c, monitor)
    if run.pending_decision is not None:
        answer = prompt_decision(run, run.pending_decision)
        if answer is None:
            return
        engine.decide(run_id, answer[0], answer[1])
    elif run.status.value in ("paused", "failed"):
        engine.resume(run_id)
    _drive(c, engine, run_id, monitor)
