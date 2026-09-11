"""Arrangements that survive a narrow terminal.

Every helper here exists because the obvious alternative breaks under width pressure: a padded
``Text`` wraps its label into its value, a fixed column steals the space the content needed,
and a layout decided before Rich measures the surface ellipsizes the field that mattered.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.table import Table


def field_pairs(pairs: Sequence[tuple[str, RenderableType]], width: int = 12) -> Table:
    """Several label/value lines sharing one label column, so the values line up."""
    grid = Table.grid(padding=(0, 1), expand=True)
    grid.add_column(width=width, style="h.key", no_wrap=True, overflow="ellipsis")
    grid.add_column(ratio=1, overflow="fold")
    for key, value in pairs:
        grid.add_row(key, value)
    return grid


def two_columns(
    left: RenderableType, right: RenderableType, ratio: tuple[int, int] = (1, 1)
) -> Table:
    grid = Table.grid(padding=(0, 2), expand=True)
    grid.add_column(ratio=ratio[0])
    grid.add_column(ratio=ratio[1])
    grid.add_row(left, right)
    return grid


class Responsive:
    """Defers a layout choice to render time, when the surface's own width is known.

    A panel cannot tell whether it landed in a wide surface or a narrow cell until Rich
    measures it, and deciding earlier is how a layout ends up ellipsizing the field that
    mattered.
    """

    def __init__(self, build: Callable[[int], RenderableType]) -> None:
        self.build = build

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.build(options.max_width)
