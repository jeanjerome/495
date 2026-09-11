"""Wiring: a console, a source, a shell, and whichever loop the terminal allows."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.text import Text

from harness495.core.store import RunStore
from harness495.interfaces.tui.keys import KeyReader
from harness495.interfaces.tui.loops import run_interactive, run_prompted
from harness495.interfaces.tui.shell import Shell
from harness495.interfaces.tui.source import StoreSource
from harness495.interfaces.tui.theme import THEME


def build_console(width: int | None = None, record: bool = False) -> Console:
    """A console that speaks the theme. Nothing outside it may name a colour."""
    return Console(theme=THEME, highlight=False, record=record, width=width)


def watch(
    store: RunStore,
    run_id: str | None = None,
    stage: str | None = None,
    console: Console | None = None,
    once: bool = False,
    export: Path | None = None,
) -> int:
    """Open the run surface over a store.

    Returns a process exit code: 0 once the surface is closed, 1 if there was nothing to open.

    The surface never drives the run — it reads what has been written and answers the decision
    the run is stopped on. So it can be left up in one terminal while ``495 run`` advances the
    same run in another, and both agree, because both are reading the same files.
    """
    console = console or build_console(record=export is not None)
    source = StoreSource(store)
    if not source.runs():
        console.print(Text("no run in this state directory yet", style="h.meta"))
        return 1

    shell = Shell(source, console, animated=_animated(console, once or export is not None))
    if run_id is not None:
        try:
            shell.select(run_id)
        except LookupError:
            console.print(Text(f"run {run_id} not found", style="attn.dead"))
            return 1
        shell.view = stage or shell.view
    else:
        # No id given: the listing is the only screen that can answer "which run".
        shell.view = stage or "runs"
    if stage is not None:
        shell.view = stage

    if once or export is not None:
        console.print(shell.flow(console.width))
        if export is not None:
            console.save_svg(str(export), title=f"495 {shell.run.id} · {shell.view}")
            console.print(Text(f"written {export}", style="h.meta"))
        return 0

    with KeyReader() as reader:
        if reader.interactive:
            run_interactive(shell, reader)
        else:
            run_prompted(shell)
    return 0


def _animated(console: Console, still: bool) -> bool:
    """The mark moves only where movement is drawn rather than recorded.

    A single render, an SVG export or a redirected stdout each capture one frame, and a frame
    caught mid-dissolution reads as a broken glyph rather than as an animation.
    """
    return not still and console.is_terminal
