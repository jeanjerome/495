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
from harness495.interfaces.tui.asking import Ask
from harness495.interfaces.tui.attention import Attention, attending, attention, store_attention
from harness495.interfaces.tui.chrome import (
    attention_band,
    footer_bar,
    header,
    nav_bar,
    store_header,
)
from harness495.interfaces.tui.driving import Activity, Driver, ReadOnly
from harness495.interfaces.tui.headlines import headline
from harness495.interfaces.tui.icons import ICON
from harness495.interfaces.tui.keys import Binding
from harness495.interfaces.tui.source import RunSource, StaticSource
from harness495.interfaces.tui.stages import (
    DECISION_STAGE,
    STAGE_INDEX,
    STAGES,
    stage_of,
    stage_state,
)
from harness495.interfaces.tui.views import (
    STAGE_VIEWS,
    HomeContext,
    StageContent,
    ViewContext,
    build_home,
    build_log,
    decision_panel,
    help_view,
)
from harness495.interfaces.tui.widgets import (
    FILTERS,
    Responsive,
    panel,
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
    Binding("m", "merge", "merge the branch"),
    Binding("i", "integrate", "check a ref"),
    Binding("space", "freeze", "freeze"),
    Binding("r", "refresh", "refresh", hidden=True),
    Binding("?", "help", "help"),
    Binding("q", "quit", "quit"),
)

#: Views whose list takes a cursor.
LIST_VIEWS = frozenset({"profile", "spec", "change", "checks", "review", "verdict", "runs"})

NOT_ON_THE_HOME = frozenset({"stage:+1", "stage:-1", "filter"})
"""The two keys that have no meaning on the home page, and the one that belongs elsewhere.

← and → walk to the *next* stop, which needs a stop to start from; the home page stands at
none. Taking that origin from whichever run happens to be open is exactly the borrowing this
page exists to end. The digits do work here — a stop is somewhere to stand *in* a run, so they
open the row under the cursor there — and ``f`` is the log's own key."""

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
        self.opened = False
        self.asking: Ask | None = None
        """The question being answered on the surface, which owns the keyboard while it is."""
        if selected is not None:
            self.select(selected)
        self.view = stage_of(self.run) if self.opened else "runs"
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
        """A shell over a snapshot of one run, for a preview, an export or a test.

        The run is open: a snapshot is taken *of* something, and a preview that opened on the
        listing would show the store rather than the run it was asked for.
        """
        return cls(StaticSource(runs, events), console, animated=animated, selected=runs[0].id)

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
        """The event stream of the open run. A store with nothing in it has none.

        Emptying the store is something another terminal can do — ``495 cleanup`` takes a run
        away while this one is up — and the surface has to survive it, which it does by
        landing on the page that is about the store rather than about one of its runs.
        """
        return self.source.events(self.run.id) if self.runs else ()

    def select(self, run_id: str) -> None:
        """Open a run. Everything the chrome says, and every key that acts, is about this one."""
        for index, run in enumerate(self.runs):
            if run.id == run_id:
                self.selected = index
                self.opened = True
                return
        raise LookupError(run_id)

    @property
    def elapsed(self) -> float:
        """How long the run has been alive, not how long this surface has been up."""
        return (dt.datetime.now(dt.UTC) - self.run.created_at).total_seconds()

    @property
    def at_home(self) -> bool:
        """Whether the screen is the store's rather than one run's.

        The listing is the home page whether or not a run was opened behind it. Read off the
        *view*, never off ``opened``: that is a latch nothing lowers, so a chrome hung on it
        went on naming the last run opened for the rest of the session — the header named it,
        the band asked its question and the strip drew its pipeline, three rows above a cursor
        standing somewhere else entirely.
        """
        return self.view == "runs" or not self.opened

    @property
    def focus(self) -> Run | None:
        """The run a key acts on: the row under the cursor at home, the open run inside one.

        One subject per screen, and it is always the one the screen points at. The alternative
        is the one the surface used to take: the controls kept acting on the run opened last,
        so ``d`` answered a question three rows above the cursor and the footer offered it —
        two runs on one screen, one of them invisible.
        """
        runs = self.runs
        if not runs:
            return None
        return runs[min(self.cursor, len(runs) - 1)] if self.at_home else self.run

    @property
    def cursor_key(self) -> str:
        """Where the cursor of the current view is remembered.

        Per run everywhere but on the listing: a row there *is* a run, so keying it by the run
        you happen to have open would reset it the moment you opened another one.
        """
        return "runs" if self.at_home else f"{self.run.id}:{self.view}"

    @property
    def cursor(self) -> int:
        return self.cursors.get(self.cursor_key, 0)

    @cursor.setter
    def cursor(self, value: int) -> None:
        self.cursors[self.cursor_key] = value

    @property
    def unseen(self) -> int:
        return max(0, len(visible_events(self.events, "loud")) - self.seen)

    @property
    def activity(self) -> Activity | None:
        """What this surface is doing — to the run in focus, not to another one."""
        work = self.driver.working()
        run = self.focus
        return work if work is not None and run is not None and work.run_id == run.id else None

    @property
    def held(self) -> str | None:
        run = self.focus
        if run is None or not self.driver.drives():
            return None
        return self.driver.held_elsewhere(run.id)

    def attention(self) -> Attention:
        return attention(self.run, self.activity, self.held, self.driver.drives())

    def store_state(self) -> Attention:
        """What the *store* needs from you, for the band on the home page.

        The run this surface is driving is passed in because the store cannot see it: between
        two interventions a run being walked from here holds no running intervention, and the
        band would call it idle for as long as the harness takes to start the next agent.
        """
        work = self.driver.working()
        return store_attention(
            self.runs, [work.run_id] if work is not None else (), self.driver.creates()
        )

    def attend(self) -> None:
        """Put the cursor on the run the store's attention is on.

        The band names it and this goes to it, both from :func:`attending`, so the row ``n``
        lands on is always the row the band was talking about.
        """
        target = attending(self.runs)
        if target is None:
            return
        for index, run in enumerate(self.runs):
            if run.id == target.id:
                self.cursor = index
                return

    def moving(self, attn: Attention) -> bool:
        """Whether the marks that stand for work should turn rather than stand still.

        Something has to be advancing the run, and the surface has to be one where movement is
        drawn rather than recorded: a single ``--print`` and an SVG export each capture one
        frame, and a frame of a spinner caught on its own reads as an arbitrary glyph where a
        still ◉ reads as the state it is. A frozen display draws nothing that moves either —
        the point of ``space`` is that the screen stops.
        """
        return self.animated and not self.paused and attn.working

    def startable(self) -> str | None:
        """What pressing ``s`` would do here, or ``None`` when nothing would.

        A run that is finished, that something else is advancing, or that is stopped on a
        question has no answer to "start it" — and a key that does nothing is worse than a key
        that is not offered, because it has to be tried before it can be ruled out.
        """
        run = self.focus
        if run is None or not self.driver.drives():
            return None
        if self.activity is not None or self.held is not None:
            return None
        status = run.status
        if run.pending_decision is not None:
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
        if self.asking is not None:
            # The keyboard belongs to the question: every key is an answer, and a control
            # offered here would be a control whose key types a character instead.
            return False
        if not self.driver.drives():
            return False
        if action == "create":
            return self.driver.creates()
        run = self.focus
        if run is None:
            # Every control below names "the run". An empty store holds none.
            return False
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
            return run.pending_decision is not None
        if action == "control:start":
            return self.startable() is not None
        if action == "integrate":
            return bool(run.result.report_ref)
        if action == "merge":
            # Offered until the check says the branch is in. Whether the tree is clean enough
            # for it is a question for git, and asking git on every frame would put a
            # subprocess behind the footer; the question asks once, when it is pressed.
            return bool(run.result.branch) and run.integration_state() != "landed"
        return False

    def refusal(self, action: str) -> str | None:
        """Why a key did nothing, when the reason is not on the screen already."""
        if self.can(action) or action == "create":
            return None
        held = self.held
        run = self.focus
        if held is not None and run is not None:
            return f"{run.id} is being advanced by {held}; act on it there"
        return None

    def controls(self) -> list[tuple[str, str]]:
        """The keys that act on the run in focus right now, in the order they become relevant.

        On the home page that is the row under the cursor, so the listing offers what would
        happen to the run you are pointing at — and offers nothing where pointing at it is all
        this surface can do.
        """
        run = self.focus
        out: list[tuple[str, str]] = []
        if self.can("decide"):
            out.append(("d", "answer"))
        if self.can("control:pause"):
            out.append(("p", "pause the run"))
        verb = self.startable()
        if verb is not None and self.can("control:start"):
            out.append(("s", verb))
        if self.can("merge"):
            out.append(("m", "merge the branch"))
        if self.can("integrate"):
            # Not only on the eighth stop. It is the one thing left to do on a delivered run,
            # and a control that appears only once you have found the stop it belongs to is a
            # control you find by accident. Once something has landed it is no longer that one
            # thing, so it stops being named like it: what is left is asking again later.
            landed = run is not None and run.integration_state() == "landed"
            out.append(("i", "check it again" if landed else "check a ref"))
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
        if self.at_home and not self._home_act(action):
            return
        if action.startswith("control:"):
            run = self.focus
            if run is None or not self.can(action):
                self.driver.notice = self.refusal(action)
                return
            if action == "control:start":
                self.driver.start(run.id)
            else:
                self.driver.pause(run.id)
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
            if self.at_home and self._open_cursor():
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

    def _home_act(self, action: str) -> bool:
        """One key on the home page. ``False`` when it was spent here and goes no further.

        Everything the page can do itself is done here — the cursor, the jump to what needs
        you — and everything that only makes sense *inside* a run opens the row under the
        cursor first, so a digit lands on that run's stop rather than on the stop of a run the
        screen was not about. The controls fall through untouched: they already act on the run
        in focus, which on this page is that same row.
        """
        if action in NOT_ON_THE_HOME:
            return False
        if action == "catchup":
            self.attend()
            return False
        if action.startswith("stage:") or action == "view:log":
            return self._open_cursor()
        return True

    def _open_cursor(self) -> bool:
        """Open the row the cursor is on. ``False`` when the store is empty."""
        runs = self.runs
        if not runs:
            return False
        self.selected = min(self.cursor, len(runs) - 1)
        self.opened = True
        return True

    # ---- content

    def context(self) -> ViewContext:
        return ViewContext(
            run=self.run,
            cursor=self.cursor,
            logs=self.source.logs(self.run.id),
            can_drive=self.driver.drives(),
        )

    def content(self, width: int = 200, height: int = 40) -> StageContent:
        if self.at_home:
            # How the two halves are arranged is decided here, where the width is known, and
            # the home page is told: under the listing the card costs rows the listing would
            # otherwise have had, and a budget that ignored that would draw a screen the
            # layout then crops from the bottom without saying so.
            stacked = width < SIDE_BY_SIDE
            return build_home(HomeContext(self.runs, self.cursor, height, stacked, self.held))
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
        if self.at_home:
            return len(self.runs)
        run = self.run
        it = run.current_iteration
        return {
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
        content = self.content(width, height)
        blocks: list[RenderableType] = []

        if self.opened and self.view in STAGE_INDEX:
            run = self.run
            stage = STAGES[STAGE_INDEX[self.view]]
            state = stage_state(run, self.view)
            blocks.append(
                panel(
                    headline(run, self.view),
                    # The stop, not its state: the strip three lines up draws the state, in
                    # the same colour, and the border below carries it too.
                    ICON[stage.name],
                    stage.name,
                    stage.question,
                    tone={"here": "live", "blocked": "ask", "failed": "bad"}.get(state, "quiet"),
                )
            )
            # The question goes where it was raised, above what it rests on.
            pending = run.pending_decision
            if (
                pending is not None
                and DECISION_STAGE.get(pending.kind, "verdict") == self.view
                and self.asking is None
            ):
                blocks.append(decision_panel(run, pending))
        if self.asking is not None:
            # In the place the panel it replaces would have stood: answering a question is
            # reading it, and a question that moved when you started answering it would make
            # you find it twice.
            asking = self.asking
            blocks.append(Responsive(asking.panel))

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
        that can say you are there. On the home page the row holds what the listing answers
        to, then what would act on the run under the cursor — in that order, because a narrow
        terminal keeps the first keys and the list's own act is ``enter``.
        """
        if self.asking is not None:
            return [(key, label, False) for key, label in self.asking.controls()]
        rows = self.row_count()
        if self.at_home:
            picks: list[tuple[str, str, bool]] = []
            if rows:
                picks += [("↑↓", "move", False), ("enter", "open run", False)]
            picks += [(key, label, False) for key, label in self.controls()]
            if attending(self.runs) is not None:
                picks.append(("n", "what needs you", False))
            return [*picks, ("?", "help", self.helping), ("q", "quit", False)]
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
        if self.at_home:
            return self._home(width, height, note)
        # One reading of what the run needs, for the two places that say it: the band says it
        # in words, the strip by turning the stop it is at. Asked twice they could disagree
        # within a frame — the run settles between the two calls — and the screen would then
        # show a stop turning under a band that says nothing is advancing it.
        attn = self.attention()
        rows = [
            Layout(name="header", size=4),
            Layout(name="band", size=3),
            *([Layout(name="notice", size=1)] if note is not None else []),
            Layout(name="nav", size=3),
            Layout(name="body"),
            Layout(name="footer", size=1),
        ]
        root = Layout()
        root.split_column(*rows)
        root["header"].update(header(self.run, self.animated))
        root["band"].update(attention_band(attn, self.moving(attn), self.paused))
        if note is not None:
            root["notice"].update(note)
        root["nav"].update(Responsive(lambda w: nav_bar(self.run, self.view, w, self.moving(attn))))
        root["body"].update(self.body(width, height))
        root["footer"].update(
            Responsive(
                lambda w: footer_bar(self.footer_keys(), self.run, self.elapsed, not self.paused, w)
            )
        )
        return root

    def _home(self, width: int, height: int, note: RenderableType | None) -> Layout:
        """The home page: the store, the row under the cursor, and how 495 walks a run here.

        Two surfaces of the run screen are missing and one is replaced, all for one reason:
        the header's identity, the band and the pipeline strip each speak for *a* run, and the
        subject here is the store. They used to speak for whichever run was opened last —
        which is how the header could name one run while the cursor sat on another, and how
        ``d`` could answer a question you were not looking at. The strip has no equivalent at
        this scale and goes; the identity and the band do, and say it of the store. What is
        said about one run is said in the card, where the cursor says which run is meant.
        """
        attn = self.store_state()
        rows = [
            Layout(name="header", size=4),
            Layout(name="band", size=3),
            *([Layout(name="notice", size=1)] if note is not None else []),
            Layout(name="body"),
            Layout(name="footer", size=1),
        ]
        root = Layout()
        root.split_column(*rows)
        root["header"].update(store_header(self.runs, self.animated))
        root["band"].update(attention_band(attn, self.moving(attn), self.paused))
        if note is not None:
            root["notice"].update(note)
        root["body"].update(self.body(width, height))
        root["footer"].update(
            Responsive(
                lambda w: footer_bar(
                    self.footer_keys(), None, 0.0, not self.paused, w, store=self.runs
                )
            )
        )
        return root

    def flow(self, width: int) -> Group:
        """The same content without a ``Layout``, for piped output and exports.

        A ``Layout`` clips whatever does not fit and says nothing about it; a surface meant to
        be read after the fact, or captured, has to flow instead.
        """
        note = self.notice_line()
        if self.at_home:
            home = self.store_state()
            return Group(
                store_header(self.runs, self.animated),
                attention_band(home, self.moving(home), self.paused),
                *([note] if note is not None else []),
                self.body(width, 200),
                Responsive(
                    lambda w: footer_bar(
                        self.footer_keys(), None, 0.0, not self.paused, w, store=self.runs
                    )
                ),
            )
        attn = self.attention()
        return Group(
            header(self.run, self.animated),
            attention_band(attn, self.moving(attn), self.paused),
            *([note] if note is not None else []),
            Responsive(lambda w: nav_bar(self.run, self.view, w, self.moving(attn))),
            self.body(width, 200),
            Responsive(
                lambda w: footer_bar(self.footer_keys(), self.run, self.elapsed, not self.paused, w)
            ),
        )
