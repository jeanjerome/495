"""The two ways the shell is driven: keys on a terminal, prompts without one."""

from __future__ import annotations

from rich.live import Live
from rich.prompt import IntPrompt, Prompt
from rich.syntax import Syntax

from harness495.core.engine import EngineError
from harness495.interfaces.tui.keys import KeyReader
from harness495.interfaces.tui.shell import Shell
from harness495.interfaces.tui.stages import STAGE_BY_KEY, STAGES, stage_of
from harness495.interfaces.tui.views import ask_decision
from harness495.interfaces.tui.widgets import short

REFRESH = 10.0
"""Frames per second. The mark dissolves a digit every 0.12s, so below about eight the
animation reads as a stutter rather than a pulse; above it the screen costs more than it says."""


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
        while shell.running:
            key = reader.poll(timeout=1 / refresh)
            if key is not None:
                action = shell.resolve(key)
                if action == "decide":
                    _decide_inline(shell, reader, live)
                elif action == "open" and shell.view == "checks":
                    _page_log(shell, reader, live)
                elif action:
                    shell.act(action)
            if not shell.paused:
                shell.source.refresh()
            if not shell.paused or key is not None:
                size = shell.console.size
                live.update(shell.screen(size.width, size.height))


def _decide_inline(shell: Shell, reader: KeyReader, live: Live) -> None:
    """Take the screen down for the question, then give it back.

    A live region redraws over the last line, the prompt included, so a question asked
    underneath one is invisible and every answer typed into it is lost.
    """
    run = shell.run
    pending = run.pending_decision
    if pending is None:
        return
    live.stop()
    try:
        with reader.released():
            answer = ask_decision(shell.console, run, pending)
            if answer is not None:
                try:
                    shell.source.decide(run.id, answer[0], answer[1])
                except (EngineError, RuntimeError) as exc:
                    shell.console.print(f"[attn.dead]could not record it:[/] {exc}")
                else:
                    shell.view = stage_of(shell.run)
            Prompt.ask(
                "press enter to go back", default="", console=shell.console, show_default=False
            )
    finally:
        live.start(refresh=True)


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


def run_prompted(shell: Shell) -> None:
    """The same shell without a tty: print the view, ask what to do next, repeat.

    This is the path a piped session or CI takes. Nothing is hidden from it; it just cannot
    poll for keys, so it asks — and it asks with the same vocabulary the keyboard uses.
    """
    console = shell.console
    while shell.running:
        shell.source.refresh()
        console.print(shell.flow(console.width))
        run = shell.run
        if run.pending_decision is not None:
            answer = ask_decision(console, run, run.pending_decision)
            if answer is not None:
                try:
                    shell.source.decide(run.id, answer[0], answer[1])
                except (EngineError, RuntimeError) as exc:
                    console.print(f"[attn.dead]could not record it:[/] {exc}")
                    shell.running = False
                else:
                    shell.view = stage_of(shell.run)
            continue
        choices = [s.key for s in STAGES] + ["g", "l", "o", "?", "q"]
        key = Prompt.ask(
            "stage (1-7), g log, l runs, o open a run, ? help, q quit",
            choices=choices,
            default="q",
            console=console,
            show_choices=False,
        )
        if key == "o":
            index = IntPrompt.ask(
                f"run number (1-{len(shell.runs)})", default=shell.selected + 1, console=console
            )
            shell.selected = max(1, min(len(shell.runs), index)) - 1
            shell.view = stage_of(shell.run)
        elif key in STAGE_BY_KEY:
            shell.act(f"stage:{STAGE_BY_KEY[key]}")
        elif key in ("g", "l"):
            shell.act("view:" + ("log" if key == "g" else "runs"))
        elif key == "?":
            shell.act("help")
        else:
            shell.running = False
