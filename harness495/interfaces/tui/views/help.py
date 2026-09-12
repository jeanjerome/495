"""What every key does, and what every mark means."""

from __future__ import annotations

from rich import box
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.stages import STAGES
from harness495.interfaces.tui.widgets import panel, two_columns

CONTROLS = (
    ("c", "new run", "an intent, or an existing change to evaluate; it starts straight away"),
    ("s", "start", "advance until it finishes or needs you; a paused or failed run resumes"),
    ("p", "pause", "stop after the step it is on — the agent is killed, nothing is lost"),
    ("d", "answer", "answer what the run stopped on, and let it carry on"),
    ("m", "merge", "merge the delivered branch into the branch you are on, then check it"),
    ("i", "integrate", "check the ref you merged into against the verified version"),
)
"""A control appears only where it applies: the footer offers what can act on this run now."""

OTHER_KEYS = (
    ("→ ← tab", "walk", "the next or previous stage of the pipeline"),
    ("n", "catch up", "jump to the stage the run is actually at"),
    ("↑ ↓ / j k", "move", "the cursor; the detail beside the list follows it"),
    ("enter", "open", "the full log of the selected check, in your pager"),
    ("g", "log", "the event stream, filtered"),
    ("f", "filter", "log: useful → all → loud"),
    ("l", "runs", "every run in the store; enter opens one"),
    ("space", "freeze", "stop refreshing the display; the run itself is untouched"),
    ("r", "refresh", "reload the run from the store and redraw now"),
    ("?", "help", "this"),
    ("q", "quit", "anywhere; the run keeps going without the surface"),
)


def _keys_table(rows: tuple[tuple[str, str, str], ...], width: int) -> Table:
    table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 2), show_edge=False)
    table.add_column("key", width=width, style="cursor", no_wrap=True)
    table.add_column("does", width=9, style="bold", no_wrap=True)
    table.add_column("where", ratio=1, style="h.meta")
    for key, does, where in rows:
        table.add_row(f" {key} ", does, where)
    return table


def help_view() -> RenderableType:
    stages = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 2), show_edge=False)
    stages.add_column("key", width=5, style="cursor", no_wrap=True)
    stages.add_column("stage", width=15, style="bold", no_wrap=True)
    stages.add_column("answers", ratio=1)
    for s in STAGES:
        # The same emoji the stage's own panel carries, so the list of stops and the stop you
        # land on are recognised as one thing before either is read.
        stages.add_row(f" {s.key} ", f"{ICON[s.name]}  {s.name}", s.question)

    legend = Table.grid(padding=(0, 3))
    legend.add_column()
    legend.add_column()
    legend.add_row(
        Group(
            Text("on the pipeline strip", style="h.key"),
            Text.assemble(("● ", "tab.done"), ("a green tab is walked", "h.value")),
            Text.assemble(
                ("◉ ", "tab.here"),
                ("a cyan tab is where the run is; it turns while something advances it", "h.value"),
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
        two_columns(
            panel(_keys_table(CONTROLS, 4), ICON["controls"], "what drives the run"),
            panel(_keys_table(OTHER_KEYS, 11), ICON["keys"], "what moves you around"),
        ),
        panel(legend, ICON["legend"], "what the marks mean"),
    )
