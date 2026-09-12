"""The two ways the shell is driven: keys on a terminal, prompts without one.

Both paths reach the same :meth:`Shell.act`, and both take the same controls. What differs is
only how the surface asks: a terminal polls for a key while a thread advances the run, a piped
session asks in words and waits for the work to finish before printing the next view.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator

from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.syntax import Syntax
from rich.text import Text

from harness495.core.engine import EngineError
from harness495.core.models import Event, RunStatus
from harness495.core.store import RunBusy, RunNotFound
from harness495.interfaces.tui.keys import KeyReader
from harness495.interfaces.tui.shell import Shell
from harness495.interfaces.tui.stages import STAGE_BY_KEY, STAGES, stage_of
from harness495.interfaces.tui.theme import EVENT_STYLE
from harness495.interfaces.tui.views import ask_decision, ask_intent
from harness495.interfaces.tui.widgets import clip, short

REFRESH = 10.0
"""Frames per second. The mark dissolves a digit every 0.12s, so below about eight the
animation reads as a stutter rather than a pulse; above it the screen costs more than it says."""

#: Everything a control can raise once the surface stops only reading.
CONTROL_ERRORS = (EngineError, RunBusy, RunNotFound, RuntimeError, OSError)


def run_interactive(shell: Shell, reader: KeyReader, refresh: float = REFRESH) -> None:
    """Redraw on a clock, act on a key, never block on either."""
    size = shell.console.size
    with Live(
        shell.screen(size.width, size.height),
        console=shell.console,
        screen=True,
        refresh_per_second=refresh,
        vertical_overflow="crop",
    ) as live:
        try:
            while shell.running:
                key = reader.poll(timeout=1 / refresh)
                if key is not None:
                    action = shell.resolve(key)
                    if action in INLINE:
                        shell.driver.notice = None
                        if shell.can(action):
                            INLINE[action](shell, reader, live)
                        else:
                            shell.driver.notice = shell.refusal(action)
                    elif action == "open" and shell.view == "checks":
                        _page_log(shell, reader, live)
                    elif action:
                        shell.act(action)
                if not shell.paused:
                    shell.source.refresh()
                if not shell.paused or key is not None:
                    size = shell.console.size
                    live.update(shell.screen(size.width, size.height))
        except KeyboardInterrupt:
            shell.running = False
        finally:
            _wind_down(shell, live)


def _wind_down(shell: Shell, live: Live | None, timeout: float = 30.0) -> None:
    """Never leave a run mid-intervention: the engine advancing it lives in this process.

    The worker is a daemon thread, so quitting would take the agent down with it and leave the
    run at a phase entered but never left — a state no command knows how to resume. Asking it
    to stop instead kills the agent and pauses the run where it was, which ``s`` here and
    ``495 resume`` elsewhere both continue from.
    """
    work = shell.driver.working()
    if work is None:
        return
    if live is not None:
        live.stop()
    shell.console.print(
        Text(f"pausing {work.run_id} before leaving; the agent is being stopped", style="attn.you")
    )
    if work.interruptible:
        shell.driver.pause(work.run_id)
    wait = getattr(shell.driver, "wait", None)
    if callable(wait) and not wait(timeout):
        shell.console.print(
            Text(
                f"it has not settled after {timeout:.0f}s — 495 resume {work.run_id} continues it",
                style="gauge.warn",
            )
        )


@contextlib.contextmanager
def _off_screen(shell: Shell, reader: KeyReader, live: Live | None) -> Iterator[None]:
    """Take the screen down for a question, then give it back.

    A live region redraws over the last line, the prompt included, so a question asked
    underneath one is invisible and every answer typed into it is lost.
    """
    if live is not None:
        live.stop()
    try:
        with reader.released():
            yield
    finally:
        if live is not None:
            live.start(refresh=True)


def _back(console: Console) -> None:
    Prompt.ask("press enter to go back", default="", console=console, show_default=False)


def _decide_inline(shell: Shell, reader: KeyReader, live: Live | None) -> None:
    """Answer the question the run is stopped on, and let it carry on.

    Answering and continuing are one act: the run stopped to ask, and the answer is what it was
    waiting for. Recording it and then leaving the run standing would turn one decision into
    two things to remember.
    """
    run = shell.run
    pending = run.pending_decision
    if pending is None:
        return
    with _off_screen(shell, reader, live):
        answer = ask_decision(shell.console, run, pending)
        if answer is not None:
            try:
                shell.driver.decide(run.id, answer[0], answer[1])
            except CONTROL_ERRORS as exc:
                shell.console.print(f"[attn.dead]could not record it:[/] {exc}")
            else:
                shell.source.refresh(force=True)
                shell.view = stage_of(shell.run)
        _back(shell.console)


def _create_inline(shell: Shell, reader: KeyReader, live: Live | None) -> None:
    """Take an intent — or an existing change — and open the run it starts."""
    if not shell.driver.creates():
        shell.driver.notice = "this surface has no project to create a run in"
        return
    with _off_screen(shell, reader, live):
        console = shell.console
        answer = ask_intent(console)
        if answer is None:
            return
        intent, ref = answer
        try:
            run_id = shell.driver.create(intent, ref)
        except CONTROL_ERRORS as exc:
            console.print(f"[attn.dead]could not create it:[/] {exc}")
            _back(console)
            return
        shell.source.refresh(force=True)
        with contextlib.suppress(LookupError):
            shell.select(run_id)
        shell.view = stage_of(shell.run)
        console.print(Text(f"run {run_id} created and started", style="attn.done"))


def _integrate_inline(shell: Shell, reader: KeyReader, live: Live | None) -> None:
    """Ask which ref you merged into, then have the harness recognise it — or not."""
    run = shell.run
    if not run.result.report_ref:
        shell.driver.notice = "nothing has been delivered, so there is nothing to recognise"
        return
    it = run.current_iteration
    head = it.version.head_commit if it and it.version else ""
    with _off_screen(shell, reader, live):
        console = shell.console
        console.print(
            Text(
                f"495 looks for {short(head, 12)} — and for the exact content of the files it "
                "changed — in the ref you name.",
                style="h.value",
            )
        )
        ref = Prompt.ask("ref you integrated into", default="HEAD", console=console)
        rerun = Confirm.ask(
            "re-run the verification commands there?", default=False, console=console
        )
        try:
            shell.driver.integrate(run.id, ref, rerun)
        except CONTROL_ERRORS as exc:
            console.print(f"[attn.dead]could not check it:[/] {exc}")
            _back(console)


#: Actions that need the screen: they ask a question, and a question asked under a live region
#: is invisible.
INLINE: dict[str, Callable[[Shell, KeyReader, Live | None], None]] = {
    "decide": _decide_inline,
    "create": _create_inline,
    "integrate": _integrate_inline,
}
INLINE_BY_KEY = {"d": "decide", "c": "create", "i": "integrate"}


def _page_log(shell: Shell, reader: KeyReader, live: Live | None) -> None:
    """A full command log is longer than any panel, so it gets the screen.

    ``Console.pager`` hands the text to the user's PAGER, which already knows how to search and
    scroll it. Re-implementing that inside a Rich panel would be a worse ``less``.
    """
    vs = shell.run.spec.verifications
    if not vs:
        return
    vid = vs[min(shell.cursor, len(vs) - 1)].id
    logs = shell.source.logs(shell.run.id)
    records = [e for e in shell.run.evidence if e.verification_id == vid]
    text = (
        "\n\n".join(
            f"# {e.id}  {e.kind.value}  on {short(e.subject_version)}  exit {e.exit_code}\n"
            f"{logs.get(e) or e.summary}"
            for e in records
        )
        or f"no output recorded for {vid}"
    )
    if live is not None:
        live.stop()
    try:
        with reader.released(), shell.console.pager(styles=True):
            shell.console.print(
                Syntax(
                    text, "console", theme="ansi_dark", background_color="default", word_wrap=True
                )
            )
    finally:
        if live is not None:
            live.start(refresh=True)


def echo_events(console: Console) -> Callable[[Event], None]:
    """An event printer for a session that has no screen to redraw.

    Without a terminal the run still has to be visible while it works, and the surface only
    prints between questions. The engine's own events are what fill that silence.
    """

    def echo(ev: Event) -> None:
        console.print(
            Text.assemble(
                (ev.ts.astimezone().strftime("%H:%M:%S "), "h.meta"),
                (f"{ev.type:<22}", EVENT_STYLE.get(ev.type, "h.meta")),
                (" " + clip(ev.message, 160), "h.value"),
            )
        )

    return echo


def run_prompted(shell: Shell) -> None:
    """The same shell without a tty: print the view, ask what to do next, repeat.

    This is the path a piped session or CI takes. Nothing is hidden from it, controls included;
    it just cannot poll for keys, so it asks — and it asks with the same vocabulary the
    keyboard uses. Work started here is waited for rather than watched, since there is no clock
    to redraw on: the run's own events are echoed while it goes.
    """
    console = shell.console
    while shell.running:
        shell.source.refresh()
        console.print(shell.flow(console.width))
        run = shell.run
        pending = run.pending_decision
        if pending is not None and shell.can("decide"):
            answer = ask_decision(console, run, pending)
            if answer is None:
                shell.running = False
                continue
            try:
                shell.driver.decide(run.id, answer[0], answer[1])
            except CONTROL_ERRORS as exc:
                console.print(f"[attn.dead]could not record it:[/] {exc}")
                shell.running = False
                continue
            _settle(shell)
            continue
        controls = shell.controls()
        offered = "".join(f"{key} {label}, " for key, label in controls)
        if shell.opened:
            choices = [s.key for s in STAGES] + [k for k, _ in controls] + ["g", "l", "o", "?", "q"]
            question = (
                f"{offered}stage (1-{len(STAGES)}), g log, l runs, o open a run, ? help, q quit"
            )
        else:
            # The listing, with nothing open: a stage, a log and a control all name a run, and
            # asking for one before a run is picked is the terminal's way of offering a key
            # that does nothing.
            choices = [k for k, _ in controls] + ["o", "?", "q"]
            question = f"{offered}o open a run, ? help, q quit"
        key = Prompt.ask(
            question, choices=choices, default="q", console=console, show_choices=False
        )
        if key == "o":
            index = IntPrompt.ask(
                f"run number (1-{len(shell.runs)})", default=shell.selected + 1, console=console
            )
            # Through ``select``, which is the one place a run is opened: setting the index
            # alone would leave the surface showing a run it does not consider open.
            shell.select(shell.runs[max(1, min(len(shell.runs), index)) - 1].id)
            shell.view = stage_of(shell.run)
        elif key == "s":
            shell.act("control:start")
            _settle(shell)
        elif key == "p":
            shell.act("control:pause")
        elif key in ("c", "i") and shell.can(INLINE_BY_KEY[key]):
            INLINE[INLINE_BY_KEY[key]](shell, KeyReader(), None)
            _settle(shell)
        elif key in STAGE_BY_KEY:
            shell.act(f"stage:{STAGE_BY_KEY[key]}")
        elif key in ("g", "l"):
            shell.act("view:" + ("log" if key == "g" else "runs"))
        elif key == "?":
            shell.act("help")
        else:
            shell.running = False


def _settle(shell: Shell) -> None:
    """Wait for whatever was just started, then read the run back.

    A prompted session has no clock: the next thing it prints has to be the state the work left
    behind, not the state it started from.
    """
    wait = getattr(shell.driver, "wait", None)
    if callable(wait):
        wait()
    shell.source.refresh(force=True)
    if shell.run.status is not RunStatus.delivered:
        shell.view = stage_of(shell.run)
