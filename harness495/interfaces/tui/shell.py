"""Application state, and the screen built from it.

Views read this; nothing in a view writes to it. Every key ends up in :meth:`Shell.act`,
whether it was polled from a terminal in raw mode or typed at a prompt, so the two input paths
cannot drift apart.

Two objects sit behind the shell and are deliberately different things: a *source* says what
the runs are, a *driver* makes one move. Which controls appear on screen is decided by asking
the driver what it can do here — a snapshot surface offers none rather than offering keys that
fail under the finger.
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Sequence

from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.padding import Padding
from rich.text import Text

from harness495.core.models import Event, Run, RunStatus
from harness495.interfaces.tui.attention import Attention, attention
from harness495.interfaces.tui.chrome import attention_band, footer_bar, header, nav_bar
from harness495.interfaces.tui.driving import Activity, Driver, ReadOnly
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
    Binding("s", "control:start", "start"),
    Binding("p", "control:pause", "pause the run"),
    Binding("c", "create", "new run"),
    Binding("i", "integrate", "check a ref", scope="integration"),
    Binding("space", "freeze", "freeze"),
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
        driver: Driver | None = None,
    ) -> None:
        self.source = source
        self.console = console
        self.animated = animated
        self.driver: Driver = driver or ReadOnly()
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
    def activity(self) -> Activity | None:
        """What this surface is doing — to *this* run, not to another one."""
        work = self.driver.working()
        return work if work is not None and work.run_id == self.run.id else None

    @property
    def held(self) -> str | None:
        return self.driver.held_elsewhere(self.run.id) if self.driver.drives() else None

    def attention(self) -> Attention:
        return attention(self.run, self.paused, self.activity, self.held, self.driver.drives())

    def startable(self) -> str | None:
        """What pressing ``s`` would do here, or ``None`` when nothing would.

        A run that is finished, that something else is advancing, or that is stopped on a
        question has no answer to "start it" — and a key that does nothing is worse than a key
        that is not offered, because it has to be tried before it can be ruled out.
        """
        if not self.driver.drives() or self.activity is not None or self.held is not None:
            return None
        status = self.run.status
        if self.run.pending_decision is not None:
            return None
        if status is RunStatus.created:
            return "start"
        if status is RunStatus.paused:
            return "continue"
        if status is RunStatus.failed:
            return "try again"
        if status in {RunStatus.delivered, RunStatus.aborted, RunStatus.rejected}:
            return None
        return "continue"

    def can(self, action: str) -> bool:
        """Whether this key would do something here.

        One rule for both ends: the footer offers what this allows and the loops refuse what it
        does not, so an offered key and a working key are never two different sets. Anything a
        run is not ours to act on — because another process is advancing it — is refused here
        rather than written over there.
        """
        if not self.driver.drives():
            return False
        if action == "create":
            return self.driver.creates()
        if action == "control:pause":
            # A stop is a file in the run directory, which is how ``495 stop`` reaches a run in
            # another terminal. So this one control works on a run this surface does not hold.
            work = self.activity
            if work is not None:
                return work.interruptible
            return self.held is not None
        if self.held is not None:
            return False
        if action == "decide":
            return self.run.pending_decision is not None
        if action == "control:start":
            return self.startable() is not None
        if action == "integrate":
            return bool(self.run.result.report_ref)
        return False

    def refusal(self, action: str) -> str | None:
        """Why a key did nothing, when the reason is not on the screen already."""
        if self.can(action) or action == "create":
            return None
        held = self.held
        if held is not None:
            return f"{self.run.id} is being advanced by {held}; act on it there"
        return None

    def controls(self) -> list[tuple[str, str]]:
        """The keys that act on the run right now, in the order they become relevant."""
        out: list[tuple[str, str]] = []
        if self.can("decide"):
            out.append(("d", "answer"))
        if self.can("control:pause"):
            out.append(("p", "pause the run"))
        verb = self.startable()
        if verb is not None and self.can("control:start"):
            out.append(("s", verb))
        if self.view == "integration" and self.can("integrate"):
            out.append(("i", "check a ref"))
        if self.can("create"):
            out.append(("c", "new run"))
        return out

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
        # Any key clears the last thing that went wrong: it has been read, or it has been
        # overtaken by whatever is being done now.
        self.driver.notice = None
        if action.startswith("control:"):
            if not self.can(action):
                self.driver.notice = self.refusal(action)
                return
            if action == "control:start":
                self.driver.start(self.run.id)
            else:
                self.driver.pause(self.run.id)
            return
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
        elif action == "freeze":
            self.paused = not self.paused
        elif action == "refresh":
            self.source.refresh(force=True)
        elif action == "help":
            self.helping = not self.helping
        elif action == "quit":
            self.running = False

    # ---- content

    def context(self) -> ViewContext:
        return ViewContext(
            run=self.run,
            cursor=self.cursor,
            logs=self.source.logs(self.run.id),
            can_drive=self.driver.drives(),
        )

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
        keys: list[tuple[str, str, bool]] = [(k, label, False) for k, label in self.controls()]
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

    def notice_line(self) -> RenderableType | None:
        """What the driver could not do, on a line of its own.

        Not in the band: the band says what the *run* needs, and a refused keystroke must not
        be able to hide a question the run is stopped on.
        """
        note = self.driver.notice
        if not note:
            return None
        return Padding(
            Text(f"✕  {note}", style="attn.dead", no_wrap=True, overflow="ellipsis"),
            (0, 1),
            style="chrome.bar",
            expand=True,
        )

    def screen(self, width: int, height: int) -> Layout:
        note = self.notice_line()
        rows = [
            Layout(name="header", size=2),
            Layout(name="band", size=3),
            *([Layout(name="notice", size=1)] if note is not None else []),
            Layout(name="nav", size=3),
            Layout(name="body"),
            Layout(name="footer", size=1),
        ]
        root = Layout()
        root.split_column(*rows)
        root["header"].update(header(self.run, self.animated))
        root["band"].update(attention_band(self.attention(), pulse("band")))
        if note is not None:
            root["notice"].update(note)
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
        note = self.notice_line()
        return Group(
            header(self.run, self.animated),
            attention_band(self.attention(), None),
            *([note] if note is not None else []),
            Responsive(lambda w: nav_bar(self.run, self.view, w)),
            self.body(width, 200),
            Responsive(
                lambda w: footer_bar(self.footer_keys(), self.run, self.elapsed, not self.paused, w)
            ),
        )
