"""How close a ceiling is, drawn so that unknown never looks like zero."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text


def gauge(fraction: float | None, width: int = 10) -> Text:
    """How close to a ceiling the run is. Unknown is shown as unknown, never as zero."""
    if fraction is None:
        return Text("░" * width, style="gauge.empty")
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * width)
    style = "gauge.high" if fraction >= 0.9 else "gauge.warn" if fraction >= 0.7 else "gauge.ok"
    return Text("█" * filled, style=style) + Text("░" * (width - filled), style="gauge.empty")


def meter(
    label: str,
    used: float,
    ceiling: float | None,
    fmt: str = "{:.0f}",
    compact: bool = False,
) -> Table:
    """One ceiling line: label, bar, used against the ceiling. No ceiling means no bar."""
    grid = Table.grid(padding=(0, 1))
    grid.add_column(width=10 if compact else 12, style="h.key", no_wrap=True)
    grid.add_column(width=6 if compact else 10)
    grid.add_column(width=13 if compact else 16, justify="right", style="h.value", no_wrap=True)
    if ceiling:
        grid.add_row(
            label,
            gauge(used / ceiling, 6 if compact else 10),
            f"{fmt.format(used)} / {fmt.format(ceiling)}",
        )
    else:
        grid.add_row(label, Text("—", style="h.meta"), fmt.format(used))
    return grid


def badge(label: str, style: str) -> Text:
    return Text(f" {label} ", style=style)
