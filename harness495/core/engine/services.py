"""The seam between the engine's state machine and the regions that work for it.

A region takes a :class:`RunServices` rather than an :class:`~harness495.core.engine.Engine`,
so what it may do to the world is the seven collaborators named here and nothing else.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from harness495.core.models import Run, RunStatus
from harness495.core.store import RunStore
from harness495.sandbox import Sandbox


class EmitEvent(Protocol):
    """Append an event to the run's log and hand it to whoever is listening."""

    def __call__(
        self, run: Run, type_: str, message: str = "", data: dict[str, Any] | None = None
    ) -> None: ...


class RunServices:
    """The infrastructure a region of the engine works through: the store it persists to, the
    sandbox it executes in, the event and warning sinks, the worktree the run works in, the
    check that says whether a stop was asked for, and the status setter.

    These seven are what every region reaches for by way of infrastructure, and the only thing
    most of them reach for at all. Naming them as one collaborator is what lets a region take
    what it uses rather than reach for every method of :class:`Engine`.

    Not a value object: ``set_status`` writes the run and emits an event, and ``store`` is the
    state on disk. It is the engine's own services under one name.

    ``sandbox`` is read through a callable rather than held, because the backend is selected on
    the first phase that needs one — after the services are built.
    """

    def __init__(
        self,
        store: RunStore,
        sandbox: Callable[[], Sandbox],
        emit: EmitEvent,
        warn: Callable[[Run, str], None],
        worktree: Callable[[Run], Path],
        stop_check: Callable[[Run], Callable[[], bool]],
        set_status: Callable[[Run, RunStatus], None],
    ) -> None:
        self.store = store
        self.emit = emit
        self.warn = warn
        self.worktree = worktree
        self.stop_check = stop_check
        self.set_status = set_status
        self._sandbox = sandbox

    @property
    def sandbox(self) -> Sandbox:
        return self._sandbox()


__all__ = ["EmitEvent", "RunServices"]
