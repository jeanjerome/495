"""Where the surface gets its runs.

The shell never touches the store: it asks a source for runs, events and recorded output, and
that is all a source does. Acting on a run — answering its question, advancing it, checking
what you merged — belongs to a driver, so the same shell renders a live run, a frozen snapshot
for an export, and a fixture in a test, none of which can advance anything by being drawn.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Protocol

from harness495.core.models import Event, Run
from harness495.core.store import RunNotFound, RunStore
from harness495.interfaces.tui.logs import Logs, NoLogs, StoredLogs


class RunSource(Protocol):
    """What the shell needs from the world outside it."""

    def runs(self) -> Sequence[Run]: ...

    def events(self, run_id: str) -> Sequence[Event]: ...

    def logs(self, run_id: str) -> Logs: ...

    def refresh(self, force: bool = False) -> bool:
        """Take in whatever changed since the last call. ``True`` if anything did."""
        ...


class StaticSource:
    """A snapshot that never changes: a preview, an export, a test."""

    def __init__(self, runs: Sequence[Run], events: Sequence[Event] = ()) -> None:
        self._runs = list(runs)
        self._events = list(events)

    def runs(self) -> Sequence[Run]:
        return self._runs

    def events(self, run_id: str) -> Sequence[Event]:
        return [e for e in self._events if e.run_id == run_id] or self._events

    def logs(self, run_id: str) -> Logs:
        return NoLogs()

    def refresh(self, force: bool = False) -> bool:
        return False


class StoreSource:
    """The run directory on disk, re-read on a clock.

    Polling rather than watching: a run is advanced by whichever process owns it — this one,
    another terminal, a CI job — and the only thing all of them agree on is what has been
    written. Re-reading a run and tailing its event file is cheap next to an agent turn, and
    it cannot disagree with what ``495 status`` would print.
    """

    def __init__(self, store: RunStore, interval: float = 1.0) -> None:
        self.store = store
        self.interval = interval
        self._runs: list[Run] = []
        self._events: dict[str, list[Event]] = {}
        self._logs: dict[str, Logs] = {}
        self._last = 0.0
        self.refresh(force=True)

    def runs(self) -> Sequence[Run]:
        return self._runs

    def events(self, run_id: str) -> Sequence[Event]:
        return self._events.get(run_id, [])

    def logs(self, run_id: str) -> Logs:
        got = self._logs.get(run_id)
        if got is None:
            got = self._logs[run_id] = StoredLogs(self.store, run_id)
        return got

    def refresh(self, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and now - self._last < self.interval:
            return False
        self._last = now
        self._runs = self.store.list_runs()
        for run in self._runs:
            # Only the tail is read: the file is append-only, and re-parsing every line of a
            # long run once a second is how a surface starts costing more than the run.
            seen = self._events.setdefault(run.id, [])
            seen.extend(self.store.events(run.id, offset=len(seen)))
        return True

    def load(self, run_id: str) -> Run:
        """One run by id, for a surface opened on a single run."""
        return self.store.load(run_id)

    def exists(self, run_id: str) -> bool:
        try:
            self.store.load(run_id)
        except RunNotFound:
            return False
        return True
