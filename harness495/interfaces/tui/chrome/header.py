"""Identity: which run, which intent, which commits."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from harness495.core.models import Run
from harness495.interfaces.tui.chrome.logo import WIDTH as LOGO_WIDTH
from harness495.interfaces.tui.chrome.logo import LogoMark
from harness495.interfaces.tui.stages import status_style
from harness495.interfaces.tui.widgets.layout import Responsive
from harness495.interfaces.tui.widgets.text import clip, short

MARK_FLOOR = 92
"""Below this width the mark goes: it is the one thing here that carries no information."""


def header(run: Run, animated: bool = True) -> RenderableType:
    return Responsive(lambda w: _header(run, w, animated))


def _header(run: Run, width: int, animated: bool) -> RenderableType:
    """Identity, in two rows, with the mark standing across both.

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
    return Padding(grid, (0, 1), expand=True)
