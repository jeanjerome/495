"""What makes a run move, when the surface is the one driving it.

The source says what a run *is*; a driver is what advances it. They are separate because they
fail differently: reading a run directory always works, advancing one needs a project, a
sandbox, agents and the right to claim the run. A snapshot — an export, a fixture, a
``--read-only`` surface — gets :class:`ReadOnly`, and every control then disappears from the
screen rather than failing under the finger.

Work happens on a thread. An intervention takes minutes and the engine writes its progress to
the store as it goes; the surface is already re-reading that store once a second, so a run
advanced from here is displayed exactly the way one advanced from another terminal is. The
thread is what keeps the clock, the pulse and the keyboard alive while it does.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from harness495.core.config import load_config
from harness495.core.engine import Engine
from harness495.core.models import DecisionMaker, Event, RunMode
from harness495.core.store import RunStore


@dataclass(frozen=True)
class Activity:
    """What the driver is doing to a run right now, and since when."""

    verb: str
    run_id: str
    since: float
    interruptible: bool = True
    """Whether asking the run to stop would reach it. An integration check is one command
    against one ref; it ends before a stop flag could be read."""

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.since


class Driver(Protocol):
    """What the surface may do to a run. Everything here is a command, never a question."""

    notice: str | None
    """The last thing that went wrong, in one line. Cleared on the next keypress."""

    def drives(self) -> bool:
        """Whether this surface can advance runs at all."""
        ...

    def creates(self) -> bool:
        """Whether it can take a new intent — it needs a project, not just a store."""
        ...

    def working(self) -> Activity | None: ...

    def held_elsewhere(self, run_id: str) -> str | None:
        """Who else is advancing this run, if anyone."""
        ...

    def start(self, run_id: str) -> None: ...

    def pause(self, run_id: str) -> None: ...

    def decide(self, run_id: str, choice: str, note: str) -> None: ...

    def integrate(self, run_id: str, ref: str, rerun: bool) -> None: ...

    def merge(self, run_id: str, how: str, rerun: bool) -> None: ...

    def create(self, intent: str, evaluate_ref: str = "") -> str: ...


class ReadOnly:
    """A surface that only looks. Every control refuses, and the shell offers none."""

    notice: str | None = None

    def drives(self) -> bool:
        return False

    def creates(self) -> bool:
        return False

    def working(self) -> Activity | None:
        return None

    def held_elsewhere(self, run_id: str) -> str | None:
        return None

    def _refuse(self) -> None:
        raise RuntimeError("this surface only reads the store; it cannot advance a run")

    def start(self, run_id: str) -> None:
        self._refuse()

    def pause(self, run_id: str) -> None:
        self._refuse()

    def decide(self, run_id: str, choice: str, note: str) -> None:
        self._refuse()

    def integrate(self, run_id: str, ref: str, rerun: bool) -> None:
        self._refuse()

    def merge(self, run_id: str, how: str, rerun: bool) -> None:
        self._refuse()

    def create(self, intent: str, evaluate_ref: str = "") -> str:
        self._refuse()
        return ""


class StoreDriver:
    """Drives runs in this store, one at a time, on a thread of its own.

    One at a time on purpose: a second run started while the first is producing would put two
    agents in two worktrees against one budget line and one screen, and the surface has one
    attention line to say what is happening. The engine's own claim on the run is what keeps
    *other processes* out; this keeps the surface honest with itself.
    """

    def __init__(
        self,
        store: RunStore,
        project: Path | None = None,
        on_event: Callable[[Event], None] | None = None,
        engine_factory: Callable[[], Engine] | None = None,
    ) -> None:
        self.store = store
        self.project = project
        self.on_event = on_event
        #: Built per command rather than held: an engine carries the sandbox it selected and
        #: the stop flag of the run it is walking, and neither survives the next command.
        self.engine_factory = engine_factory
        self.notice: str | None = None
        self._thread: threading.Thread | None = None
        self._activity: Activity | None = None
        self._lock = threading.Lock()

    # ---- what can be done from here

    def drives(self) -> bool:
        return True

    def creates(self) -> bool:
        return self.project is not None

    def working(self) -> Activity | None:
        with self._lock:
            return self._activity

    def held_elsewhere(self, run_id: str) -> str | None:
        return self.store.holder(run_id)

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the current work ends. For a session without a clock to redraw on."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    # ---- commands

    def engine(self) -> Engine:
        if self.engine_factory is not None:
            return self.engine_factory()
        return Engine(self.store, on_event=self.on_event, label="the run surface")

    def start(self, run_id: str) -> None:
        """Advance the run until it blocks, finishes, or is paused from here."""
        held = self.held_elsewhere(run_id)
        if held is not None:
            self.notice = f"{run_id} is already being advanced by {held}"
            return
        self._spawn("advancing", run_id, lambda: self.engine().run(run_id))

    def pause(self, run_id: str) -> None:
        """Ask the run to stop at the next opportunity, wherever it is being driven from.

        A stop is a file in the run directory, not a signal: the engine that reads it may be
        this thread or a process in another terminal, and both look in the same place.
        """
        self.store.request_stop(run_id, "paused from the run surface")

    def decide(self, run_id: str, choice: str, note: str) -> None:
        """Record the answer, then carry on — the decision is asked for the run to continue.

        Applying it is a file write, so it happens here rather than on the thread: the caller
        has just taken the screen down for a prompt and can say straight away that it failed.
        """
        run = self.engine().decide(run_id, choice, note, DecisionMaker.human)
        if not run.is_blocked():
            self.start(run_id)

    def integrate(self, run_id: str, ref: str, rerun: bool) -> None:
        self._spawn(
            "checking the integration",
            run_id,
            lambda: self.engine().check_integration(run_id, ref, rerun),
            interruptible=False,
        )

    def merge(self, run_id: str, how: str, rerun: bool) -> None:
        """Bring the delivered branch into the tree you have checked out, then check it.

        On the thread like the rest, and for the same reason: with the checks re-run it is as
        long as a verification pass. Not interruptible — the integration is one command that
        either happened or was put back, and asking it to stop between the two is asking for
        the state this control exists to avoid.
        """
        self._spawn(
            "integrating the delivered branch",
            run_id,
            lambda: self.engine().merge_delivery(run_id, how, rerun),
            interruptible=False,
        )

    def create(self, intent: str, evaluate_ref: str = "") -> str:
        """Take an intent — or an existing change — and start the run it opens.

        Creating is a directory and a document; it is done here so the new id can be returned
        and the surface can move to it. Only the walking of the pipeline goes on the thread.
        """
        if self.project is None:
            raise RuntimeError("this surface has no project; it cannot create a run")
        config = load_config(self.project, self.store.state_dir)
        mode = RunMode.evaluate if evaluate_ref else RunMode.change
        run = self.engine().create_run(
            intent,
            self.project,
            config,
            mode,
            evaluate_ref=evaluate_ref or None,
            source="surface",
        )
        self.start(run.id)
        return run.id

    # ---- the thread

    def _spawn(
        self,
        verb: str,
        run_id: str,
        work: Callable[[], object],
        interruptible: bool = True,
    ) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                busy = self._activity
                self.notice = f"already {busy.verb} {busy.run_id}" if busy else "already working"
                return
            self._activity = Activity(verb, run_id, time.monotonic(), interruptible)
        self.notice = None
        thread = threading.Thread(target=self._work, args=(work,), daemon=True)
        self._thread = thread
        thread.start()

    def _work(self, work: Callable[[], object]) -> None:
        try:
            work()
        except Exception as exc:  # noqa: BLE001
            # Anything the engine did not turn into a failed run — a missing repository, a
            # claim taken meanwhile, a broken configuration — ends here. A thread that died
            # without saying so would leave the surface reporting work that stopped minutes
            # ago, which is the one thing an attention line must never do.
            self.notice = f"{type(exc).__name__.removesuffix('Error').lower() or 'error'}: {exc}"
        finally:
            with self._lock:
                self._activity = None
