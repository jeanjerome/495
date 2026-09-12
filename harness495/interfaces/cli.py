"""Command-line interface. Every command drives the same :class:`Engine`."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import sys
import time
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from harness495 import __version__
from harness495.core import git
from harness495.core.config import CONFIG_TEMPLATE, PROJECT_TEMPLATE, load_config
from harness495.core.engine import Engine, EngineError
from harness495.core.models import (
    AgentKind,
    AgentSpec,
    DecisionMaker,
    Event,
    HarnessConfig,
    PendingDecision,
    ReviewerSpec,
    Run,
    RunMode,
    Spec,
)
from harness495.core.profile import detect_profile
from harness495.core.report import render_markdown
from harness495.core.store import RunBusy, RunNotFound, RunStore, default_state_dir
from harness495.interfaces.render import (
    RunMonitor,
    console,
    decision_shows_requirements,
    print_decision,
    print_event,
    print_run_summary,
    print_spec,
    prompt_decision,
)

app = typer.Typer(
    name="495",
    help="495: an agentic engineering harness. Turns an intent into a verified, reviewed, traceable change.",
    no_args_is_help=False,
    add_completion=False,
    rich_markup_mode="markdown",
)

EXIT_AWAITING_DECISION = 3
EXIT_REJECTED = 4
EXIT_FAILED = 1


class Ctx:
    def __init__(self, project: Path, state_dir: Path | None, json_output: bool) -> None:
        self.project = project.resolve()
        self.state_dir = (state_dir or default_state_dir(self.project)).resolve()
        self.json = json_output
        self.store = RunStore(self.state_dir)
        self.monitor: RunMonitor | None = None

    def config(self) -> HarnessConfig:
        return load_config(self.project, self.state_dir)

    def engine(self, interactive: bool) -> Engine:
        self.monitor = None if self.json else RunMonitor()
        on_event = self.monitor.handle if self.monitor is not None else None
        handler = prompt_decision if interactive and not self.json and sys.stdin.isatty() else None
        return Engine(self.store, on_event=on_event, decision_handler=handler)

    def watching(self) -> AbstractContextManager[Any]:
        """Keep the phase and the spend on screen while the engine works."""
        return self.monitor if self.monitor is not None else contextlib.nullcontext()


def _ctx(ctx: typer.Context) -> Ctx:
    return ctx.obj  # type: ignore[no-any-return]


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    project: Path = typer.Option(
        Path.cwd(), "--project", "-C", help="Target project directory (a git repository)."
    ),
    state_dir: Path | None = typer.Option(
        None, "--state-dir", help="Where runs are stored (default: <project>/.495)."
    ),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output, no prompts."),
    version: bool = typer.Option(False, "--version", help="Print the version and exit."),
) -> None:
    if version:
        typer.echo(f"495 {__version__}")
        raise typer.Exit()
    ctx.obj = Ctx(project, state_dir, json_output)
    if ctx.invoked_subcommand is None:
        from harness495.interfaces.interactive import interactive_session

        interactive_session(ctx.obj)


# ---------------------------------------------------------------------- helpers


def _emit_json(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


def _run_payload(run: Run) -> dict[str, Any]:
    payload = {
        "id": run.id,
        "status": run.status.value,
        "mode": run.mode.value,
        "outcome": run.result.outcome.value if run.result.outcome else None,
        "summary": run.result.summary,
        "iteration": run.iteration_number,
        "pending_decision": run.pending_decision.model_dump(mode="json")
        if run.pending_decision
        else None,
        "cost_usd": run.consumption.cost_usd,
        "cost_basis": run.consumption.cost_basis.value,
        "tokens": run.consumption.usage.total_tokens,
        "interventions": run.consumption.interventions,
        "result": run.result.model_dump(mode="json"),
        "warnings": run.warnings,
        "stop_reason": run.stop_reason,
        "requirements": [
            {
                "id": r.id,
                "status": r.status.value,
                "statement": r.statement,
                "reason": r.status_reason,
            }
            for r in run.spec.requirements
        ],
    }
    return payload


def _finish(c: Ctx, run: Run) -> None:
    if c.json:
        _emit_json(_run_payload(run))
    else:
        pending = run.pending_decision
        print_run_summary(run, c.store, with_requirements=not decision_shows_requirements(pending))
        if pending is not None:
            print_decision(pending, run)
            console.print(
                f"Answer with: [bold]495 decide {run.id} <choice> [--note ...][/bold] then [bold]495 resume {run.id}[/bold]"
            )
    if run.status.value == "awaiting_decision":
        raise typer.Exit(EXIT_AWAITING_DECISION)
    if run.status.value in ("rejected", "aborted"):
        raise typer.Exit(EXIT_REJECTED)
    if run.status.value == "failed":
        raise typer.Exit(EXIT_FAILED)


def _advance(c: Ctx, engine: Engine, run_id: str) -> Run:
    """Walk the run to its next stop, or name whoever is already walking it.

    A run is claimed while it is advanced, so a second `495 run` — or the run surface in
    another terminal — is told where the run is being driven from instead of interleaving its
    writes with the ones happening there.
    """
    try:
        with c.watching():
            return engine.run(run_id)
    except RunBusy as exc:
        _error(c, str(exc))
        raise typer.Exit(EXIT_FAILED) from exc


def _apply_overrides(
    config: HarnessConfig,
    agent: str | None,
    producer: str | None,
    specifier: str | None,
    reviewers: list[str] | None,
    max_cost: float | None,
    max_iterations: int | None,
    timeout: int | None,
    auto_approve: bool,
    sandbox: str | None,
    allowed_paths: list[str] | None,
    allow_network: bool = False,
) -> HarnessConfig:
    if agent:
        spec = _agent_spec(config, agent)
        config.agents[spec.name] = spec
        config.roles.specifier = spec.name
        config.roles.producer = spec.name
        for r in config.roles.reviewers:
            r.agent = spec.name
    if producer:
        spec = _agent_spec(config, producer)
        config.agents[spec.name] = spec
        config.roles.producer = spec.name
    if specifier:
        spec = _agent_spec(config, specifier)
        config.agents[spec.name] = spec
        config.roles.specifier = spec.name
    if reviewers:
        new = []
        for item in reviewers:
            perspective, _, agent_ref = item.partition("=")
            spec = (
                _agent_spec(config, agent_ref) if agent_ref else config.agent(config.roles.producer)
            )
            config.agents[spec.name] = spec
            new.append(ReviewerSpec(perspective=perspective.strip(), agent=spec.name))
        config.roles.reviewers = new
    if max_cost is not None:
        config.budget.max_cost_usd = max_cost
    if max_iterations is not None:
        config.budget.max_iterations = max_iterations
    if timeout is not None:
        config.budget.intervention_timeout_s = timeout
    if auto_approve:
        config.auto_approve = True
    if sandbox:
        config.sandbox.backend = sandbox
    if allow_network:
        config.sandbox.allow_network = True
    if allowed_paths:
        config.project.scope.allowed_paths = list(allowed_paths)
    return config


def _agent_spec(config: HarnessConfig, ref: str) -> AgentSpec:
    """``name`` (from config), ``kind`` or ``kind:model`` (ad hoc)."""
    if ref in config.agents:
        return config.agents[ref]
    kind, _, model = ref.partition(":")
    if kind not in AgentKind.__members__:
        raise typer.BadParameter(
            f"unknown agent '{ref}'; use a configured name or kind[:model] with kind in {list(AgentKind.__members__)}"
        )
    return AgentSpec(name=ref, kind=AgentKind(kind), model=model or None)


def _load_spec_file(path: Path) -> Spec:
    data = json.loads(path.read_text(encoding="utf-8"))
    from harness495.core.engine import _spec_from_agent

    spec = _spec_from_agent(data)
    spec.source = "user"
    return spec


def _install_sigint(engine: Engine, run_id: str) -> None:
    def handler(signum: int, frame: Any) -> None:
        engine.request_stop(run_id, "interrupted by SIGINT")
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handler)


# ---------------------------------------------------------------------- commands


@app.command()
def init(
    ctx: typer.Context, force: bool = typer.Option(False, help="Overwrite existing files.")
) -> None:
    """Create `.495/config.toml` and `.495/project.toml` templates and show the detected profile."""
    c = _ctx(ctx)
    c.state_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, template in (("config.toml", CONFIG_TEMPLATE), ("project.toml", PROJECT_TEMPLATE)):
        p = c.state_dir / name
        if p.exists() and not force:
            continue
        p.write_text(template, encoding="utf-8")
        written.append(str(p))
    if git.is_repo(c.project):
        git.ensure_excluded(git.repo_root(c.project), ".495/")
    profile_cmd(ctx)
    if c.json:
        return
    for w in written:
        console.print(f"wrote {w}")


@app.command("profile")
def profile_cmd(ctx: typer.Context) -> None:
    """Detect the project's stack, verification commands and conventions (no agent involved)."""
    c = _ctx(ctx)
    prof = detect_profile(c.project, c.config().project)
    if c.json:
        _emit_json(prof.model_dump(mode="json"))
        return
    table = Table(title=f"Project profile: {prof.root}")
    table.add_column("name")
    table.add_column("kind")
    table.add_column("command")
    table.add_column("source")
    for cmd in prof.commands:
        table.add_row(cmd.name, cmd.kind.value, cmd.command, cmd.source)
    console.print(
        f"languages: {', '.join(prof.languages) or 'unknown'}; tooling: {', '.join(prof.tooling) or 'none'}"
    )
    console.print(
        f"base commit: {prof.base_commit or 'not a git repository'}; docs: {', '.join(prof.doc_files) or 'none'}"
    )
    console.print(table)


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Check agents, sandboxes and git availability without spending tokens."""
    c = _ctx(ctx)
    from harness495.agents.registry import build_agent
    from harness495.sandbox import DockerSandbox, Sandbox, SeatbeltSandbox, select_sandbox

    config = c.config()
    report: dict[str, Any] = {"agents": {}, "sandboxes": {}, "git": git.is_repo(c.project)}
    selected, warnings = select_sandbox(config.sandbox)
    for name, spec in config.agents.items():
        try:
            ok, detail = build_agent(spec, selected).check()
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, str(exc)
        report["agents"][name] = {
            "kind": spec.kind.value,
            "model": spec.model,
            "ok": ok,
            "detail": detail,
        }
    for sb in (SeatbeltSandbox(), DockerSandbox(config.sandbox.docker_image), Sandbox()):
        ok, detail = sb.available()
        report["sandboxes"][sb.name] = {"ok": ok, "detail": detail}
    report["selected_sandbox"] = selected.name
    report["warnings"] = warnings
    if c.json:
        _emit_json(report)
        return
    table = Table(title="495 doctor")
    table.add_column("component")
    table.add_column("ok")
    table.add_column("detail")
    for name, info in report["agents"].items():
        table.add_row(
            f"agent {name} ({info['kind']}{':' + info['model'] if info['model'] else ''})",
            "yes" if info["ok"] else "NO",
            info["detail"],
        )
    for name, info in report["sandboxes"].items():
        table.add_row(f"sandbox {name}", "yes" if info["ok"] else "NO", info["detail"])
    table.add_row("git repository", "yes" if report["git"] else "NO", str(c.project))
    table.add_row("selected sandbox", selected.name, "; ".join(warnings) or "")
    console.print(table)


@app.command()
def new(
    ctx: typer.Context,
    intent: str = typer.Argument(..., help="What the change must accomplish."),
    start: bool = typer.Option(True, "--start/--no-start", help="Start the run immediately."),
    spec_file: Path | None = typer.Option(
        None, "--spec", help="JSON specification to use instead of the specifier agent."
    ),
    agent: str | None = typer.Option(
        None, help="Agent for every role: name from config, or kind[:model]."
    ),
    producer: str | None = typer.Option(None, help="Agent for the producer role."),
    specifier: str | None = typer.Option(None, help="Agent for the specifier role."),
    reviewer: list[str] | None = typer.Option(
        None, help="perspective[=agent], repeatable; replaces configured reviewers."
    ),
    max_cost: float | None = typer.Option(None, help="Cost limit in USD."),
    max_iterations: int | None = typer.Option(None, help="Maximum production iterations."),
    timeout: int | None = typer.Option(None, help="Per-intervention timeout in seconds."),
    auto_approve: bool = typer.Option(
        False, "--auto-approve", help="Approve the specification automatically when it has no gap."
    ),
    sandbox: str | None = typer.Option(None, help="host | seatbelt | docker | auto"),
    allow_network: bool = typer.Option(
        False,
        "--allow-network",
        help="Let verification commands reach the network (builds that resolve dependencies).",
    ),
    allowed_path: list[str] | None = typer.Option(
        None, help="Glob the change may touch (repeatable)."
    ),
) -> None:
    """Create a run from an intent and (by default) start it."""
    c = _ctx(ctx)
    config = _apply_overrides(
        c.config(),
        agent,
        producer,
        specifier,
        reviewer,
        max_cost,
        max_iterations,
        timeout,
        auto_approve,
        sandbox,
        allowed_path,
        allow_network,
    )
    engine = c.engine(interactive=True)
    spec = _load_spec_file(spec_file) if spec_file else None
    try:
        run = engine.create_run(intent, c.project, config, RunMode.change, spec=spec, source="cli")
    except EngineError as exc:
        _error(c, str(exc))
        return
    if not start:
        if c.json:
            _emit_json(_run_payload(run))
        else:
            console.print(f"created run [bold]{run.id}[/bold]; start it with: 495 run {run.id}")
        return
    _install_sigint(engine, run.id)
    run = _advance(c, engine, run.id)
    _finish(c, run)


@app.command("eval")
def eval_cmd(
    ctx: typer.Context,
    intent: str = typer.Argument(..., help="What the existing change is supposed to accomplish."),
    ref: str | None = typer.Option(
        None, help="Commit to evaluate ('<ref>' against its parent, or '<base>..<ref>')."
    ),
    patch: Path | None = typer.Option(None, help="Patch file to evaluate on top of HEAD."),
    spec_file: Path | None = typer.Option(
        None, "--spec", help="JSON specification to use instead of the specifier agent."
    ),
    agent: str | None = typer.Option(
        None, help="Agent for the specifier and reviewers: name or kind[:model]."
    ),
    reviewer: list[str] | None = typer.Option(None, help="perspective[=agent], repeatable."),
    max_cost: float | None = typer.Option(None),
    timeout: int | None = typer.Option(None),
    auto_approve: bool = typer.Option(False, "--auto-approve"),
    sandbox: str | None = typer.Option(None),
    allow_network: bool = typer.Option(False, "--allow-network"),
    allowed_path: list[str] | None = typer.Option(None),
) -> None:
    """Evaluate an existing change (commit, patch, or the working tree) without a production agent."""
    c = _ctx(ctx)
    if ref and patch:
        raise typer.BadParameter("use either --ref or --patch")
    evaluate_ref = ref or (f"patch:{patch.resolve()}" if patch else "WORKTREE")
    config = _apply_overrides(
        c.config(),
        agent,
        None,
        None,
        reviewer,
        max_cost,
        None,
        timeout,
        auto_approve,
        sandbox,
        allowed_path,
        allow_network,
    )
    engine = c.engine(interactive=True)
    spec = _load_spec_file(spec_file) if spec_file else None
    try:
        run = engine.create_run(
            intent,
            c.project,
            config,
            RunMode.evaluate,
            evaluate_ref=evaluate_ref,
            spec=spec,
            source="cli",
        )
    except EngineError as exc:
        _error(c, str(exc))
        return
    _install_sigint(engine, run.id)
    run = _advance(c, engine, run.id)
    _finish(c, run)


@app.command("run")
def run_cmd(ctx: typer.Context, run_id: str) -> None:
    """Start or continue a run until it needs a decision or finishes."""
    c = _ctx(ctx)
    engine = c.engine(interactive=True)
    _install_sigint(engine, run_id)
    try:
        run = _advance(c, engine, run_id)
    except RunNotFound:
        _error(c, f"run {run_id} not found")
        return
    _finish(c, run)


@app.command()
def resume(ctx: typer.Context, run_id: str) -> None:
    """Resume a paused, failed or decided run."""
    c = _ctx(ctx)
    engine = c.engine(interactive=True)
    _install_sigint(engine, run_id)
    try:
        engine.resume(run_id)
        run = _advance(c, engine, run_id)
    except RunNotFound:
        _error(c, f"run {run_id} not found")
        return
    _finish(c, run)


@app.command()
def stop(
    ctx: typer.Context, run_id: str, reason: str = typer.Option("stop requested from the CLI")
) -> None:
    """Ask a running run (in another process) to pause at the next opportunity."""
    c = _ctx(ctx)
    if not c.store.exists(run_id):
        _error(c, f"run {run_id} not found")
        return
    c.store.request_stop(run_id, reason)
    if c.json:
        _emit_json({"id": run_id, "stop_requested": True})
    else:
        console.print(f"stop requested for {run_id}; the run will pause after the current step")


@app.command()
def decide(
    ctx: typer.Context,
    run_id: str,
    choice: str = typer.Argument(..., help="One of the option keys shown in the pending decision."),
    note: str = typer.Option("", help="Free-text note; required by some options."),
    resume_after: bool = typer.Option(
        True, "--resume/--no-resume", help="Continue the run right away."
    ),
) -> None:
    """Record a human decision on a run that is waiting for one."""
    c = _ctx(ctx)
    engine = c.engine(interactive=True)
    try:
        run = engine.decide(run_id, choice, note, DecisionMaker.human)
    except (EngineError, RunNotFound) as exc:
        _error(c, str(exc))
        return
    if resume_after and not run.is_blocked():
        _install_sigint(engine, run_id)
        run = _advance(c, engine, run_id)
    _finish(c, run)


@app.command()
def status(ctx: typer.Context, run_id: str) -> None:
    """Show the state of a run."""
    c = _ctx(ctx)
    try:
        run = c.store.load(run_id)
    except RunNotFound:
        _error(c, f"run {run_id} not found")
        return
    if c.json:
        _emit_json(_run_payload(run))
        return
    print_run_summary(run, c.store)
    if run.pending_decision:
        print_decision(run.pending_decision, run)


@app.command("list")
def list_cmd(ctx: typer.Context) -> None:
    """List runs in the state directory."""
    c = _ctx(ctx)
    runs = c.store.list_runs()
    if c.json:
        _emit_json([_run_payload(r) for r in runs])
        return
    table = Table(title=f"runs in {c.state_dir}")
    for col in ("id", "status", "mode", "outcome", "it.", "cost", "created", "intent"):
        table.add_column(col)
    for r in runs:
        table.add_row(
            r.id,
            r.status.value,
            r.mode.value,
            r.result.outcome.value if r.result.outcome else "",
            str(r.iteration_number),
            f"{r.consumption.cost_usd:.3f}" if r.consumption.cost_usd else "-",
            r.created_at.strftime("%Y-%m-%d %H:%M"),
            r.intent.text[:60].replace("\n", " "),
        )
    console.print(table)


@app.command()
def events(
    ctx: typer.Context,
    run_id: str,
    follow: bool = typer.Option(False, "--follow", "-f", help="Keep printing new events."),
) -> None:
    """Print the event log of a run (JSON lines with --json)."""
    c = _ctx(ctx)
    if not c.store.exists(run_id):
        _error(c, f"run {run_id} not found")
        return
    offset = 0
    while True:
        for ev in c.store.events(run_id, offset):
            offset += 1
            if c.json:
                typer.echo(ev.model_dump_json())
            else:
                print_event(ev)
        if not follow:
            break
        try:
            run = c.store.load(run_id)
        except RunNotFound:
            break
        if run.is_blocked():
            break
        time.sleep(1.0)


@app.command()
def report(
    ctx: typer.Context,
    run_id: str,
    fmt: str = typer.Option("md", "--format", help="md | json"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write to a file instead of stdout."
    ),
) -> None:
    """Render the restitution of a run."""
    c = _ctx(ctx)
    try:
        run = c.store.load(run_id)
    except RunNotFound:
        _error(c, f"run {run_id} not found")
        return
    text = run.model_dump_json(indent=2) if fmt == "json" else render_markdown(run, c.store)
    if output:
        output.write_text(text, encoding="utf-8")
        if not c.json:
            console.print(f"wrote {output}")
    else:
        typer.echo(text)


@app.command()
def spec(ctx: typer.Context, run_id: str) -> None:
    """Show the run's specification: what the change must accomplish and how it is checked."""
    c = _ctx(ctx)
    try:
        run = c.store.load(run_id)
    except RunNotFound:
        _error(c, f"run {run_id} not found")
        return
    if c.json:
        _emit_json(run.spec.model_dump(mode="json"))
        return
    print_spec(run.spec)
    if run.spec.artifact_ref:
        console.print(f"saved at {c.store.resolve(run.id, run.spec.artifact_ref)}")
    state = "approved" if run.spec.approved else "not approved"
    console.print(
        f"{state}" + (f" by {run.spec.approved_by.value}" if run.spec.approved_by else "")
    )


@app.command("check-integration")
def check_integration(
    ctx: typer.Context,
    run_id: str,
    ref: str = typer.Option("HEAD", help="Ref of the integrated tree to check."),
    rerun: bool = typer.Option(
        False, "--rerun", help="Re-run the verification commands on the integrated ref."
    ),
) -> None:
    """After you integrated the change, verify that the integrated tree matches the evaluated version."""
    c = _ctx(ctx)
    engine = c.engine(interactive=False)
    try:
        run = engine.check_integration(run_id, ref, rerun)
    except (EngineError, RunBusy, RunNotFound, git.GitError) as exc:
        _error(c, str(exc))
        return
    ic = run.result.integration
    assert ic is not None
    if c.json:
        _emit_json(ic.model_dump(mode="json"))
    else:
        ok = ic.contains_commit or ic.files_identical
        console.print(
            f"[{'green' if ok else 'red'}]integration {'verified' if ok else 'MISMATCH'}[/]: {ic.detail}"
        )
    if not (ic.contains_commit or ic.files_identical) or ic.verifications_passed is False:
        raise typer.Exit(EXIT_REJECTED)


@app.command()
def export(
    ctx: typer.Context, run_id: str, output: Path | None = typer.Option(None, "-o", "--output")
) -> None:
    """Archive a run directory (state, prompts, transcripts, evidence, report) as a tar.gz."""
    c = _ctx(ctx)
    dest = output or Path.cwd() / f"{run_id}.tar.gz"
    try:
        c.store.export(run_id, dest)
    except RunNotFound:
        _error(c, f"run {run_id} not found")
        return
    if c.json:
        _emit_json({"id": run_id, "archive": str(dest)})
    else:
        console.print(f"exported {run_id} to {dest}")


@app.command()
def cleanup(
    ctx: typer.Context,
    run_id: str,
    delete: bool = typer.Option(False, help="Also delete the run state."),
) -> None:
    """Remove the run's git worktree (the branch is kept); optionally delete the run state."""
    c = _ctx(ctx)
    engine = c.engine(interactive=False)
    try:
        engine.cleanup_worktree(run_id)
    except RunNotFound:
        _error(c, f"run {run_id} not found")
        return
    if delete:
        c.store.delete(run_id)
    if c.json:
        _emit_json({"id": run_id, "worktree_removed": True, "deleted": delete})
    else:
        console.print(f"worktree of {run_id} removed" + (", state deleted" if delete else ""))


@app.command()
def watch(
    ctx: typer.Context,
    run_id: str | None = typer.Argument(None, help="Run to open; omitted, the listing opens."),
    stage: str | None = typer.Option(
        None,
        "--stage",
        help="Open on one stop: profile, spec, change, checks, review, verdict, deliver, "
        "integration, log, runs.",
    ),
    once: bool = typer.Option(False, "--print", help="Render the view once and exit."),
    export: Path | None = typer.Option(None, "--export", help="Write the view to an SVG file."),
    width: int | None = typer.Option(None, "--width", help="Force a render width."),
    read_only: bool = typer.Option(
        False, "--read-only", help="Show the surface without its controls; nothing can be driven."
    ),
    ascii_icons: bool = typer.Option(
        False, "--ascii-icons", help="Panel titles with geometric marks instead of emoji."
    ),
) -> None:
    """Open the run surface: the pipeline, what each stage produced, and the controls.

    The eight stops of the workflow, each showing what that stage produced and carrying what
    acts on it: `c` opens a run from an intent, `s` advances it, `p` pauses it, `d` answers the
    question it stopped on, `i` checks what you merged.

    A run is claimed while it is being advanced, so a surface opened on a run another terminal
    is driving watches it instead of joining in — both are looking at the same files.
    """
    from harness495.interfaces.tui import build_console
    from harness495.interfaces.tui import watch as watch_runs
    from harness495.interfaces.tui.icons import use_icons

    c = _ctx(ctx)
    if c.json:
        _error(c, "the run surface has no machine-readable form; use status, list or events")
        return
    if ascii_icons:
        use_icons("ascii")
    code = watch_runs(
        c.store,
        run_id=run_id,
        stage=stage,
        console=build_console(width, record=export is not None),
        once=once,
        export=export,
        project=c.project,
        read_only=read_only,
    )
    if code:
        raise typer.Exit(code)


@app.command()
def schema(
    ctx: typer.Context, name: str = typer.Argument("run", help="run | event | spec | config")
) -> None:
    """Print the JSON schema of the persisted documents."""
    from harness495.core.models import Event as EventModel

    models: dict[str, type[BaseModel]] = {
        "run": Run,
        "event": EventModel,
        "spec": Spec,
        "config": HarnessConfig,
    }
    if name not in models:
        raise typer.BadParameter(f"unknown schema '{name}'; choose from {list(models)}")
    typer.echo(json.dumps(models[name].model_json_schema(), indent=2))


@app.command()
def validate(ctx: typer.Context, path: Path) -> None:
    """Validate a run.json document against the schema."""
    c = _ctx(ctx)
    try:
        run = Run.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _error(c, f"invalid: {exc}")
        return
    if c.json:
        _emit_json({"valid": True, "id": run.id, "status": run.status.value})
    else:
        console.print(f"[green]valid[/] run {run.id} ({run.status.value})")


@app.command()
def serve(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(4950),
) -> None:
    """Expose the same workflow over an HTTP JSON API."""
    from harness495.interfaces.api import serve as serve_api

    c = _ctx(ctx)
    serve_api(c.project, c.state_dir, host, port)


def _error(c: Ctx, message: str) -> None:
    if c.json:
        _emit_json({"error": message})
    else:
        console.print(f"[red]error:[/] {message}")
    raise typer.Exit(EXIT_FAILED)


def main() -> None:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    app()


__all__ = ["app", "main", "Ctx", "Event", "PendingDecision", "Console"]
