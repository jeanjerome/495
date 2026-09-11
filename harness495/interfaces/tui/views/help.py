"""What every key does, and what every mark means."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.stages import STAGES
from harness495.interfaces.tui.widgets import panel

OTHER_KEYS = (
    ("→ ← tab", "walk", "the next or previous stage of the pipeline"),
    ("n", "catch up", "jump to the stage the run is actually at"),
    ("↑ ↓ / j k", "move", "the cursor; the detail beside the list follows it"),
    ("enter", "open", "the full log of the selected check, in your pager"),
    ("g", "log", "the event stream, filtered"),
    ("f", "filter", "log: useful → all → loud"),
    ("l", "runs", "every run in the store; enter opens one"),
    ("d", "decide", "answer the pending decision, wherever you are"),
    ("space", "pause", "freeze the display; the run itself keeps going"),
    ("r", "refresh", "reload the run from the store and redraw now"),
    ("?", "help", "this"),
    ("q", "quit", "anywhere; the run is not affected"),
)


def help_view() -> RenderableType:
    stages = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 2), show_edge=False)
    stages.add_column("key", width=5, style="cursor", no_wrap=True)
    stages.add_column("stage", width=9, style="bold", no_wrap=True)
    stages.add_column("answers", ratio=1)
    for s in STAGES:
        stages.add_row(f" {s.key} ", s.name, s.question)

    extra = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 2), show_edge=False)
    extra.add_column("key", width=11, style="cursor", no_wrap=True)
    extra.add_column("does", width=9, style="bold", no_wrap=True)
    extra.add_column("where", ratio=1, style="h.meta")
    for key, does, where in OTHER_KEYS:
        extra.add_row(f" {key} ", does, where)

    legend = Table.grid(padding=(0, 3))
    legend.add_column()
    legend.add_column()
    legend.add_row(
        Group(
            Text("on the pipeline strip", style="h.key"),
            Text.assemble(("● ", "tab.done"), ("a green tab is walked", "h.value")),
            Text.assemble(
                ("◉ ", "tab.here"), ("a cyan tab is where the run is working", "h.value")
            ),
            Text.assemble(
                ("◆ ", "tab.blocked"), ("a magenta tab has stopped to ask you", "h.value")
            ),
            Text.assemble(("○ ", "tab.todo"), ("a grey tab has not been reached", "h.value")),
            Text.assemble(
                ("┃ ", "tab.name.viewed"), ("a heavy frame is the tab you are on", "h.value")
            ),
            Text.assemble(
                ("4/6 ", "tab.count.bad"), ("a red count is why you would open it", "h.value")
            ),
        ),
        Group(
            Text("on a requirement", style="h.key"),
            Text.assemble(("● ", "req.satisfied"), ("satisfied by the evidence", "h.value")),
            Text.assemble(("✕ ", "req.violated"), ("contradicted by the evidence", "h.value")),
            Text.assemble(("◐ ", "req.undetermined"), ("the evidence cannot say", "h.value")),
            Text.assemble(("○ ", "req.pending"), ("not assessed yet", "h.value")),
        ),
    )
    return Group(
        panel(stages, ICON["pipeline"], "the pipeline is the navigation", "press a digit, or ← →"),
        panel(extra, ICON["keys"], "everything else"),
        panel(legend, ICON["legend"], "what the marks mean"),
    )
