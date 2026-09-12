"""Wiring: a console, a source, a driver, a shell, and whichever loop the terminal allows."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.text import Text

from harness495.core.store import RunStore
from harness495.interfaces.tui.driving import Driver, ReadOnly, StoreDriver
from harness495.interfaces.tui.keys import KeyReader
from harness495.interfaces.tui.loops import echo_events, run_interactive, run_prompted
from harness495.interfaces.tui.shell import Shell
from harness495.interfaces.tui.source import StoreSource
from harness495.interfaces.tui.theme import THEME
from harness495.interfaces.tui.views import ask_intent


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
    project: Path | None = None,
    read_only: bool = False,
) -> int:
    """Open the run surface: the pipeline, what each stage produced, and the controls.

    Returns a process exit code: 0 once the surface is closed, 1 if there was nothing to open.

    The surface drives runs but never on its own: it advances one when a key says so, and the
    engine claims the run for as long as it does, so a run already being advanced from another
    terminal is watched rather than joined. Rendering alone changes nothing, which is what
    ``--read-only``, a single ``--print`` and an export all rely on.
    """
    console = console or build_console(record=export is not None)
    still = once or export is not None
    driver: Driver = ReadOnly() if read_only or still else StoreDriver(store, project=project)
    source = StoreSource(store)

    if not source.runs():
        opened = _first_run(console, driver)
        if opened is None:
            return 1
        source.refresh(force=True)
        run_id = opened

    shell = Shell(source, console, animated=_animated(console, still), driver=driver)
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

    if still:
        console.print(shell.flow(console.width))
        if export is not None:
            console.save_svg(str(export), title=f"495 {shell.run.id} · {shell.view}")
            console.print(Text(f"written {export}", style="h.meta"))
        return 0

    with KeyReader() as reader:
        if reader.interactive:
            run_interactive(shell, reader)
        else:
            if isinstance(driver, StoreDriver):
                driver.on_event = echo_events(console)
            run_prompted(shell)
    return 0


def _first_run(console: Console, driver: Driver) -> str | None:
    """An empty store has no surface to draw, so it asks for the one thing that would fill it.

    The first stop of the workflow is the intent arriving. A store with nothing in it is that
    moment, and answering "no run yet" with a command to go and type elsewhere would be the
    surface refusing the only thing it is there for.
    """
    if not driver.creates() or not console.is_terminal:
        console.print(
            Text.assemble(
                ("no run in this state directory yet", "h.meta"),
                ('  ·  start one with 495 new "<intent>"', "attn.hint"),
            )
        )
        return None
    console.print(Text("No run here yet.", style="h.meta"))
    answer = ask_intent(console)
    if answer is None:
        return None
    try:
        return driver.create(*answer)
    except Exception as exc:  # noqa: BLE001
        console.print(Text(f"could not create it: {exc}", style="attn.dead"))
        return None


def _animated(console: Console, still: bool) -> bool:
    """The mark moves only where movement is drawn rather than recorded.

    A single render, an SVG export or a redirected stdout each capture one frame, and a frame
    caught mid-dissolution reads as a broken glyph rather than as an animation.
    """
    return not still and console.is_terminal
