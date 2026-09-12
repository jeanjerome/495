"""What every stage view returns, and what all of them are given."""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import RenderableType

from harness495.core.models import Run
from harness495.interfaces.tui.logs import Logs, NoLogs


@dataclass
class StageContent:
    """One stage, in the shape all eight share: headline · list · detail.

    The detail follows the cursor rather than replacing the list, which is what lets you read
    six command outputs by pressing ↓ six times.
    """

    body: RenderableType
    rows: int = 0
    detail: RenderableType | None = None
    below: RenderableType | None = None
    label: str = ""
    """What the rows are — ``checks``, ``verdicts``, ``files``. Never the stage's own name:
    repeating it under the headline costs a line and tells the reader nothing."""


@dataclass(frozen=True)
class ViewContext:
    """Everything a stage view is allowed to read.

    A view is a pure function of this: give it the same run and the same cursor and it draws
    the same screen. Nothing in a view writes back.
    """

    run: Run
    cursor: int = 0
    logs: Logs = NoLogs()
    can_drive: bool = False
    """Whether this surface can act on the run. A view names a key only where pressing it
    would do something: a still capture and a ``--read-only`` surface state the command line
    instead."""
