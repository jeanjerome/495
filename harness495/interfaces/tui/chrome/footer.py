"""What can be pressed here, and what the run has spent."""

from __future__ import annotations

from collections.abc import Sequence

from rich.console import RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from harness495.core.models import Run
from harness495.interfaces.tui.widgets.text import hms

WIDE = 140
"""Above this, every key fits; below it the row is trimmed to what acts on the current view."""


def vitals(run: Run, elapsed: float, width: int = 200) -> Text:
    """What the run has spent and how long it has been at it. Never off the screen.

    The spend is the one figure that can end a run on its own, so it is the last thing a
    narrow terminal gives up.
    """
    c, b = run.consumption, run.budget
    out = Text(justify="right", no_wrap=True)
    if b.max_cost_usd:
        ratio = c.cost_usd / b.max_cost_usd
        style = "gauge.high" if ratio >= 0.9 else "gauge.warn" if ratio >= 0.7 else "h.value"
        out.append(f"{c.cost_usd:.2f}/{b.max_cost_usd:.0f} USD", style=style)
    else:
        out.append(f"{c.cost_usd:.2f} USD", style="gauge.warn")
    if width >= 100:
        out.append(f"  {c.usage.total_tokens / 1e6:.1f}M tok", style="h.meta")
        out.append(f"  it {run.iteration_number}/{b.max_iterations}", style="h.meta")
    out.append(f"  {hms(elapsed)}", style="h.meta")
    return out


def footer_bar(
    keys: Sequence[tuple[str, str, bool]],
    run: Run | None,
    elapsed: float,
    live: bool,
    width: int = 200,
) -> RenderableType:
    """The keys that act *here*, and the vitals. Stage keys live on the nav bar.

    Narrow terminals lose the general keys, never the ones that act on the view you are in: an
    ellipsis at the end of the row would drop exactly the wrong ones.

    ``run`` is ``None`` on the listing, where no run has been opened: a spend, an iteration
    count and a clock are facts about one run, and there is none to be had. The live mark
    stays, because it is the display that it speaks for.
    """
    room = 5 if width >= 104 else (4 if width >= 88 else 2)
    if width < WIDE and len(keys) > room:
        # The key naming the view you are in survives the trim: it is the only thing on the
        # row that answers "where am I" when the pipeline strip cannot, because you are not on
        # a stage at all. So does the last key, which is always the way out of the screen —
        # quit, or the escape that closes a question. A row that already fits is left exactly
        # as it was: a trim that added a key would offer one the surface did not.
        keys = [*keys[:room], *(k for k in keys[room:-1] if k[2]), keys[-1]]
    left = Text(no_wrap=True, overflow="ellipsis")
    for key, label, active in keys:
        left.append(f" {key} ", style="key.active" if active else "h.rule")
        left.append(f"{label}  ", style="tab.name.viewed" if active else "h.meta")
    right = vitals(run, elapsed, width) if run is not None else Text(justify="right")
    right.append("  ●" if live else "  ‖", style="req.satisfied" if live else "gauge.warn")

    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(ratio=1, overflow="ellipsis")
    grid.add_column(justify="right", width=len(right.plain) + 2, no_wrap=True)
    grid.add_row(left, right)
    return Padding(grid, (0, 1), style="chrome.bar", expand=True)
