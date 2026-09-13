"""Identity: which run, which intent, which commits."""

from __future__ import annotations

from collections.abc import Sequence

from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from harness495 import __version__
from harness495.core.models import Run
from harness495.interfaces.tui.chrome.footer import store_vitals
from harness495.interfaces.tui.chrome.logo import WIDTH as LOGO_WIDTH
from harness495.interfaces.tui.chrome.logo import LogoMark
from harness495.interfaces.tui.stages import status_style
from harness495.interfaces.tui.widgets.layout import Responsive
from harness495.interfaces.tui.widgets.text import clip, short

MARK_FLOOR = 92
"""Below this width the mark goes: it is the one thing here that carries no information."""


def _rule(width: int) -> Text:
    """The line that closes the header, whichever of the two it is.

    The screen is three things stacked — who you are looking at, what it needs, what it holds
    — and the first two used to touch: the band's own frame opened one row under the last row
    of the header, so the eye read one block of five lines rather than an identity and a state.
    A rule ends the first, and it is the quietest mark the theme has, because saying "the
    header stopped here" is all it does.

    Full width, where the header's own rows are inset by one: it is a divider of the screen,
    not of the text above it, and it lines up with the frames below rather than with the words.
    """
    return Text("─" * max(0, width), style="h.rule", no_wrap=True)


def header(run: Run, animated: bool = True) -> RenderableType:
    return Responsive(lambda w: _header(run, w, animated))


def store_header(runs: Sequence[Run], animated: bool = True) -> RenderableType:
    """Identity on the listing: which store you are in, what it holds, and that nothing is open.

    The run header names a run. On the listing there is none — one has not been picked yet —
    and the store is what the screen is about, so that is what it names. A store is one
    project's ``.495`` directory, which is why the project can be read off any run in it.

    The second row is what the run header spends on a branch and two commits: how many runs
    the store holds and what they have cost between them. It is the only place that figure is
    stated — a run's own spend is on its footer, and nobody adds up eight of those by eye.
    """
    return Responsive(lambda w: _store_header(runs, w, animated))


def _store_header(runs: Sequence[Run], width: int, animated: bool) -> RenderableType:
    root = runs[0].project_root if runs else ""
    ident = Text(no_wrap=True, overflow="ellipsis")
    ident.append(root.rsplit("/", 1)[-1] or "no project", style="h.ref.strong")
    where = Text(root, style="h.meta", no_wrap=True, overflow="ellipsis")
    state = Text("no run is open", style="h.meta", justify="right", no_wrap=True)

    grid = Table.grid(expand=True, padding=(0, 2))
    if width >= MARK_FLOOR:
        grid.add_column(width=LOGO_WIDTH, vertical="middle")
    grid.add_column(ratio=3, overflow="ellipsis", vertical="middle")
    grid.add_column(ratio=2, justify="right", overflow="ellipsis", vertical="middle")
    holdings = store_vitals(runs, width)
    holdings.append(f"  495 {__version__}", style="h.meta")
    cells: list[RenderableType] = [Group(ident, where), Group(state, holdings)]
    if width >= MARK_FLOOR:
        grid.add_row(LogoMark(animated), *cells)
    else:
        grid.add_row(*cells)
    return Group(Padding(grid, (0, 1), expand=True), _rule(width), Text())


def _header(run: Run, width: int, animated: bool) -> RenderableType:
    """Identity, in two rows and a rule, with the mark standing across both.

    No frame. This is reference material — which run, which intent, which commits — and it is
    read once and then ignored; a heavy border around it spends the eye's attention on the one
    thing in the chrome that never changes and never asks for anything. The weight belongs to
    the band under it, which is the part that does.
    """
    it = run.current_iteration
    v = it.version if it else None

    ident = Text(no_wrap=True, overflow="ellipsis")
    ident.append(run.id, style="h.ref.strong")
    ident.append(f"   {run.mode.value}", style="h.meta")
    # Not bold: the intent is otherwise the brightest thing in the header, competing with the
    # band for an attention it never needs — it does not change.
    intent = Text(clip(run.intent.text, 200), style="h.value", no_wrap=True, overflow="ellipsis")

    state = Text(justify="right", no_wrap=True)
    state.append(run.status.value.replace("_", " "), style=status_style(run.status))
    refs = Text(justify="right", no_wrap=True, overflow="ellipsis")
    refs.append(run.project_root.rsplit("/", 1)[-1], style="h.value")
    if v:
        refs.append("  ·  ", style="h.meta")
        refs.append(v.branch or "detached", style="h.ref")
        refs.append(f"  {short(v.base_commit)}→{short(v.head_commit)}", style="h.meta")

    grid = Table.grid(expand=True, padding=(0, 2))
    # Eleven columns of branding are eleven columns not spent on the intent.
    if width >= MARK_FLOOR:
        grid.add_column(width=LOGO_WIDTH, vertical="middle")
    grid.add_column(ratio=3, overflow="ellipsis", vertical="middle")
    grid.add_column(ratio=2, justify="right", overflow="ellipsis", vertical="middle")
    cells: list[RenderableType] = [Group(ident, intent), Group(state, refs)]
    if width >= MARK_FLOOR:
        grid.add_row(LogoMark(animated), *cells)
    else:
        grid.add_row(*cells)
    return Group(Padding(grid, (0, 1), expand=True), _rule(width), Text())
