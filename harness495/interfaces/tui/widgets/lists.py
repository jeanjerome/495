"""Rows, bullets and the marks that point at one of them."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from harness495.core.models import Finding
from harness495.interfaces.tui.theme import SEVERITIES


def bullets(
    heading: str, items: Sequence[str], style: str, empty: str = "none"
) -> RenderableType:
    """A heading and its items, each wrapping under itself rather than under its bullet.

    A bullet built by prefixing a string is a bullet only on the first line: the second one
    comes back to column zero and the list stops looking like a list.
    """
    grid = Table.grid(padding=(0, 1), expand=True)
    grid.add_column(width=2, style="h.rule", no_wrap=True)
    grid.add_column(ratio=1, overflow="fold")
    if not items:
        grid.add_row("", Text(empty, style="h.meta"))
    for item in items:
        grid.add_row("•", Text(item, style=style))
    return Group(Text(heading, style="h.key"), grid)


def commands(*lines: tuple[str, str]) -> RenderableType:
    """A shell command and what running it does. The point of the deliver stage."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(no_wrap=True, overflow="fold")
    grid.add_column(style="h.meta", ratio=1, overflow="ellipsis", no_wrap=True)
    for cmd, why in lines:
        grid.add_row(Text(cmd, style="h.ref.strong"), why)
    return grid


def cursor_cell(selected: bool) -> Text:
    return Text("▸" if selected else " ", style="cursor" if selected else "h.meta")


def nothing_yet(message: str) -> RenderableType:
    """A stage that has produced nothing says so in a sentence.

    The alternative — a header row over an empty table — puts the message in whichever column
    happens to be first, where it is usually four characters wide.
    """
    return Padding(Text(message, style="h.meta"), (0, 0, 0, 2))


def severity_counts(findings: Iterable[Finding]) -> Text:
    """``1b 2m`` — how many findings of each severity, worst first, each in its own colour."""
    counts = Text()
    items = list(findings)
    for sev in SEVERITIES:
        n = sum(1 for f in items if f.severity is sev)
        if n:
            counts.append(f"{n}{sev.value[0]} ", style=f"sev.{sev.value}")
    return counts if counts.plain else Text("—", style="h.meta")
