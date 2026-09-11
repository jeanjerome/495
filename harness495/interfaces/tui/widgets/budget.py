"""What the run has spent against every ceiling that can stop it."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from harness495.core.models import CostBasis, Run
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.widgets.gauges import meter
from harness495.interfaces.tui.widgets.layout import Responsive
from harness495.interfaces.tui.widgets.panels import panel
from harness495.interfaces.tui.widgets.text import plural


def budget_panel(run: Run) -> Panel:
    return panel(Responsive(lambda w: budget_meters(run, w < 46)), ICON["budget"], "budget")


def budget_meters(run: Run, compact: bool) -> RenderableType:
    c, b = run.consumption, run.budget
    rows: list[RenderableType] = [
        meter("spend USD", c.cost_usd, b.max_cost_usd, "{:.2f}", compact),
        meter(
            "tokens",
            c.usage.total_tokens / 1e6,
            (b.max_total_tokens or 0) / 1e6 or None,
            "{:.2f}M",
            compact,
        ),
        meter("agent runs", c.interventions, b.max_interventions, "{:.0f}", compact),
        meter("iterations", run.iteration_number, b.max_iterations, "{:.0f}", compact),
    ]
    util = c.usage.context_utilization
    if util is not None:
        mark = "≤" if c.usage.context_peak_is_upper_bound else ""
        rows.append(meter(f"context {mark}", util * 100, 100.0, "{:.0f}%", compact))
    note = f"cost basis {c.cost_basis.value}"
    if c.cost_unknown_interventions:
        n = c.cost_unknown_interventions
        note += f", {n} {plural(n, 'run')} unpriced"
    rows += [
        Text(),
        Text(note, style="h.meta" if c.cost_basis is CostBasis.reported else "gauge.warn"),
    ]
    return Group(*rows)
