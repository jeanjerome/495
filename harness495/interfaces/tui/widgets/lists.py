"""Rows, bullets and the marks that point at one of them."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from harness495.core.models import Finding
from harness495.interfaces.tui.theme import SEVERITIES

CHOICES_WIDE = 100
"""Below this a consequence goes under its label rather than into a third column."""


@dataclass(frozen=True)
class Choice:
    """One answer to a question, and what taking it does.

    ``key`` is what is typed, whole: two answers starting on the same letter would otherwise
    be given the same shortcut, and the key of a decision is also what ``495 decide`` takes.
    """

    key: str
    label: str
    consequence: str = ""
    marked: bool = False
    """Carries a star — it will ask for something more, such as the note behind a decision."""


def choices(options: Sequence[Choice], width: int) -> Table:
    """Every answer, with what taking it does to the run.

    A question whose answers are listed without their consequences is not a question: it is a
    guess. This is the one shape 495 asks in, whether the run raised the question or the
    surface did.
    """
    keyed = max((len(o.key) for o in options), default=6) + 2
    grid = Table.grid(padding=(0, 2), expand=True)
    grid.add_column(width=keyed, no_wrap=True)
    if width >= CHOICES_WIDE:
        grid.add_column(width=24, overflow="fold")
        grid.add_column(ratio=1, overflow="fold")
    else:
        grid.add_column(ratio=1, overflow="fold")
    for o in options:
        label = Text(o.label, style="h.title")
        if o.marked:
            label.append(" *", style="attn.you")
        chip = Text(f" {o.key} ", style="cursor")
        why = Text(o.consequence, style="h.meta")
        if width >= CHOICES_WIDE:
            grid.add_row(chip, label, why)
        else:
            grid.add_row(chip, Group(label, why))
    return grid


def bullets(heading: str, items: Sequence[str], style: str, empty: str = "none") -> RenderableType:
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
