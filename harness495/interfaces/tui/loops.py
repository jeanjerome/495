"""The two ways the shell is driven: keys on a terminal, prompts without one.

Both paths reach the same :meth:`Shell.act`, and both take the same controls. What differs is
only how the surface asks: a terminal polls for a key while a thread advances the run, a piped
session asks in words and waits for the work to finish before printing the next view.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.prompt import IntPrompt, Prompt
from rich.syntax import Syntax
from rich.text import Text

from harness495.core import git
from harness495.core.engine import EngineError
from harness495.core.models import Event, RunStatus
from harness495.core.store import RunBusy, RunNotFound
from harness495.interfaces.tui.asking import Answers, Ask, ask_in_prompt
from harness495.interfaces.tui.keys import KeyReader
from harness495.interfaces.tui.shell import Shell
from harness495.interfaces.tui.stages import STAGE_BY_KEY, STAGES, stage_of
from harness495.interfaces.tui.theme import EVENT_STYLE
from harness495.interfaces.tui.views import (
    ask_decision,
    decision_question,
    integration_question,
    intent_question,
    intent_taken,
    merge_question,
)
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
                pressed = key is not None
                while key is not None:
                    _press(shell, key, reader, live)
                    # Everything else already waiting, before drawing: a pasted line is one
                    # read of hundreds of keys, and a frame per key would take half a minute
                    # to show a sentence that was pasted in one.
                    key = reader.poll(0) if shell.running else None
                if not shell.paused:
                    shell.source.refresh()
                if not shell.paused or pressed:
                    size = shell.console.size
                    live.update(shell.screen(size.width, size.height))
        except KeyboardInterrupt:
            shell.running = False
        finally:
            _wind_down(shell, live)


def _press(shell: Shell, key: str, reader: KeyReader, live: Live | None) -> None:
    """One key, wherever it belongs.

    A question owns the keyboard while it is open: ``q`` types a q, space is a space, and the
    one way out of it is written on the panel.
    """
    if shell.asking is not None:
        answer(shell, key)
        return
    action = shell.resolve(key)
    if action in OPENS:
        shell.driver.notice = None
        if shell.can(action):
            OPENS[action](shell)
        else:
            shell.driver.notice = shell.refusal(action)
    elif action == "open" and shell.view == "checks":
        _page_log(shell, reader, live)
    elif action:
        shell.act(action)


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


def open_decide(shell: Shell) -> None:
    """Put the question the run stopped on into the panel that already states it.

    Answering and continuing are one act: the run stopped to ask, and the answer is what it was
    waiting for. Recording it and then leaving the run standing would turn one decision into
    two things to remember.
    """
    pending = shell.run.pending_decision
    if pending is None:
        return
    run_id = shell.run.id
    shell.asking = Ask(
        decision_question(shell.run, pending),
        commit=lambda answers: _decided(shell, run_id, answers),
    )


def _decided(shell: Shell, run_id: str, answers: Answers) -> None:
    try:
        shell.driver.decide(run_id, answers["choice"], answers.get("note", ""))
    except CONTROL_ERRORS as exc:
        shell.driver.notice = f"could not record it: {exc}"
        return
    shell.source.refresh(force=True)
    shell.view = stage_of(shell.run)


def open_create(shell: Shell) -> None:
    """Take an intent — or an existing change — and open the run it starts."""
    if not shell.driver.creates():
        shell.driver.notice = "this surface has no project to create a run in"
        return
    shell.asking = Ask(intent_question(), commit=lambda answers: _created(shell, answers))


def _created(shell: Shell, answers: Answers) -> None:
    intent, ref = intent_taken(answers)
    try:
        run_id = shell.driver.create(intent, ref)
    except CONTROL_ERRORS as exc:
        shell.driver.notice = f"could not create it: {exc}"
        return
    shell.source.refresh(force=True)
    with contextlib.suppress(LookupError):
        shell.select(run_id)
    shell.view = stage_of(shell.run)


def open_integrate(shell: Shell) -> None:
    """Ask which ref you merged into, then have the harness recognise it — or not."""
    run = shell.run
    if not run.result.report_ref:
        shell.driver.notice = "nothing has been delivered, so there is nothing to recognise"
        return
    it = run.current_iteration
    head = (it.version.head_commit if it and it.version else "") or ""
    run_id = run.id
    shell.asking = Ask(
        integration_question(head),
        commit=lambda answers: _integrated(shell, run_id, answers),
    )


def _integrated(shell: Shell, run_id: str, answers: Answers) -> None:
    try:
        shell.driver.integrate(run_id, answers["ref"], answers.get("rerun") == "yes")
    except CONTROL_ERRORS as exc:
        shell.driver.notice = f"could not check it: {exc}"


def open_merge(shell: Shell) -> None:
    """Read the repository once, then ask whether to merge into what is checked out there.

    The two facts the question rests on — which branch you are on, whether it is clean — are
    not on the run, and the surface cannot ask git for them on every frame. So they are read
    here, on the keystroke: a tree that would refuse the merge says so instead of opening a
    question whose only outcome is that refusal.
    """
    run = shell.run
    it = run.current_iteration
    head = (it.version.head_commit if it and it.version else "") or ""
    branch = run.result.branch or (it.version.branch if it and it.version else None)
    if not branch:
        shell.driver.notice = "the run delivered no branch to merge"
        return
    root = Path(run.project_root)
    try:
        into = git.current_branch(root) or "HEAD"
        dirty = git.has_uncommitted_changes(root)
        # A branch that has gone somewhere of its own cannot be fast-forwarded onto, so that
        # answer is not in the grid: the question offers what this repository can do now.
        ways = tuple(
            w for w in git.INTEGRATIONS if w != "fast-forward" or git.can_fast_forward(root, branch)
        )
    except (git.GitError, OSError) as exc:
        shell.driver.notice = f"could not read {root}: {exc}"
        return
    if dirty:
        shell.driver.notice = f"{into} has uncommitted changes; commit or stash them first"
        return
    run_id = run.id
    shell.asking = Ask(
        merge_question(branch, into, head, ways),
        commit=lambda answers: _merged(shell, run_id, answers),
    )


def _merged(shell: Shell, run_id: str, answers: Answers) -> None:
    try:
        shell.driver.merge(run_id, answers["how"], answers.get("checks") == "yes")
    except CONTROL_ERRORS as exc:
        shell.driver.notice = f"could not merge it: {exc}"


#: The controls that ask something before they act. On a terminal the question is drawn on the
#: surface; a prompted session asks the same steps in words. Both end in the same commit.
OPENS: dict[str, Callable[[Shell], None]] = {
    "decide": open_decide,
    "create": open_create,
    "integrate": open_integrate,
    "merge": open_merge,
}


def answer(shell: Shell, key: str) -> None:
    """One keystroke into the open question, and what to do when it closes.

    The commit runs here rather than inside the question so that what it refuses lands on the
    notice line, where every other refused control lands.
    """
    ask = shell.asking
    if ask is None:
        return
    ask.key(key)
    if ask.state == "done":
        shell.asking = None
        ask.commit(ask.answers)
    elif ask.state == "cancelled":
        shell.asking = None


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
        elif key == "c" and shell.can("create"):
            answers = ask_in_prompt(console, intent_question())
            if answers is not None:
                _created(shell, answers)
                _settle(shell)
        elif key == "m" and shell.can("merge"):
            open_merge(shell)
            ask = shell.asking
            shell.asking = None
            if ask is not None:
                answers = ask_in_prompt(console, ask.question)
                if answers is not None:
                    _merged(shell, shell.run.id, answers)
                    _settle(shell)
        elif key == "i" and shell.can("integrate"):
            it = shell.run.current_iteration
            head = (it.version.head_commit if it and it.version else "") or ""
            answers = ask_in_prompt(console, integration_question(head))
            if answers is not None:
                _integrated(shell, shell.run.id, answers)
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
