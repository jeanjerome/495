"""Application state, and the screen built from it.

Views read this; nothing in a view writes to it. Every key ends up in :meth:`Shell.act`,
whether it was polled from a terminal in raw mode or typed at a prompt, so the two input paths
cannot drift apart.
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Sequence

from rich.console import Console, Group, RenderableType
from rich.layout import Layout

from harness495.core.models import Event, Run
from harness495.interfaces.tui.chrome import attention_band, footer_bar, header, nav_bar
from harness495.interfaces.tui.headlines import headline
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.keys import Binding
from harness495.interfaces.tui.source import RunSource, StaticSource
from harness495.interfaces.tui.stages import (
    DECISION_STAGE,
    STAGE_INDEX,
    STAGES,
    STATE_GLYPH,
    stage_of,
    stage_state,
)
from harness495.interfaces.tui.views import (
    STAGE_VIEWS,
    StageContent,
    ViewContext,
    build_log,
    build_runs,
    decision_panel,
    help_view,
)
from harness495.interfaces.tui.widgets import (
    FILTERS,
    Responsive,
    panel,
    pulse,
    two_columns,
    visible_events,
)

BINDINGS: tuple[Binding, ...] = (
    *(Binding(s.key, f"stage:{s.name}", s.name) for s in STAGES),
    Binding("right", "stage:+1", "stage", hidden=True),
    Binding("tab", "stage:+1", "stage", hidden=True),
    Binding("left", "stage:-1", "stage", hidden=True),
    Binding("shifttab", "stage:-1", "stage", hidden=True),
    Binding("n", "catchup", "catch up"),
    Binding("g", "view:log", "log"),
    Binding("l", "view:runs", "runs"),
    Binding("up", "cursor:-1", "move", scope="list", hidden=True),
    Binding("down", "cursor:+1", "move", scope="list", hidden=True),
    Binding("k", "cursor:-1", "up", scope="list", hidden=True),
    Binding("j", "cursor:+1", "down", scope="list", hidden=True),
    Binding("enter", "open", "open", scope="list"),
    Binding("f", "filter", "filter", scope="log"),
    Binding("d", "decide", "answer"),
    Binding("space", "pause", "pause"),
    Binding("r", "refresh", "refresh", hidden=True),
    Binding("?", "help", "help"),
    Binding("q", "quit", "quit"),
)

#: Views whose list takes a cursor.
LIST_VIEWS = frozenset({"profile", "spec", "change", "checks", "review", "verdict", "runs"})

SIDE_BY_SIDE = 136
"""Above this the detail sits beside the list; below it, under it. It is always on screen."""


class Shell:
    def __init__(
        self,
        source: RunSource,
        console: Console,
        selected: str | None = None,
        animated: bool = True,
    ) -> None:
        self.source = source
        self.console = console
        self.animated = animated
        self.selected = 0
        if selected is not None:
            self.select(selected)
        self.view = stage_of(self.run)
        self.cursors: dict[str, int] = {}
        self.filter = "useful"
        self.paused = False
        self.helping = False
        self.running = True
        self.started = time.monotonic()
        self.seen = len(visible_events(self.events, "loud"))

    @classmethod
    def over(
        cls, runs: Sequence[Run], events: Sequence[Event], console: Console, animated: bool = True
    ) -> Shell:
        """A shell over a snapshot, for a preview, an export or a test."""
        return cls(StaticSource(runs, events), console, animated=animated)

    # ---- state

    @property
    def runs(self) -> Sequence[Run]:
        return self.source.runs()

    @property
    def run(self) -> Run:
        runs = self.runs
        return runs[min(self.selected, len(runs) - 1)]

    @property
    def events(self) -> Sequence[Event]:
        return self.source.events(self.run.id)

    def select(self, run_id: str) -> None:
        for index, run in enumerate(self.runs):
            if run.id == run_id:
                self.selected = index
                return
        raise LookupError(run_id)

    @property
    def elapsed(self) -> float:
        """How long the run has been alive, not how long this surface has been up."""
        return (dt.datetime.now(dt.UTC) - self.run.created_at).total_seconds()

    @property
    def cursor(self) -> int:
        return self.cursors.get(f"{self.run.id}:{self.view}", 0)

    @cursor.setter
    def cursor(self, value: int) -> None:
        self.cursors[f"{self.run.id}:{self.view}"] = value

    @property
    def unseen(self) -> int:
        return max(0, len(visible_events(self.events, "loud")) - self.seen)

    @property
    def scope(self) -> str:
        if self.view == "log":
            return "log"
        return "list" if self.view in LIST_VIEWS else self.view

    def resolve(self, key: str) -> str | None:
        """Which action a key means here. Scope decides, so ``enter`` can differ between views."""
        if key == " ":
            key = "space"
        for b in BINDINGS:
            if b.key == key and b.scope in ("global", self.scope):
                return b.action
        return None

    def act(self, action: str) -> None:
        if action.startswith("stage:"):
            arg = action.split(":", 1)[1]
            if arg in ("+1", "-1"):
                here = STAGE_INDEX.get(self.view, STAGE_INDEX[stage_of(self.run)])
                self.view = STAGES[(here + int(arg)) % len(STAGES)].name
            else:
                self.view = arg
            self.helping = False
        elif action == "catchup":
            self.view, self.helping = stage_of(self.run), False
        elif action.startswith("view:"):
            name = action.split(":", 1)[1]
            self.view, self.helping = name, False
            if name == "log":
                self.seen = len(visible_events(self.events, "loud"))
        elif action.startswith("cursor:"):
            limit = self.row_count()
            if limit:
                self.cursor = (self.cursor + int(action.split(":", 1)[1])) % limit
        elif action == "open":
            if self.view == "runs":
                self.selected = min(self.cursor, len(self.runs) - 1)
                self.view = stage_of(self.run)
        elif action == "filter":
            self.filter = FILTERS[(FILTERS.index(self.filter) + 1) % len(FILTERS)]
        elif action == "pause":
            self.paused = not self.paused
        elif action == "refresh":
            self.source.refresh(force=True)
        elif action == "help":
            self.helping = not self.helping
        elif action == "quit":
            self.running = False

    # ---- content

    def context(self) -> ViewContext:
        return ViewContext(run=self.run, cursor=self.cursor, logs=self.source.logs(self.run.id))

    def content(self, height: int = 40) -> StageContent:
        if self.view == "runs":
            return build_runs(self.runs, self.cursor)
        if self.view == "log":
            return build_log(self.events, self.filter, max(6, height - 14), self.unseen)
        build = STAGE_VIEWS.get(self.view, STAGE_VIEWS["deliver"])
        return build(self.context())

    def row_count(self) -> int:
        """How many rows the current view offers the cursor.

        Counted from the run rather than by building the view: the footer and the cursor both
        need this on every frame, and rebuilding six tables to ask them how long they are
        would make every builder's cost a rendering cost.
        """
        run = self.run
        it = run.current_iteration
        return {
            "runs": len(self.runs),
            "profile": len(run.profile.commands) if run.profile else 0,
            "spec": len(run.spec.requirements),
            "change": len(it.version.files_changed) if it and it.version else 0,
            "checks": len(run.spec.verifications),
            "review": len(run.reviews),
            "verdict": len(run.spec.requirements),
        }.get(self.view, 0)

    def body(self, width: int, height: int) -> RenderableType:
        if self.helping:
            return help_view()
        run = self.run
        content = self.content(height)
        blocks: list[RenderableType] = []

        if self.view in STAGE_INDEX:
            stage = STAGES[STAGE_INDEX[self.view]]
            state = stage_state(run, self.view)
            blocks.append(
                panel(
                    headline(run, self.view),
                    STATE_GLYPH[state],
                    stage.name,
                    stage.question,
                    tone={"here": "live", "blocked": "ask", "failed": "bad"}.get(state, "quiet"),
                )
            )
            # The question goes where it was raised, above what it rests on.
            pending = run.pending_decision
            if pending is not None and DECISION_STAGE.get(pending.kind, "verdict") == self.view:
                blocks.append(decision_panel(run, pending))

        listing: RenderableType = (
            panel(
                content.body,
                ICON["list"],
                content.label,
                f"{content.rows}" if content.rows else "",
                subtitle="↑↓ moves the cursor; the detail follows it" if content.detail else "",
            )
            if content.label
            else content.body
        )
        if content.detail is None:
            blocks.append(listing)
            if content.below is not None:
                blocks.append(content.below)
        elif width >= SIDE_BY_SIDE:
            # Side by side, what the stage could not fit on a line stays under the list: the
            # detail column then reads as one object rather than floating above a gap.
            left = Group(listing, content.below) if content.below is not None else listing
            blocks.append(two_columns(left, content.detail, ratio=(3, 2)))
        else:
            blocks += [listing, content.detail]
            if content.below is not None:
                blocks.append(content.below)
        return Group(*blocks)

    def footer_keys(self) -> list[tuple[str, str, bool]]:
        """Key, label, and whether it names the view you are in.

        ``log`` and ``runs`` stay on the row when you are in them, marked: they are the only
        two destinations the pipeline strip does not show, so the footer is the only place
        that can say you are there.
        """
        rows = self.row_count()
        keys: list[tuple[str, str, bool]] = []
        if self.run.pending_decision is not None:
            keys.append(("d", "answer", False))
        if self.scope == "list" and rows:
            keys.append(("↑↓", "move", False))
        if self.view == "checks" and rows:
            keys.append(("enter", "full log", False))
        if self.view == "runs" and rows:
            keys.append(("enter", "open run", False))
        if self.view == "log":
            keys.append(("f", self.filter, False))
        keys.append(("←→", "stage", False))
        if self.view != stage_of(self.run):
            keys.append(("n", "catch up", False))
        unseen = self.unseen
        keys.append(("g", f"log · {unseen} new" if unseen else "log", self.view == "log"))
        keys.append(("l", "runs", self.view == "runs"))
        keys += [("?", "help", self.helping), ("q", "quit", False)]
        return keys

    # ---- rendering

    def screen(self, width: int, height: int) -> Layout:
        root = Layout()
        root.split_column(
            Layout(name="header", size=2),
            Layout(name="band", size=3),
            Layout(name="nav", size=3),
            Layout(name="body"),
            Layout(name="footer", size=1),
        )
        root["header"].update(header(self.run, self.animated))
        root["band"].update(attention_band(self.run, self.paused, pulse("band")))
        root["nav"].update(Responsive(lambda w: nav_bar(self.run, self.view, w)))
        root["body"].update(self.body(width, height))
        root["footer"].update(
            Responsive(
                lambda w: footer_bar(self.footer_keys(), self.run, self.elapsed, not self.paused, w)
            )
        )
        return root

    def flow(self, width: int) -> Group:
        """The same content without a ``Layout``, for piped output and exports.

        A ``Layout`` clips whatever does not fit and says nothing about it; a surface meant to
        be read after the fact, or captured, has to flow instead.
        """
        return Group(
            header(self.run, self.animated),
            attention_band(self.run, self.paused, None),
            Responsive(lambda w: nav_bar(self.run, self.view, w)),
            self.body(width, 200),
            Responsive(
                lambda w: footer_bar(self.footer_keys(), self.run, self.elapsed, not self.paused, w)
            ),
        )
