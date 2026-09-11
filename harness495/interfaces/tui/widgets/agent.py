"""Who held the tree, with which permissions, in which sandbox, for how long."""

from __future__ import annotations

import datetime as dt

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from harness495.core.models import Capability, Intervention, InterventionStatus, Run
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.widgets.gauges import badge
from harness495.interfaces.tui.widgets.layout import field_pairs
from harness495.interfaces.tui.widgets.panels import panel
from harness495.interfaces.tui.widgets.progress import WorkingBar
from harness495.interfaces.tui.widgets.text import clip, hms

WRITING_TOOLS = frozenset({"edit", "write", "multiedit", "notebookedit", "apply_patch"})


def activity_bars(activity: dict[str, int], width: int = 18) -> Table:
    """Tool counts from the transcript: how the agent spent its turn, read against write."""
    top = sorted(activity.items(), key=lambda item: -item[1])[:6]
    peak = max((n for _, n in top), default=1)
    grid = Table.grid(padding=(0, 1))
    grid.add_column(width=10, style="h.value", no_wrap=True)
    grid.add_column(width=width)
    grid.add_column(justify="right", style="h.meta", width=4)
    for tool, n in top:
        writes = tool.lower() in WRITING_TOOLS
        grid.add_row(
            tool,
            Text(
                "▇" * max(1, round(n / peak * width)),
                style="tool.write" if writes else "tool.read",
            ),
            str(n),
        )
    return grid


def agent_card(
    run: Run, current: Intervention | None, working: WorkingBar | None = None
) -> RenderableType:
    """The card for one intervention.

    The capability is a badge rather than a field because it is the single most consequential
    fact about a running agent, and a field reads at the same weight as a timeout.
    """
    if current is None:
        return panel(
            Text("no agent has run for this stage yet", style="h.meta"), ICON["agent"], "agent"
        )
    a, s = current.agent, current.sandbox
    running = current.status is InterventionStatus.running
    write = current.capability is Capability.write
    elapsed = (
        (dt.datetime.now(dt.UTC) - current.started_at).total_seconds()
        if running
        else (current.duration_s or 0.0)
    )
    cost = f"{current.cost.usd:.2f} USD" if current.cost.usd is not None else "unpriced"
    body: list[RenderableType] = [
        field_pairs(
            [
                (
                    "role",
                    Text(
                        current.role.value
                        + (f" · {current.perspective}" if current.perspective else ""),
                        style="h.value",
                    ),
                ),
                ("agent", Text(f"{a.kind.value}:{a.model or 'default'}", style="h.ref")),
                (
                    "may",
                    badge(
                        "WRITE the worktree" if write else "READ only",
                        "cap.write" if write else "cap.read",
                    ),
                ),
                (
                    "sandbox",
                    Text(
                        f"{s.backend}, network {s.network}"
                        + (f", writes {', '.join(s.writable_paths)}" if s.writable_paths else ""),
                        style="gauge.warn" if s.network != "denied" else "h.value",
                    ),
                ),
                (
                    "spent",
                    Text(
                        f"{hms(elapsed)} of {current.timeout_s // 60}m  ·  {cost}  ·  "
                        f"{current.usage.total_tokens / 1000:.0f}k tokens",
                        style="gauge.warn" if elapsed > current.timeout_s * 0.8 else "h.value",
                    ),
                ),
            ]
        )
    ]
    if running and working is not None:
        left = max(0.0, current.timeout_s - elapsed)
        body += [Text(), working.renderable(f"{hms(left)} before the timeout kills it")]
    if current.activity:
        body += [Text(), Text("what it did", style="h.key"), activity_bars(current.activity)]
    if current.error:
        body += [Text(), Text(clip(current.error, 160), style="attn.dead")]
    return panel(
        Group(*body),
        ICON["agent"],
        "agent",
        f"{current.id} · {'running' if running else current.status.value}",
        tone="live" if running else "quiet",
    )
